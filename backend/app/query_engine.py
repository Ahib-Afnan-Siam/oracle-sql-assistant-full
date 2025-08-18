# app/query_engine.py
import logging
import re
import traceback
from typing import List, Dict, Any, AsyncGenerator, Tuple, Optional
from datetime import datetime, date
from decimal import Decimal
from statistics import median
#from tabulate import tabulate
from time import time
import cx_Oracle
import json  # ← add
from app.summarizer import summarize_with_mistral, _pipe_snapshot, stream_summary  # ← add 2 symbols
from app.config import SUMMARY_ENGINE, SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET       # ← add 2 constants
from app.vector_store_chroma import hybrid_schema_value_search
from app.ollama_llm import call_ollama
from app.db_connector import connect_to_source
from app.config import OLLAMA_SQL_MODEL
import asyncio
import difflib


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------------------------
# Simple TTL caches (in-memory)
# --------------------------------------------------------------------------------------
RESULT_CACHE_TTL_SEC = 10 * 60          # 10 minutes
LLM_CACHE_TTL_SEC    = 30 * 60          # 30 minutes

_result_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
_llm_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}

_SAMPLE_SQL_RX = re.compile(
    r"(?is)^\s*select\s+\*\s+from\s+[A-Za-z0-9_\"\.]+\s+fetch\s+first\s+\d+\s+rows\s+only\s*$"
)

def _is_sample_sql(sql: str) -> bool:
    s = (sql or "").strip()
    if not _SAMPLE_SQL_RX.match(s):
        return False
    # consider no WHERE/JOINS as pure sample
    return not re.search(r"\bwhere\b|\bjoin\b|\bnatural\b", s, re.IGNORECASE)

_SQL_WS = re.compile(r"\s+")
def _norm_sql_key(sql: str) -> str:
    s = (sql or "").strip().rstrip(";")
    return _SQL_WS.sub(" ", s)

def _cache_get_result(db: str, sql: str) -> Optional[Dict[str, Any]]:
    if _is_sample_sql(sql) or _is_nondeterministic(sql):
        return None  # never serve cached sample
    key = (db, _norm_sql_key(sql))
    entry = _result_cache.get(key)
    if not entry:
        return None
    if time() - entry["ts"] > RESULT_CACHE_TTL_SEC:
        _result_cache.pop(key, None)
        return None
    return entry

MAX_CACHE_ITEMS = 500

def _trim_cache(c: Dict[Tuple[str,str], Dict[str,Any]]):
    if len(c) <= MAX_CACHE_ITEMS:
        return
    # drop oldest first
    for k, _ in sorted(c.items(), key=lambda kv: kv[1]["ts"])[: len(c) - MAX_CACHE_ITEMS]:
        c.pop(k, None)

_NONDET_RX = re.compile(r"\b(SYSDATE|SYSTIMESTAMP|CURRENT_DATE|DBMS_RANDOM)\b", re.I)

def _is_nondeterministic(sql: str) -> bool:
    if _NONDET_RX.search(sql or ""):
        return True
    if re.search(r"\bROWNUM\b", sql or "", re.I) and not re.search(r"\bORDER\s+BY\b", sql or "", re.I):
        return True
    return False

def _cache_set_result(db: str, sql: str, columns, rows, *, cache_ok: bool = True) -> None:
    if not cache_ok:
        return
    if _is_sample_sql(sql) or _is_nondeterministic(sql):
        return
    _result_cache[(db, _norm_sql_key(sql))] = {
        "ts": time(), "columns": columns, "rows": rows, "row_count": len(rows)
    }
    _trim_cache(_result_cache)

def cached_call_ollama(prompt: str, model: str) -> str:
    key = (model, prompt)
    entry = _llm_cache.get(key)
    if entry and time() - entry["ts"] <= LLM_CACHE_TTL_SEC:
        return entry["text"]
    text = call_ollama(prompt, model=model)
    _llm_cache[key] = {"ts": time(), "text": text}
    _trim_cache(_llm_cache)
    return text

# ----------------------------------------------------------------------
# Timeframe guidance (kept dynamic)
# ----------------------------------------------------------------------
TIMEFRAME_GUIDANCE = """
TIMEFRAME TRANSLATION (Oracle):
- today → WHERE <date_col> >= TRUNC(SYSDATE)
- yesterday / last day → WHERE <date_col> >= TRUNC(SYSDATE-1) AND <date_col> < TRUNC(SYSDATE)
- last 7 days → WHERE <date_col> >= TRUNC(SYSDATE) - 7
- this week → WHERE <date_col> >= TRUNC(SYSDATE, 'D')
- last week → WHERE <date_col> >= TRUNC(SYSDATE, 'D') - 7 AND <date_col> < TRUNC(SYSDATE, 'D')
- this month → WHERE <date_col> >= TRUNC(SYSDATE, 'MM')
- last month → WHERE <date_col> >= TRUNC(ADD_MONTHS(SYSDATE,-1),'MM') AND <date_col> < TRUNC(SYSDATE,'MM')
- this quarter → WHERE <date_col> >= TRUNC(SYSDATE, 'Q')
- last quarter → WHERE <date_col> >= ADD_MONTHS(TRUNC(SYSDATE,'Q'), -3) AND <date_col> < TRUNC(SYSDATE,'Q')
- this year → WHERE <date_col> >= TRUNC(SYSDATE, 'YYYY')
- last year → WHERE <date_col> >= ADD_MONTHS(TRUNC(SYSDATE,'YYYY'), -12) AND <date_col> < TRUNC(SYSDATE,'YYYY')

Prefer date columns whose names contain: date, dt, time, created, updated, txn_date, order_date, post_date, delivery_date, etc.
Use TRUNC on date columns when comparing to day/month/quarter boundaries.
"""

# ----------------------------------------------------------------------
# Date normalization for Oracle + explicit date range extraction
# ----------------------------------------------------------------------
DATE_FORMATS = {
    "default": "DD-MON-YYYY",
    "variants": [
        "YYYY-MM-DD",
        "MM/DD/YYYY",
        "DD-MON-YY",
        "MON-DD-YYYY",
        "DD/MM/YYYY",
        "DD/MM/YY",
    ],
}

def normalize_dates(sql: str) -> str:
    for fmt in DATE_FORMATS["variants"]:
        sql = re.sub(
            fr"TO_DATE\('([^']+)'\s*,\s*'{fmt}'\)",
            f"TO_DATE('\\1', '{DATE_FORMATS['default']}')",
            sql,
            flags=re.IGNORECASE,
        )
    return sql


_MON3 = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]

def _parse_day_first_date(s: str) -> Optional[datetime]:
    try:
        parts = re.split(r"[/-]", s.strip())
        if len(parts) != 3:
            return None
        d, m, y = [int(p) for p in parts]
        if y < 100:
            y += 2000 if y < 50 else 1900
        return datetime(y, m, d)
    except Exception:
        return None

def _to_oracle_date(dt: datetime) -> str:
    return f"TO_DATE('{dt.day:02d}-{_MON3[dt.month-1]}-{dt.year}','DD-MON-YYYY')"

def apply_date_range_constraint(sql: str, rng: Optional[Dict[str, str]]) -> str:
    if not rng:
        return sql
    col = rng["column"]
    between = f"{col} BETWEEN {rng['start']} AND {rng['end']}"
    # already present?
    if re.search(rf"\b{re.escape(col)}\b.*\bBETWEEN\b", sql, re.IGNORECASE):
        return sql

    # Split once on the first WHERE and reassemble with parentheses
    parts = re.split(r"(?i)\bWHERE\b", sql, maxsplit=1)
    if len(parts) == 2:
        before, after = parts[0], parts[1].strip()
        if after:
            return f"{before}WHERE ({between}) AND ({after})"
        else:
            return f"{before}WHERE {between}"

    # No WHERE yet: inject before GROUP/ORDER/FETCH if present
    m = re.search(r"(?i)\b(GROUP|ORDER|FETCH)\b", sql)
    if m:
        return sql[:m.start()] + f" WHERE {between} " + sql[m.start():]
    return sql + f" WHERE {between}"


# ----------------------------------------------------------------------
# Prompt construction (dynamic; no hardcoded tables/terms)
# ----------------------------------------------------------------------
def _extract_table_hints(schema_chunks: List[str]) -> str:
    tables = []
    for s in schema_chunks:
        for line in s.splitlines():
            m = re.search(r"\bTABLE\s+([A-Za-z0-9_\.]+)", line, flags=re.IGNORECASE)
            if m:
                tables.append(m.group(1).strip())
    seen, ordered = set(), []
    for t in tables:
        u = t.upper()
        if u not in seen:
            seen.add(u)
            ordered.append(t)
    return ", ".join(ordered[:80]) if ordered else ""

def _is_report_like(user_query: str) -> bool:
    uq = user_query.lower()
    return bool(re.search(r"\b(report|summary|summarize|overview|update|insight|analysis|analyze|status|review)\b", uq))

def generate_sql_prompt(schema_chunks: list, user_query: str) -> str:
    context = "\n\n".join(schema_chunks)
    allowed = _extract_table_hints(schema_chunks)
    report_like = _is_report_like(user_query)

    projection_rules = (
        "Project only the minimal column(s) necessary to answer."
        if not report_like else
        "Prefer a compact descriptive projection: one identifier (id/name/code), one date or period if available, one category (e.g., floor/line/unit/department), and up to two numeric measures most relevant to the question."
    )

    raw_table_hint = (
        "If the user asks to 'show/list <table>' or '<table> table' or says 'grid', "
        "return an UNFILTERED sample:\n"
        "SELECT * FROM <that_table> FETCH FIRST 200 ROWS ONLY.\n"
        "Do NOT add any WHERE filters unless explicitly requested."
    )

    date_range_hint = _date_range_hint_for_prompt(user_query)
    single_table_for_report = _explicit_single_table_report_request(user_query, schema_chunks)
    no_join_guard = (
        f"- The user asked for a report/summary of table {single_table_for_report}. "
        f"Use ONLY {single_table_for_report}. Do NOT join any other table.\n"
        if single_table_for_report else ""
    )

    return f"""
You are an expert Oracle SQL generator.

Return exactly ONE syntactically valid SELECT statement (no markdown fences, no explanation).
It must directly answer the user's question using ONLY the SCHEMA CONTEXT.

STRICT RULES:
- {projection_rules}
{no_join_guard}- If the user specifies a date/time window, include ONLY that window. Otherwise add **no** time filter.
- When a date range is typed like "<col> between DD/MM/YYYY and DD/MM/YYYY" (or "from ... to ..."),
  use: WHERE <col> BETWEEN TO_DATE('dd-mon-yyyy','DD-MON-YYYY') AND TO_DATE('dd-mon-yyyy','DD-MON-YYYY').
  Use TRUNC(<col>) only when comparing to day/month/quarter boundaries from the guidance.
- Do NOT use DISTINCT unless the user explicitly asks for 'distinct' or 'unique'.
- Avoid SELECT * unless the user explicitly asks for 'all columns' OR it is a raw table/show/list/grid request.
- Never combine SELECT * with GROUP BY. If you use GROUP BY, project only grouped columns and aggregates explicitly.
- Use only literal values explicitly present in the question.
- No bind variables.
- Choose tables/columns only if they are present in the SCHEMA CONTEXT.
- If the question mentions floors/lines/units (textile/garments domain), prefer tables/columns that include those concepts **if and only if they appear in the SCHEMA CONTEXT**.
- {raw_table_hint}
- {TIMEFRAME_GUIDANCE}

{date_range_hint}

ALLOWED TABLES (hints): {allowed if allowed else "not specified"}

SCHEMA CONTEXT:
{context}

QUESTION:
{user_query}

SQL:
""".strip()


# ----------------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------------
def is_valid_sql(sql: str, source_id: str) -> bool:
    # Basic guards
    s = (sql or "").strip()
    if not s.lower().startswith("select"):
        return False
    # single SELECT only (no stacked statements / semicolons)
    if ";" in s or s.lower().count(" select ") > 0 and s.lower().find("select", 1) != -1:
        return False
    # refuse bind-style placeholders (your pipeline removes them anyway)
    if re.search(r":\w+", s, re.IGNORECASE):
        return False
    # optionally cap length to avoid abuse
    if len(s) > 100000:
        return False

    try:
        with connect_to_source(source_id) as (conn, _):
            cursor = conn.cursor()
            # parse only; do not execute
            cursor.prepare(s)   # python-oracledb / cx_Oracle parse step
            return True
    except Exception as e:
        logger.warning(f"[Validation Fail] {e}")
        return False


def retry_with_stricter_prompt(user_query: str, schema_chunks: list, error: str) -> str:
    prompt = f"""
A previous SQL attempt failed with: {error.split(':')[0]}

Re-generate ONE Oracle SELECT that directly answers the user's question.

RULES:
- Follow timeframe guidance exactly.
- Use only tables/columns from SCHEMA CONTEXT.
- No bind variables; no explanations; no markdown.
- If it's a report/summary/update, include a compact descriptive projection (id/name/code, date, category, up to two numeric measures).

SCHEMA CONTEXT:
{'\n\n'.join(schema_chunks)}

QUESTION:
{user_query}

SQL:
"""
    sql = cached_call_ollama(prompt, model=OLLAMA_SQL_MODEL)
    return normalize_dates(sql.strip().strip("`").rstrip(";"))

# ----------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------
def to_jsonable(value):
    if hasattr(value, "read"):  # LOB
        return value.read()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

def handle_bind_variables(sql: str, user_query: str) -> str:
    if re.search(r":\w+", sql, re.IGNORECASE):
        sql = re.sub(r"WHERE\s+.*?=.*?:\w+.*?(?=;|$)", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"(AND|OR)\s+.*?=.*?:\w+", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+WHERE\s*$", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+(AND|OR)\s*$", "", sql, flags=re.IGNORECASE)
    return sql

def _set_case_insensitive_session(cursor):
    try:
        cursor.execute("ALTER SESSION SET NLS_COMP=LINGUISTIC")
        cursor.execute("ALTER SESSION SET NLS_SORT=BINARY_CI")
    except Exception as e:
        logger.warning(f"Could not set CI session: {e}")

def _case_insensitive_rewrite(sql: str) -> str:
    m = re.search(r"\bWHERE\b(.*)$", sql, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return sql
    where = m.group(1)
    def repl(match):
        col = match.group(1)
        val = match.group(2)
        return f"UPPER({col}) = UPPER('{val}')"
    new_where = re.sub(
        r"(\b[A-Za-z_][A-Za-z0-9_]*\b)\s*=\s*'([^']*)'",
        repl,
        where,
        flags=re.IGNORECASE,
    )
    if new_where == where:
        return sql
    return sql[: m.start(1)] + new_where

# ----------------------------------------------------------------------
# Display decisions
# ----------------------------------------------------------------------
def determine_display_mode(user_query: str, rows: list) -> str:
    """
    Decide how to render results.
    - If the user asks for BOTH (summary + table), return "both".
    - If they ask only for table/grid, return "table".
    - If they ask only for summary/report, return "summary".
    - Otherwise use simple heuristics (row count → table).
    """
    uq = (user_query or "").strip().lower()
    want_table = bool(re.search(r'\b(show|list|display|table|tabular|rows|grid)\b', uq))
    want_summary = bool(re.search(r'\b(summary|summarise|summarize|overview|report|insights?|analysis|analyze|describe|explain|update|status)\b', uq))

    # Nothing to show yet → keep summary so UI can render a message
    if not rows:
        return "summary"

    # Explicit asks win
    if want_summary and want_table:
        return "both"
    if want_table:
        return "table"
    if want_summary:
        return "summary"

    # WH-questions default to summary unless user said table
    if re.match(r'^\s*(who|what|which|when|where|why|how)\b', uq):
        return "summary"

    # Heuristic fallback
    if len(rows) > 50:
        return "table"
    return "table"

# ----------------------------------------------------------------------
# SQL execution (reads cache; fills cache)
# ----------------------------------------------------------------------
def run_sql(sql: str, selected_db: str, *, cache_ok: bool = True) -> list:
    hit = _cache_get_result(selected_db, sql)
    if hit:
        return hit["rows"]
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        _set_case_insensitive_session(cur)
        cur.execute(sql)
        cols = [desc[0] for desc in cur.description]
        rows = [{cols[i]: to_jsonable(row[i]) for i in range(len(cols))} for row in cur]
    _cache_set_result(selected_db, sql, cols, rows, cache_ok=cache_ok)
    return rows

# ----------------------------------------------------------------------
# Table extraction + optional widen for summaries
# ----------------------------------------------------------------------
_TABLE_FROM_RE = re.compile(
    r"\bfrom\s+([A-Za-z0-9_\.]+)\s*(?:[A-Za-z0-9_]+)?\s*(?:where|group|order|fetch|union|minus|intersect|$)",
    flags=re.IGNORECASE | re.DOTALL,
)

# Replace the old regex + function
_FROM_BLOCK_RE = re.compile(
    r'(?is)\bfrom\b\s+(.*?)\s*(?:\bwhere\b|\bgroup\b|\border\b|\bfetch\b|\bunion\b|\bminus\b|\bintersect\b|$)'
)

def extract_main_table(sql: str) -> Optional[str]:
    """
    Return the first table after FROM, even if the query has JOINs/aliases/NATURAL JOIN.
    """
    if not sql:
        return None
    m = _FROM_BLOCK_RE.search(sql)
    if not m:
        return None

    block = m.group(1).strip()
    # Take the part before any join/comma/ON keyword
    head = re.split(r'(?i)\bjoin\b|\bnatural\b|\bon\b|,', block)[0].strip()
    # Remove alias; keep only the table token (quoted or unquoted)
    m2 = re.match(r'\s*(?:"([^"]+)"|([A-Za-z0-9_\.]+))', head)
    if not m2:
        return None
    t = m2.group(1) or m2.group(2)
    return t.strip()


def _allowed_tables_from_context(schema_chunks: List[str]) -> List[str]:
    """Pull a deduped list of table names from the schema context."""
    rx = re.compile(r"\bTABLE\s+([A-Za-z0-9_\.]+)", re.IGNORECASE)
    seen = set()
    out: List[str] = []
    for chunk in schema_chunks or []:
        for m in rx.finditer(chunk):
            t = m.group(1).strip()
            u = t.upper()
            if u not in seen:
                seen.add(u)
                out.append(t)
    return out

def _norm_token(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def _fuzzy_find_table(user_query: str, schema_tables: List[str], threshold: float = 0.90) -> Optional[str]:
    """
    Best fuzzy match between user text and schema table names.
    Handles spaces vs underscores and small typos. Works with fully qualified names too.
    """
    uq = _norm_token(user_query)
    best, best_ratio = None, 0.0
    for t in schema_tables or []:
        for cand in (t, t.split('.')[-1]):  # full and short
            r = difflib.SequenceMatcher(None, _norm_token(cand), uq).ratio()
            if r > best_ratio:
                best, best_ratio = t, r
    return best if best_ratio >= threshold else None

def _guess_table_from_query(user_query: str, schema_chunks: List[str]) -> Optional[str]:
    """
    Heuristic: choose the longest table name that appears (full or unqualified)
    in the user text. If no literal match, try fuzzy.
    """
    if not user_query:
        return None
    uq = user_query.lower()
    candidates: List[Tuple[int, str]] = []
    allowed = _allowed_tables_from_context(schema_chunks)

    for t in allowed:
        tl = t.lower()
        short = tl.split(".")[-1]
        if tl in uq or short in uq:
            candidates.append((len(short), t))

    if candidates:
        candidates.sort(reverse=True)  # prefer longer/stronger match
        return candidates[0][1]

    # Fuzzy fallback (handles spaces vs underscores, small typos)
    return _fuzzy_find_table(user_query, allowed)


def _explicit_single_table_report_request(user_query: str, schema_chunks: List[str]) -> Optional[str]:
    """
    True when user asks for a 'report/summary of <one table>' with no join cues.
    Returns that table name or None if not applicable.
    """
    if not _is_report_like(user_query):
        return None
    uq = (user_query or "").lower()
    # any obvious join/compare language → not single-table
    if re.search(r"\b(join|merge|link|combine|across|between\s+tables|compare|vs\.?|union)\b", uq):
        return None

    # count how many allowed table names are mentioned
    tables = _allowed_tables_from_context(schema_chunks)
    mentioned = []
    for t in tables:
        tl = t.lower()
        short = tl.split(".")[-1]
        if tl in uq or short in uq:
            mentioned.append(t)

    if len(mentioned) == 1:
        return mentioned[0]

    # fallback: try our guesser
    return _fuzzy_find_table(user_query, tables)


def widen_results_if_needed(rows: list, original_sql: str, selected_db: str, display_mode: str) -> list:
    if display_mode != "summary":
        return rows
    if not rows or not isinstance(rows[0], dict):
        return rows
    if len(rows[0].keys()) > 3:
        return rows
    table = extract_main_table(original_sql or "")
    if not table:
        return rows
    try:
        widened_sql = f"SELECT * FROM {table} FETCH FIRST 200 ROWS ONLY"
        widened = run_sql(widened_sql, selected_db, cache_ok=False)
        return widened or rows
    except Exception as e:
        logger.warning(f"Widen failed for {table}: {e}")
        return rows

# ----------------------------------------------------------------------
# Descriptive, well-detailed summary/report
# ----------------------------------------------------------------------
def summarize_results(rows: list, user_query: str) -> str:
    if not rows:
        return "No results found."
    if not isinstance(rows[0], dict):
        return f"Rows: {len(rows)}"

    from collections import Counter, defaultdict
    n = len(rows)
    cols = list(rows[0].keys())

    SAMPLE_MAX = 6000
    sample = rows if n <= SAMPLE_MAX else rows[::max(1, n // SAMPLE_MAX)][:SAMPLE_MAX]

    METRIC_HINT = re.compile(r'(amt|amount|total|price|sal|salary|value|qty|quantity|cost|revenue|sales|score|count|rate|percent|pct|efficiency|output)$', re.I)
    ID_NAME_HINT = re.compile(r'(?:^|_)(id|no|code|key|num|number)$', re.I)
    LABEL_HINT = re.compile(r'(name|title|desc|description|label)$', re.I)

    ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}')
    ORA_DATE = re.compile(r'^(\d{2})-([A-Za-z]{3})-(\d{2,4})')
    MON = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,"JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

    def is_num(v): return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)
    def is_date_like(v):
        if isinstance(v, (datetime, date)): return True
        if isinstance(v, str): return bool(ISO_DATE.match(v) or ORA_DATE.match(v))
        return False
    def to_dt(v):
        if isinstance(v, datetime): return v
        if isinstance(v, date): return datetime(v.year, v.month, v.day)
        if isinstance(v, str):
            s = v.strip()
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                m = ORA_DATE.match(s[:11])
                if m:
                    dd = int(m.group(1)); mon = MON.get(m.group(2).upper(), 1); yy = int(m.group(3))
                    if yy < 100: yy += 2000 if yy < 50 else 1900
                    try: return datetime(yy, mon, dd)
                    except Exception: return None
        return None
    def fmt_num(x):
        if x is None: return "—"
        if isinstance(x, Decimal): x = float(x)
        s = f"{x:,.2f}"
        return s.rstrip("0").rstrip(".")
    def col_vals(c, rl): return [r.get(c) for r in rl]

    numeric, dates, cats, nulls, label_cols = [], [], [], [], []
    for c in cols:
        vals = col_vals(c, sample)
        non_null = [v for v in vals if v not in (None, "")]
        if len(vals) - len(non_null):
            nulls.append((c, len(vals) - len(non_null), len(vals)))
        if not non_null:
            continue
        probe = next((v for v in non_null if v not in (None, "")), None)
        if probe is None:
            continue
        if is_num(probe):
            name_is_metric = bool(METRIC_HINT.search(c))
            name_looks_id = bool(ID_NAME_HINT.search(c))
            uniq_ratio = len(set(non_null)) / max(1, len(non_null))
            if name_looks_id and not name_is_metric:
                continue
            if uniq_ratio > 0.98 and not name_is_metric:
                continue
            numeric.append(c)
        elif is_date_like(probe):
            dates.append(c)
        else:
            uniq = len(set(non_null))
            limit = min(20, max(5, int(0.7 * len(non_null))))
            avg_len = sum(len(str(v)) for v in non_null[:500]) / min(500, len(non_null))
            if LABEL_HINT.search(c):
                label_cols.append(c)
            if 1 < uniq <= limit and avg_len <= 40:
                cats.append(c)

    label = label_cols[0] if label_cols else (cats[0] if cats else (cols[0] if cols else None))

    numeric.sort(key=lambda c: (not bool(METRIC_HINT.search(c)), c.lower()))
    metrics = numeric[:2]
    cats = cats[:2]
    dates = dates[:1]

    bullets = []
    opening = f"This dataset contains {n:,} row(s) across {len(cols)} column(s)."
    bullets.append(f"• Scope: {opening}")

    top_cat_for_narrative = None
    from collections import Counter
    for c in cats:
        vals = [v for v in col_vals(c, sample) if v not in (None, "")]
        if not vals:
            continue
        cnt = Counter(vals)
        total = sum(cnt.values())
        top = cnt.most_common(8)
        parts = [f"{k} ({v:,} • {v/total:.0%})" for k, v in top]
        bullets.append(f"• {c}: " + ", ".join(parts))
        if top and top_cat_for_narrative is None:
            top_cat_for_narrative = (c, top)

    def pctl(sorted_vals, p):
        if not sorted_vals: return None
        k = (len(sorted_vals)-1) * p
        f = int(k); c = f if k.is_integer() else f+1
        if f == c: return sorted_vals[f]
        return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

    primary_metric_summary = None
    for idx, c in enumerate(metrics):
        vals = [float(v) for v in col_vals(c, sample) if is_num(v)]
        if not vals:
            continue
        vals.sort()
        mn, mx, med = vals[0], vals[-1], median(vals)
        avg = sum(vals)/len(vals)
        p80 = pctl(vals, 0.80)
        total = sum(vals)
        bullets.append(f"• {c}: min {fmt_num(mn)}, median {fmt_num(med)}, avg {fmt_num(avg)}, p80 {fmt_num(p80)}, max {fmt_num(mx)}, sum {fmt_num(total)}")
        if primary_metric_summary is None:
            primary_metric_summary = (c, mn, med, avg, p80, mx)

    if cats and metrics:
        from collections import defaultdict
        cat = cats[0]; metric = metrics[0]
        agg = defaultdict(lambda: {"n": 0, "s": 0.0})
        for r in sample:
            k = r.get(cat)
            v = r.get(metric)
            if k in (None, "") or not isinstance(v, (int, float, Decimal)):
                continue
            agg[k]["n"] += 1
            agg[k]["s"] += float(v)
        if agg:
            items = sorted(agg.items(), key=lambda kv: kv[1]["n"], reverse=True)[:6]
            parts = [f"{k}: avg {fmt_num(v['s']/v['n'])}, total {fmt_num(v['s'])} (n={v['n']:,})" for k, v in items]
            bullets.append(f"• {cat} × {metric}: " + "; ".join(parts))

    for c in dates:
        dts = [to_dt(v) for v in col_vals(c, sample)]
        dts = [d for d in dts if d]
        if dts:
            early, late = min(dts), max(dts)
            bullets.append(f"• {c}: from {early.date()} to {late.date()}")

    flagged = [(c, k, k/total) for c, k, total in nulls if total and (k/total) >= 0.10]
    flagged.sort(key=lambda t: t[2], reverse=True)
    for c, k, r in flagged[:3]:
        bullets.append(f"• {c}: {k:,} nulls ({r:.0%})")

    narrative_parts = []
    if top_cat_for_narrative:
        c, top = top_cat_for_narrative
        lead_name, lead_cnt = top[0]
        total = sum(v for _, v in top)
        share = f"{lead_cnt/total:.0%}" if total else "—"
        narrative_parts.append(f"In categorical terms, **{c}** is led by **{lead_name}** ({share}).")
    if primary_metric_summary:
        c, mn, med, avg, p80, mx = primary_metric_summary
        narrative_parts.append(f"The primary metric **{c}** spans {fmt_num(mn)}–{fmt_num(mx)} (median {fmt_num(med)}, average {fmt_num(avg)}, 80th percentile {fmt_num(p80)}).")

    conclusion = (
        "Overall, the report summarises distribution, key categories, and coverage. "
        "If you need a floor-wise or line-wise update (e.g., sewing output/efficiency), "
        "specify the time window and KPI, and I’ll produce a focused breakdown."
    )

    return "Detailed report:\n" + " ".join(narrative_parts) + "\n" + "\n".join(bullets) + "\n" + conclusion

# ----------------------------------------------------------------------
# Entity lookup: fast path (value probe)
# ----------------------------------------------------------------------
_NAMEISH = {"NAME", "FULL_NAME", "ENAME", "TITLE", "JOB", "POSITION", "ROLE", "DESIGNATION"}

def _is_entity_lookup(q: str) -> bool:
    q = (q or "").strip()
    return bool(re.search(r"^\s*(who|what)\s+is\b", q, re.I)) or len(q.split()) <= 3

def _needle_from_question(q: str) -> str:
    m = re.search(r"(?:who|what)\s+is\s+(.+)", q, re.I)
    if m:
        return m.group(1).strip().strip("?")
    return q.strip().strip("?")

_NAME_ROLE_COLS = ("ENAME","NAME","FULL_NAME","TITLE","JOB","POSITION","ROLE","DESIGNATION")

def _list_name_like_columns(selected_db: str, limit_tables: int = 400) -> List[Dict[str, str]]:
    sql = f"""
    SELECT /*+ FIRST_ROWS(200) */
           table_name, column_name
      FROM user_tab_columns
     WHERE data_type IN ('VARCHAR2','CHAR','NVARCHAR2','NCHAR')
       AND (
            { " OR ".join([f"UPPER(column_name) = '{c}'" for c in _NAME_ROLE_COLS]) }
           OR UPPER(column_name) LIKE '%NAME%'
           OR UPPER(column_name) LIKE '%TITLE%'
           OR UPPER(column_name) LIKE '%ROLE%'
           OR UPPER(column_name) LIKE '%POSITION%'
           OR UPPER(column_name) LIKE '%DESIGNATION%'
       )
     FETCH FIRST {limit_tables} ROWS ONLY
    """
    out: List[Dict[str, str]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        try:
            cur.execute(sql)
            for t, c in cur.fetchall():
                out.append({"table": t, "column": c})
        except Exception as e:
            logger.warning(f"[Meta fallback] column scan failed: {e}")
        finally:
            try: cur.close()
            except: pass
    seen = set(); dedup = []
    for x in out:
        k = (x["table"], x["column"])
        if k not in seen:
            seen.add(k); dedup.append(x)
    return dedup

def _merge_candidates(primary: List[Dict[str, str]], fallback: List[Dict[str, str]], cap: int = 200) -> List[Dict[str, str]]:
    seen = set()
    merged = []
    for lst in (primary, fallback):
        for x in lst:
            k = (x["table"], x["column"])
            if k not in seen:
                merged.append(x); seen.add(k)
            if len(merged) >= cap:
                return merged
    return merged

def _candidate_columns(selected_db: str, query_text: str, top_k: int = 12) -> List[Dict[str, str]]:
    hits = hybrid_schema_value_search(query_text, selected_db=selected_db, top_k=top_k)
    cols = []
    for h in hits:
        meta = (h or {}).get("metadata", {})
        if meta.get("kind") == "column" and meta.get("source_table") and meta.get("column"):
            cols.append({"table": meta["source_table"], "column": meta["column"]})
    seen = set()
    dedup = []
    for c in cols:
        key = (c["table"], c["column"])
        if key not in seen:
            dedup.append(c)
            seen.add(key)
    dedup.sort(key=lambda c: 0 if any(k in c["column"].upper() for k in _NAMEISH) else 1)
    return dedup[:25]

def _quick_value_probe(selected_db: str, needle: str, candidates: List[Dict[str, str]], limit_per_col: int = 5) -> List[Dict[str, Any]]:
    if not needle or not candidates:
        return []
    esc = needle.upper().replace("'", "''")
    results: List[Dict[str, Any]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        _set_case_insensitive_session(cur)
        for c in candidates:
            table = c["table"]; col = c["column"]
            sql = f"SELECT {col} FROM {table} WHERE UPPER({col}) LIKE '%{esc}%' AND ROWNUM <= {limit_per_col}"
            try:
                cur.execute(sql)
                for r in cur.fetchall():
                    results.append({"table": table, "column": col, "value": to_jsonable(r[0])})
            except Exception:
                continue
        try:
            cur.close()
        except Exception:
            pass
    return results[:50]

# --- Date range parsing -------------------------------------------------
# Handles:
#   "<col> between 01/07/2025 and 31/07/2025"
#   "<col> will be between 01/07/2025 and 31/07/2025"
#   "<col> is between 01/07/2025 and 31/07/2025"
DATE_RANGE_PATTERNS = [
    re.compile(
        r"\b(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s*(?:is|was|are|were|will\s+be|shall\s+be|be)\s+between\s+"
        r"(?P<d1>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:and|to)\s+(?P<d2>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s*(?:between|from)\s+"
        r"(?P<d1>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:and|to)\s+(?P<d2>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.IGNORECASE,
    ),
]

# Words that must NEVER be treated as a column name
_DATE_RANGE_STOPWORDS = {"be", "is", "was", "are", "were", "will", "shall"}

def _try_match_date_range(text: str):
    for rx in DATE_RANGE_PATTERNS:
        m = rx.search(text or "")
        if not m:
            continue
        col = (m.group("col") or "").strip()
        if col.lower() in _DATE_RANGE_STOPWORDS:
            continue
        d1 = _parse_day_first_date(m.group("d1"))
        d2 = _parse_day_first_date(m.group("d2"))
        if d1 and d2:
            if d2 < d1:
                d1, d2 = d2, d1
            return col, d1, d2
    return None

def extract_explicit_date_range(user_query: str) -> Optional[Dict[str, str]]:
    hit = _try_match_date_range(user_query)
    if not hit:
        return None
    col, d1, d2 = hit
    return {"column": col, "start": _to_oracle_date(d1), "end": _to_oracle_date(d2)}

# --- Date-range hint for the prompt -----------------------------------------
def _date_range_hint_for_prompt(user_query: str) -> str:
    hit = _try_match_date_range(user_query)
    if not hit:
        return ""
    col, d1, d2 = hit
    return (
        "USER-SPECIFIED DATE RANGE:\n"
        f"- The user provided a range for column {col}.\n"
        f"- Use: WHERE {col} BETWEEN {_to_oracle_date(d1)} AND {_to_oracle_date(d2)}\n"
        "Do not invent other time filters."
    )

# ----------------------------------------------------------------------
# Guardrail: remove unrequested time predicates
# ----------------------------------------------------------------------
_TIME_KEYWORDS_RX = re.compile(
    r"\b(today|yesterday|this (?:week|month|quarter|year)|last (?:week|month|quarter|year)|"
    r"last \d+\s+days?|past \d+\s+days?|last \d+\s+months?|from \d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+(?:to|and)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)

def _user_requested_time_window(q: str) -> bool:
    return bool(_TIME_KEYWORDS_RX.search(q or "")) or extract_explicit_date_range(q) is not None

def strip_unprompted_time_filters(sql: str, user_query: str) -> str:
    """
    If the user didn't ask for a timeframe, remove obviously time-based WHERE clauses.
    Keeps non-time filters intact. Heuristic; intentionally conservative.
    """
    if _user_requested_time_window(user_query):
        return sql

    parts = re.split(r"(?i)\bWHERE\b", sql, maxsplit=1)
    if len(parts) != 2:
        return sql

    before, after = parts[0], parts[1]
    m = re.search(r"(?i)\b(GROUP|ORDER|FETCH|OFFSET|LIMIT)\b", after)
    cond = after if not m else after[:m.start()]
    tail = "" if not m else after[m.start():]

    # Tokenize on AND/OR while keeping connectors
    tokens = re.split(r"(\band\b|\bor\b)", cond, flags=re.IGNORECASE)
    keep: List[str] = []

    def is_timey(s: str) -> bool:
        s = s or ""
        if re.search(r"(SYSDATE|SYSTIMESTAMP|CURRENT_DATE|TO_DATE\s*\(|TRUNC\s*\()", s, re.IGNORECASE):
            return True
        if re.search(r"(date|dt|time|hiredate|created|updated|txn|order_date|post_date|delivery)", s, re.IGNORECASE) and \
           re.search(r"\bbetween\b|>=|<=|<|>", s, re.IGNORECASE):
            return True
        return False

    pending = None
    for t in tokens:
        if re.fullmatch(r"\s*(and|or)\s*", t, flags=re.IGNORECASE):
            pending = t.strip().upper()
            continue
        clause = (t or "").strip()
        if not clause:
            continue
        if is_timey(clause):
            pending = None
            continue
        if keep and pending:
            keep.append(pending)
        keep.append(clause)
        pending = None

    if not keep:
        return (before + " " + tail).strip()

    clean_where = " ".join(keep).strip()
    return f"{before}WHERE {clean_where} {tail}".rstrip()

_GROUP_BY_TAIL = re.compile(
    r'(?is)\s+group\s+by\b.*?(?=(\border\b|\bfetch\b|\boffset\b|\blimit\b|$))'
)

def _strip_group_by_with_star(sql: str) -> str:
    """If the statement is SELECT * ... GROUP BY ..., drop the GROUP BY clause."""
    if re.match(r'(?is)^\s*select\s+\*\s+from\b', sql or '') and re.search(r'(?is)\bgroup\s+by\b', sql or ''):
        return _GROUP_BY_TAIL.sub('', sql).strip()
    return sql


# ----------------------------------------------------------------------
# Main (non-streaming)
# ----------------------------------------------------------------------
def process_question(user_query: str, selected_db: str) -> dict:
    logger.info(f"[User Query] {user_query} (DB: {selected_db})")

    results = hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=10)
    schema_chunks = [r["document"] for r in results] if results else []
    if not schema_chunks:
        return {"error": "No schema context found."}

    # ---- Fast path for entity lookups ----
    if _is_entity_lookup(user_query):
        needle = _needle_from_question(user_query)
        candidates = _candidate_columns(selected_db, user_query)
        if len(candidates) < 5:
            meta_cols = _list_name_like_columns(selected_db)
            candidates = _merge_candidates(candidates, meta_cols, cap=200)

        probe_hits = _quick_value_probe(selected_db, needle, candidates)
        if probe_hits:
            from collections import Counter
            cc = Counter((h["table"], h["column"]) for h in probe_hits)
            def score(k):
                t, c = k
                boost = 1 if any(n in c.upper() for n in _NAMEISH) else 0
                return (cc[k], boost)
            best_table, best_col = sorted(cc.keys(), key=score, reverse=True)[0]
            esc = needle.upper().replace("'", "''")
            sql = f"SELECT * FROM {best_table} WHERE UPPER({best_col}) LIKE '%{esc}%' FETCH FIRST 200 ROWS ONLY"
            try:
                rows = run_sql(sql, selected_db)
                if not rows and extract_explicit_date_range(user_query):
                    return {
                        "status": "success",
                        "summary": "No data found for the requested date range.",
                        "sql": sql,
                        "display_mode": determine_display_mode(user_query, []),  # or determine_display_mode(user_query, [])
                        "results": {"columns": [], "rows": [], "row_count": 0},
                        "schema_context": schema_chunks,
                    }
                if not rows:
                    main_table = extract_main_table(sql or "")
                    if main_table:
                        try:
                            sample_sql = f"SELECT * FROM {main_table} FETCH FIRST 200 ROWS ONLY"
                            rows = run_sql(sample_sql, selected_db)
                            if rows:
                                sql = sample_sql
                        except Exception as e:
                            logger.warning(f"Sample fallback failed for {main_table}: {e}")
            except Exception as e:
                logger.error(f"[Probe SQL Error] {e}")
                return {"error": f"Oracle query failed: {str(e)}", "sql": sql}

            display_mode = determine_display_mode(user_query, rows)

            rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode)
            python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""

            if display_mode in ["summary", "both"]:
                cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
                try:
                    summary = summarize_with_mistral(
                        user_query=user_query,
                        columns=cols_for_llm,
                        rows=rows_for_summary,
                        backend_summary=python_summary,
                        sql=sql,
                    ) if SUMMARY_ENGINE == "llm" else python_summary
                except Exception as e:
                    logger.warning(f"LLM summary failed, falling back to python summary: {e}")
                    summary = python_summary
            else:
                summary = ""

            return {
                "status": "success",
                "summary": summary,
                "sql": sql,
                "display_mode": display_mode,
                "results": {
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows),
                },
                "schema_context": schema_chunks,
            }
        # fall through to LLM path if no probe hits

    # ---- LLM path ----
    prompt = generate_sql_prompt(schema_chunks, user_query)
    sql = cached_call_ollama(prompt, model=OLLAMA_SQL_MODEL)
    sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
    sql = handle_bind_variables(sql, user_query)
    sql = normalize_dates(sql)
    # enforce explicit date range & raw table asks
    rng = extract_explicit_date_range(user_query)
    sql = apply_date_range_constraint(sql, rng)
    sql = enforce_raw_table_request(user_query, sql)
    sql = strip_unprompted_time_filters(sql, user_query) # ← guardrail
    sql = _strip_group_by_with_star(sql)  
    logger.info(f"[Generated SQL] {sql}")

    # --- Execute, with retry+fallback, and ensure `rows` is always defined ---
    used_fallback = False

    if not is_valid_sql(sql, selected_db):
        logger.warning("[Retry] Initial SQL failed. Retrying.")
        sql = retry_with_stricter_prompt(user_query, schema_chunks, "parse/validation error")
        sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
        sql = handle_bind_variables(sql, user_query)
        sql = normalize_dates(sql)
        rng = extract_explicit_date_range(user_query)
        sql = apply_date_range_constraint(sql, rng)
        sql = enforce_raw_table_request(user_query, sql)
        sql = strip_unprompted_time_filters(sql, user_query)
        sql = _strip_group_by_with_star(sql)

        if not is_valid_sql(sql, selected_db):
            # Heuristic fallback to a safe table sample
            tbl = extract_main_table(sql) or _guess_table_from_query(user_query, schema_chunks)
            if tbl:
                # IMPORTANT: if user gave an explicit date range, do NOT sample
                if extract_explicit_date_range(user_query):
                    return {"error": "Could not generate valid SQL for the specified date range.", "sql": sql}
                fallback = f"SELECT * FROM {tbl} FETCH FIRST 200 ROWS ONLY"
                if is_valid_sql(fallback, selected_db):
                    logger.info(f"[Fallback] Using table sample from {tbl}")
                    sql = fallback
                    rows = run_sql(sql, selected_db, cache_ok=False)  # run once
                    used_fallback = True
                else:
                    return {"error": "Retry failed to produce valid SQL.", "sql": sql}
            else:
                return {"error": "Retry failed to produce valid SQL.", "sql": sql}

    # If we did NOT take the fallback path, execute the (validated) SQL now
    if not used_fallback:
        try:
            rows = run_sql(sql, selected_db)
            if not rows and extract_explicit_date_range(user_query):
                return {
                    "status": "success",
                    "summary": "No data found for the requested date range.",
                    "sql": sql,
                    "display_mode": determine_display_mode(user_query, []),
                    "results": {"columns": [], "rows": [], "row_count": 0},
                    "schema_context": schema_chunks,
                }
        except Exception as e:
            logger.error(f"[Oracle Error] {e}")
            return {"error": f"Oracle query failed: {str(e)}", "sql": sql}

    display_mode = determine_display_mode(user_query, rows)

    rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode)
    python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""

    if display_mode in ["summary", "both"]:
        cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
        try:
            summary = summarize_with_mistral(
                user_query=user_query,
                columns=cols_for_llm,
                rows=rows_for_summary,
                backend_summary=python_summary,
                sql=sql,
            ) if SUMMARY_ENGINE == "llm" else python_summary
        except Exception as e:
            logger.warning(f"LLM summary failed, falling back to python summary: {e}")
            summary = python_summary
    else:
        summary = ""

    return {
        "status": "success",
        "summary": summary,
        "sql": sql,
        "display_mode": display_mode,
        "results": {
            "columns": list(rows[0].keys()) if rows else [],
            "rows": [list(r.values()) for r in rows] if rows else [],
            "row_count": len(rows),
        },
        "schema_context": schema_chunks,
    }

# If the user asked for a table/show/list, make sure we return a wide sample
_TABLE_LIKE_RE = re.compile(r"\b(show|list|display|table|grid|all columns)\b", re.I)

def enforce_raw_table_request(user_query: str, sql: str) -> str:
    if not _TABLE_LIKE_RE.search(user_query or ""):
        return sql

    rng = extract_explicit_date_range(user_query)
    has_where = bool(re.search(r"\bWHERE\b", sql or "", re.I))
    has_join = bool(re.search(r"\bJOIN\b|\bNATURAL\b", sql or "", re.I))
    m = _TABLE_FROM_RE.search(sql or "")  # keep your existing regex if you still use it
    main_tbl = extract_main_table(sql or "")

    def ensure_fetch(s: str) -> str:
        return s if re.search(r"fetch\s+first\s+\d+\s+rows\s+only", s, re.I) else s.rstrip() + " FETCH FIRST 200 ROWS ONLY"

    # Force SELECT * but keep everything after FROM
    sql_star = re.sub(r"(?is)^select\s+.*?\bfrom\b", "SELECT * FROM ", sql or "", count=1)

    if rng:
        sql_star = apply_date_range_constraint(sql_star, rng)
        return ensure_fetch(sql_star)

    if has_where:
        # respect existing filters
        return ensure_fetch(sql_star)

    # NEW: user wants a grid, no filters, and the SQL has JOINs → just show a single-table sample
    if has_join and main_tbl:
        return f"SELECT * FROM {main_tbl} FETCH FIRST 200 ROWS ONLY"

    # Otherwise: raw sample of the first table we can find
    if main_tbl:
        return f"SELECT * FROM {main_tbl} FETCH FIRST 200 ROWS ONLY"

    # Fallback to previous behavior if we couldn't determine the table safely
    if m:
        table = m.group(1)
        return f"SELECT * FROM {table} FETCH FIRST 200 ROWS ONLY"

    return sql

def _repair_sql_on_runtime_error(sql: str, selected_db: str, err_msg: str) -> Optional[str]:
    em = (err_msg or "").upper()

    # ORA-00979: invalid GROUP BY expression
    if "ORA-00979" in em:
        fixed = _strip_group_by_with_star(sql)
        if fixed != sql:
            return fixed
        tbl = extract_main_table(sql)
        if tbl:
            return f"SELECT * FROM {tbl} FETCH FIRST 200 ROWS ONLY"

    # ORA-00904/00942: invalid identifier or table/view does not exist
    if "ORA-00904" in em or "ORA-00942" in em:
        tbl = extract_main_table(sql)
        if tbl:
            return f"SELECT * FROM {tbl} FETCH FIRST 200 ROWS ONLY"

    return None


# ----------------------------------------------------------------------
# Streaming
# ----------------------------------------------------------------------
async def process_question_streaming(
    user_query: str, selected_db: str
) -> AsyncGenerator[dict, None]:
    sql = ""
    logger.info(f"[User Query - Streaming] {user_query} (DB: {selected_db})")

    try:
        # Phase 1: retrieval
        yield {"phase": "Searching schema context...", "stage": "retrieval"}
        await asyncio.sleep(0)
        results = hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=10)
        schema_chunks = [r["document"] for r in results] if results else []
        user_has_explicit_range = extract_explicit_date_range(user_query) is not None
        if not schema_chunks:
            yield {"error": {"error": "NO_SCHEMA_CONTEXT", "message": "No relevant schema information found"}}
            await asyncio.sleep(0)
            return

        # Phase 1.5: entity probe
        if _is_entity_lookup(user_query):
            needle = _needle_from_question(user_query)
            yield {"phase": f"Looking up '{needle}' in likely columns...", "stage": "entity_probe"}
            await asyncio.sleep(0)
            candidates = _candidate_columns(selected_db, user_query)
            if len(candidates) < 5:
                meta_cols = _list_name_like_columns(selected_db)
                candidates = _merge_candidates(candidates, meta_cols, cap=200)

            probe_hits = _quick_value_probe(selected_db, needle, candidates)
            if probe_hits:
                from collections import Counter
                cc = Counter((h["table"], h["column"]) for h in probe_hits)
                def score(k):
                    t, c = k
                    boost = 1 if any(n in c.upper() for n in _NAMEISH) else 0
                    return (cc[k], boost)
                best_table, best_col = sorted(cc.keys(), key=score, reverse=True)[0]
                esc = needle.upper().replace("'", "''")
                sql = f"SELECT * FROM {best_table} WHERE UPPER({best_col}) LIKE '%{esc}%' FETCH FIRST 200 ROWS ONLY"
                yield {"phase": "Executing query...", "stage": "execute", "sql": sql}
                await asyncio.sleep(0)

                # cache check
                hit = _cache_get_result(selected_db, sql)
                if hit:
                    display_mode = determine_display_mode(user_query, hit["rows"])
                    rows_for_summary = widen_results_if_needed(hit["rows"], sql, selected_db, display_mode)
                    python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
                    if display_mode in ["summary", "both"]:
                        cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
                        summary = summarize_with_mistral(
                            user_query=user_query,
                            columns=cols_for_llm,
                            rows=rows_for_summary,
                            backend_summary=python_summary,
                            sql=sql,
                        ) if SUMMARY_ENGINE == "llm" else python_summary
                    else:
                        summary = ""

                    if display_mode not in ["summary", "both"]:
                        yield {"phase": "Done", "stage": "done"}
                        await asyncio.sleep(0)

                    response: Dict[str, Any] = {
                        "status": "success",
                        "sql": sql,
                        "display_mode": display_mode,
                        "results": {
                            "columns": hit["columns"],
                            "rows": [list(r.values()) for r in hit["rows"]] if display_mode in ["table", "both"] else [],
                            "row_count": hit["row_count"],
                        },
                        "schema_context": schema_chunks,
                        "summary": summary,
                    }
                    yield response
                    return

                try:
                    rows = run_sql(sql, selected_db)
                except Exception as e:
                    yield {"error": {"error": "ORACLE_ERROR", "message": str(e), "sql": sql}}
                    await asyncio.sleep(0)
                    return

                display_mode = determine_display_mode(user_query, rows)

                rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode)
                python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
                if display_mode in ["summary", "both"]:
                    cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
                    summary = summarize_with_mistral(
                        user_query=user_query,
                        columns=cols_for_llm,
                        rows=rows_for_summary,
                        backend_summary=python_summary,
                        sql=sql,
                    ) if SUMMARY_ENGINE == "llm" else python_summary
                else:
                    summary = ""

                response: Dict[str, Any] = {
                    "status": "success",
                    "sql": sql,
                    "display_mode": display_mode,
                    "results": {
                        "columns": list(rows[0].keys()) if rows else [],
                        "rows": [list(r.values()) for r in rows] if display_mode in ["table", "both"] else [],
                        "row_count": len(rows),
                    },
                    "schema_context": schema_chunks,
                    "summary": summary,
                }

                if display_mode not in ["summary", "both"]:
                    yield {"phase": "Done", "stage": "done"}
                    await asyncio.sleep(0)

                yield response
                return
            else:
                yield {"phase": "No direct hits; switching to LLM...", "stage": "switch_llm"}
                await asyncio.sleep(0)

        # Phase 2: SQL generation
        yield {"phase": "Generating SQL...", "stage": "sql_gen"}
        await asyncio.sleep(0)
        prompt = generate_sql_prompt(schema_chunks, user_query)
        sql = cached_call_ollama(prompt, model=OLLAMA_SQL_MODEL)
        sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
        sql = handle_bind_variables(sql, user_query)
        sql = normalize_dates(sql)
        rng = extract_explicit_date_range(user_query)
        sql = apply_date_range_constraint(sql, rng)
        sql = enforce_raw_table_request(user_query, sql)
        # NEW: remove unrequested time filters
        new_sql = strip_unprompted_time_filters(sql, user_query)
        if new_sql != sql:
            sql = new_sql
            yield {"phase": "Removed unrequested time filter", "stage": "rewrite", "sql": sql}
            await asyncio.sleep(0)
            yield {"phase": "Tip: add a timeframe for a focused report (e.g., 'last month' or '01/07/2025 to 31/07/2025').", "stage": "hint"}
            await asyncio.sleep(0)

        # ✅ Always sanitize after the time-filter step (regardless of change)
        sql = _strip_group_by_with_star(sql)

        yield {"phase": "SQL ready", "stage": "sql_ready", "sql": sql}

        await asyncio.sleep(0)
        logger.info(f"[Generated SQL] {sql}")

        # Phase 3: light validation
        yield {"phase": "Validating SQL...", "stage": "validate"}
        await asyncio.sleep(0)
        if not is_valid_sql(sql, selected_db):
            sql = retry_with_stricter_prompt(user_query, schema_chunks, "initial invalid")
            sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
            sql = handle_bind_variables(sql, user_query)
            sql = normalize_dates(sql)
            rng = extract_explicit_date_range(user_query)
            sql = apply_date_range_constraint(sql, rng)
            sql = enforce_raw_table_request(user_query, sql)
            # NEW: sanitize on retry too
            new_sql = strip_unprompted_time_filters(sql, user_query)
            if new_sql != sql:
                sql = new_sql
                yield {"phase": "Removed unrequested time filter", "stage": "rewrite", "sql": sql}
                await asyncio.sleep(0)

            # ✅ Also sanitize here
            sql = _strip_group_by_with_star(sql)

            yield {"phase": "SQL ready", "stage": "sql_ready", "sql": sql}

            await asyncio.sleep(0)
            if not is_valid_sql(sql, selected_db):
                # NEW: heuristic fallback to a safe table sample
                tbl = extract_main_table(sql) or _guess_table_from_query(user_query, schema_chunks)
                if tbl:
                    fallback = f"SELECT * FROM {tbl} FETCH FIRST 200 ROWS ONLY"
                    if is_valid_sql(fallback, selected_db):
                        sql = fallback
                        yield {"phase": "Validation passed", "stage": "validate_ok"}
                        await asyncio.sleep(0)
                    else:
                        yield {"error": {"error":"INVALID_SQL", "message":"Could not generate valid SQL", "sql": sql}}
                        await asyncio.sleep(0)
                        return
                else:
                    yield {"error": {"error":"INVALID_SQL", "message":"Could not generate valid SQL", "sql": sql}}
                    await asyncio.sleep(0)
                    return

            # retry succeeded:
            yield {"phase": "Validation passed", "stage": "validate_ok"}
            await asyncio.sleep(0)
        else:
            # first attempt was valid:
            yield {"phase": "Validation passed", "stage": "validate_ok"}
            await asyncio.sleep(0)
        # cache hit path before executing
        hit = _cache_get_result(selected_db, sql)
        if hit:
            display_mode = determine_display_mode(user_query, hit["rows"])

            # Stream summary if needed
            if display_mode in ["summary", "both"]:
                yield {"phase": "Generating summary/report...", "stage": "summary_start", "display_mode": display_mode}
                await asyncio.sleep(0)

                snapshot = _pipe_snapshot(
                    hit["columns"],
                    hit["rows"],
                    max_rows=SUMMARY_MAX_ROWS,
                    char_budget=SUMMARY_CHAR_BUDGET
                )

                for piece in stream_summary(user_query, data_snippet=snapshot):
                    try:
                        obj = json.loads(piece)
                    except Exception:
                        obj = {"summary": piece}

                    if "phase" in obj:
                        obj["stage"] = "summary_stream"
                        yield obj
                    elif "summary" in obj:
                        yield {"summary": obj["summary"], "stage": "summary_chunk"}
                        await asyncio.sleep(0)

                yield {"phase": "Summary complete", "stage": "done"}
                await asyncio.sleep(0)
            if display_mode not in ["summary", "both"]:
                yield {"phase": "Done", "stage": "done"}
                await asyncio.sleep(0)

            # Final payload (table rows only if requested)
            response: Dict[str, Any] = {
                "status": "success",
                "sql": sql,
                "display_mode": display_mode,
                "results": {
                    "columns": hit["columns"],
                    "rows": [list(r.values()) for r in hit["rows"]] if display_mode in ["table", "both"] else [],
                    "row_count": hit["row_count"],
                },
                "schema_context": schema_chunks,
                # don't include full summary text here because it was streamed
                "summary": "" if display_mode in ["summary", "both"] else "",
            }


            yield response
            return


        # Phase 4: execution + stream rows (batched)
        yield {"phase": "Executing query...", "stage": "execute", "sql": sql}
        await asyncio.sleep(0)
        with connect_to_source(selected_db) as (conn, _):
            cursor = conn.cursor()
            _set_case_insensitive_session(cursor)
            try:
                cursor.execute(sql)
            except Exception as e:
                repaired = _repair_sql_on_runtime_error(sql, selected_db, str(e))
                if repaired and is_valid_sql(repaired, selected_db):
                    sql = repaired
                    yield {"phase": "Fixing SQL and retrying…", "stage": "rewrite", "sql": sql}
                    await asyncio.sleep(0)
                    cursor = conn.cursor()
                    _set_case_insensitive_session(cursor)
                    cursor.execute(sql)
                else:
                    yield {"error": {"error": "ORACLE_ERROR", "message": str(e), "sql": sql}}
                    await asyncio.sleep(0)
                    return

            col_names = [desc[0] for desc in cursor.description]
            yield {"phase": "Parsing rows...", "stage": "parsing", "columns": col_names, "row_count": 0}
            await asyncio.sleep(0)

            batch_size = 10
            batch: List[Dict[str, Any]] = []
            all_rows: List[Dict[str, Any]] = []
            row_count = 0

            for row in cursor:
                row_dict = {col_names[i]: to_jsonable(row[i]) for i in range(len(col_names))}
                batch.append(row_dict)
                all_rows.append(row_dict)
                row_count += 1

                if len(batch) >= batch_size:
                    yield {
                        "phase": "Parsing rows...",
                        "stage": "parsing",
                        "partial_results": {
                            "rows": [list(r.values()) for r in batch],
                            "row_count": row_count,
                        },
                    }
                    await asyncio.sleep(0)
                    batch = []

            if batch:
                yield {
                    "phase": "Parsing rows...",
                    "stage": "parsing",
                    "partial_results": {
                        "rows": [list(r.values()) for r in batch],
                        "row_count": row_count,
                    },
                }
                await asyncio.sleep(0)
            # --- First empty-results check
            if row_count == 0:
                if user_has_explicit_range:
                    # Return a clean, truthful payload; no sampling
                    yield {
                        "status": "success",
                        "sql": sql,
                        "display_mode": determine_display_mode(user_query, []),
                        "results": {"columns": col_names, "rows": [], "row_count": 0},
                        "schema_context": schema_chunks,
                        "summary": "No data found for the requested date range.",
                    }
                    await asyncio.sleep(0)
                    return

                ci_sql = _case_insensitive_rewrite(sql)
                if ci_sql != sql and is_valid_sql(ci_sql, selected_db):
                    yield {"phase": "No rows; retrying with case-insensitive match..."}
                    await asyncio.sleep(0)
                    cursor2 = conn.cursor()
                    _set_case_insensitive_session(cursor2)
                    cursor2.execute(ci_sql)

                    col_names = [desc[0] for desc in cursor2.description]
                    yield {"phase": "Parsing rows...", "stage": "parsing", "columns": col_names, "row_count": 0}
                    await asyncio.sleep(0)

                    batch, all_rows, row_count = [], [], 0
                    for row in cursor2:
                        row_dict = {col_names[i]: to_jsonable(row[i]) for i in range(len(col_names))}
                        batch.append(row_dict)
                        all_rows.append(row_dict)
                        row_count += 1
                        if len(batch) >= batch_size:
                            yield {
                                "phase": "Parsing rows...",
                                "stage": "parsing",
                                "partial_results": {"rows": [list(r.values()) for r in batch], "row_count": row_count},
                            }
                            await asyncio.sleep(0)
                            batch = []
                    if batch:
                        yield {
                            "phase": "Parsing rows...",
                            "stage": "parsing",
                            "partial_results": {"rows": [list(r.values()) for r in batch], "row_count": row_count},
                        }
                        await asyncio.sleep(0)

                    sql = ci_sql

                    # If still zero and the user gave an explicit range, stop (no sampling)
                    if row_count == 0 and user_has_explicit_range:
                        yield {
                            "status": "success",
                            "sql": sql,
                            "display_mode": determine_display_mode(user_query, []),
                            "results": {"columns": col_names, "rows": [], "row_count": 0},
                            "schema_context": schema_chunks,
                            "summary": "No data found for the requested date range.",
                        }
                        await asyncio.sleep(0)
                        return

                # 🔧 FINAL FALLBACK NOW RUNS OUTSIDE THE CI BRANCH
                if row_count == 0 and not user_has_explicit_range:
                    main_table = extract_main_table(sql or "")
                    if main_table:
                        try:
                            yield {"phase": f"No rows; showing sample from {main_table}..."}
                            await asyncio.sleep(0)
                            sample_sql = f"SELECT * FROM {main_table} FETCH FIRST 200 ROWS ONLY"
                            cursor3 = conn.cursor()
                            _set_case_insensitive_session(cursor3)
                            cursor3.execute(sample_sql)
                            col_names = [d[0] for d in cursor3.description]
                            all_rows, row_count = [], 0
                            for r in cursor3:
                                all_rows.append({col_names[i]: to_jsonable(r[i]) for i in range(len(col_names))})
                                row_count += 1

                            if row_count > 0:
                                sql = sample_sql
                                display_mode = determine_display_mode(user_query, all_rows)
                                rows_for_summary = widen_results_if_needed(all_rows, sql, selected_db, display_mode)
                                python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary","both"] else ""
                                if display_mode in ["summary", "both"]:
                                    cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
                                    summary = summarize_with_mistral(
                                        user_query=user_query,
                                        columns=cols_for_llm,
                                        rows=rows_for_summary,
                                        backend_summary=python_summary,
                                        sql=sql,
                                    ) if SUMMARY_ENGINE == "llm" else python_summary
                                else:
                                    summary = ""

                                response = {
                                    "status": "success",
                                    "sql": sql,
                                    "display_mode": display_mode,
                                    "results": {"columns": col_names, "rows": [list(r.values()) for r in all_rows], "row_count": row_count},
                                    "summary": summary,
                                    "schema_context": schema_chunks,
                                }
                                _cache_set_result(selected_db, sql, col_names, all_rows)
                                if display_mode not in ["summary", "both"]:
                                    yield {"phase": "Done", "stage": "done"}
                                    await asyncio.sleep(0)

                                yield response
                                return

                        except Exception as e:
                            logger.warning(f"Sample fallback failed for {main_table}: {e}")

                # Still nothing after all fallbacks
                if row_count == 0:
                    yield {"error": {"error": "NO_RESULTS", "message": "No results found"}}
                    await asyncio.sleep(0)
                    return

            # store in cache
            _cache_set_result(selected_db, sql, col_names, all_rows)

            display_mode = determine_display_mode(user_query, all_rows)

            # Stream summary if needed
            if display_mode in ["summary", "both"]:
                yield {"phase": "Generating summary/report...", "stage": "summary_start", "display_mode": display_mode}
                await asyncio.sleep(0)
                snapshot = _pipe_snapshot(
                    col_names,
                    all_rows,
                    max_rows=SUMMARY_MAX_ROWS,
                    char_budget=SUMMARY_CHAR_BUDGET
                )

                for piece in stream_summary(user_query, data_snippet=snapshot):
                    try:
                        obj = json.loads(piece)
                    except Exception:
                        obj = {"summary": piece}

                    if "phase" in obj:
                        obj["stage"] = "summary_stream"
                        yield obj
                    elif "summary" in obj:
                        yield {"summary": obj["summary"], "stage": "summary_chunk"}
                        await asyncio.sleep(0)

                yield {"phase": "Summary complete", "stage": "done"}
                await asyncio.sleep(0)
            else:
                # Table-only → finish the status pipeline cleanly
                yield {"phase": "Done", "stage": "done"}
                await asyncio.sleep(0)

            response: Dict[str, Any] = {
                "status": "success",
                "sql": sql,
                "display_mode": display_mode,
                "results": {
                    "columns": col_names,
                    "row_count": row_count,
                },
                "schema_context": schema_chunks,
            }

            # summary was streamed; keep the field empty in the final envelope
            response["summary"] = ""


            if display_mode in ["table", "both"]:
                response["results"]["rows"] = [list(r.values()) for r in all_rows]

            yield response

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}\n{traceback.format_exc()}")
        yield {
            "error": {
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": str(e),
            }
        }
        await asyncio.sleep(0)
