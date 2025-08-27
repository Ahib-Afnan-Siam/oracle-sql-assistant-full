# app/rag_engine.py
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime as _dt
import os
from app.query_engine import _MONTH_ALIASES  # add this
from app.vector_store_chroma import hybrid_schema_value_search
from app.db_connector import connect_to_source
from app.ollama_llm import ask_sql_planner
from app.config import SUMMARY_ENGINE
from app.query_engine import _get_table_colmeta
from functools import lru_cache

# Reuse the deterministic SQL toolbox + summarizer you already have
from app.query_engine import (
    build_sql_from_plan,
    normalize_dates,
    enforce_wide_projection_for_generic,
    value_aware_text_filter,
    enforce_predicate_type_compat,
    is_valid_sql,
    run_sql,
    determine_display_mode,
    widen_results_if_needed,
    summarize_results,
    ensure_label_filter,
    extract_explicit_date_range,
    # Entity-lookup fast path (importing "private" helpers is acceptable inside the app)
    _is_entity_lookup,
    _needle_from_question,
    _candidate_columns,
    _list_name_like_columns,
    _merge_candidates,
    _quick_value_probe,
    _is_banned_table,
    _filter_banned_tables,
    _extract_id_lookup,
    _list_id_like_columns,
    _set_case_insensitive_session,
)

from app.summarizer import summarize_with_mistral

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Local parser for TO_CHAR dims used in validation (aligns with query_engine)
_TOCHAR_WHITELIST = {"MON-YY", "MON-YYYY", "YYYY-MM", "YYYY", "DD-MON-YYYY"}
_TOCHAR_RX = re.compile(
    r"""(?is)^\s*TO_CHAR\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*'([A-Za-z\-]+)'\s*\)\s*$"""
)

# Prefer daily-granularity tables when the question mentions a specific day
_DAILY_HINT_RX = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|"          # 2025-08-21
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|"  # 21/08/25 or 21-08-2025
    r"\b\d{2}-[A-Za-z]{3}-\d{2,4}\b|"  # 21-AUG-25 / 21-AUG-2025
    r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}\b|" # 21 Aug 2025
    r"\bday\b",
    re.IGNORECASE,
)

def _bias_tables_for_day(tables: List[str], user_query: str) -> List[str]:
    if not tables:
        return tables
    if not _DAILY_HINT_RX.search(user_query or ""):
        return tables

    def score(t: str) -> tuple[int, str]:
        T = t.upper()
        # very simple daily-ish signal: *_DAILY, *_DLY, *_DAY
        dailyish = bool(re.search(r"(?:^|_)(DAILY|DLY|DAY)(?:$|_)", T))
        return (0 if dailyish else 1, T)   # daily tables first, then alpha for determinism

    return sorted(tables, key=score)

# ---- Multi-metric, schema-driven selection -----------------------------------
_METRIC_WORDS_RX = re.compile(
    r"\b(qty|quantity|pcs?|pieces?|rate|percent|pct|eff|efficiency|score|dhu|"
    r"defect|reject(?:ion|ed)?|rework|alter|stain|dirty|spot|hole|skip)\b", re.I
)

def _extract_metric_phrases(uq: str, max_parts: int = 8) -> list[str]:
    parts = re.split(r"\b(?:and|&|,|plus|with|as well as)\b", uq or "", flags=re.I)
    out = []
    for p in parts:
        p = p.strip()
        if p and _METRIC_WORDS_RX.search(p):
            out.append(p)
    return out[:max_parts]

def _score_metric_col(col: str, phrase: str) -> int:
    c = col.lower(); p = phrase.lower()
    score = 0
    # token overlap
    for t in re.findall(r"[a-z0-9]+", p):
        if t and t in c: score += 3
    # universal boosts
    if "qty" in p or "pcs" in p or "piece" in p:
        if "qty" in c or "pcs" in c: score += 5
    if "eff" in p or "efficiency" in p or "rate" in p or "percent" in p or "pct" in p:
        if "eff" in c or "rate" in c or "pct" in c or "percent" in c: score += 5
    if "dhu" in p and "dhu" in c: score += 8
    if ("defect" in p or "reject" in p) and ("defect" in c or "rej" in c): score += 4
    if ("stain" in p or "dirty" in p) and ("stain" in c or "dirty" in c): score += 6
    return score

def _choose_metrics_for_phrases(phrases: list[str], table: str, options: dict,
                                max_metrics: int = 8) -> list[str]:
    numeric_cols = list(options.get("numeric_columns", {}).get(table, []) or [])
    chosen: list[str] = []
    for ph in phrases:
        best = None; best_s = -1
        for col in numeric_cols:
            s = _score_metric_col(col, ph)
            if s > best_s:
                best, best_s = col, s
        if best_s > 0 and best not in chosen:
            chosen.append(best)
    return chosen[:max_metrics]

def _augment_plan_with_metrics(uq: str, plan: dict, options: dict) -> dict:
    if not isinstance(plan, dict):
        return plan

    is_two_table = bool(plan.get("tables") and plan.get("joins"))
    base = plan.get("table") if not is_two_table else (plan.get("tables") or [None])[0]
    if not base:
        return plan

    phrases = _extract_metric_phrases(uq)
    if not phrases:
        return plan

    picks = _choose_metrics_for_phrases(phrases, base, options)

    # Only consider switching tables on SINGLE-TABLE plans
    if not picks and not is_two_table:
        best = (0, None, [])
        for t in options.get("tables", []):
            cols = _choose_metrics_for_phrases(phrases, t, options)
            if len(cols) > best[0]:
                best = (len(cols), t, cols)
        if best[1]:
            plan["table"] = best[1]
            picks = best[2]

    if picks:
        plan["metrics"] = list(dict.fromkeys((plan.get("metrics") or []) + picks))[:8]
        if "limit" in plan and not re.search(r"\b(top\s*\d+|top|max|min|highest|lowest|first|last)\b", uq or "", re.I):
            plan.pop("limit", None)

    return plan


# app/rag_engine.py (add near other helpers)
_DAILY_NAME_RX = re.compile(r'(?:^|_)(DAILY|DLY|DAY)(?:$|_)', re.I)

# --- T_PROD vs T_PROD_DAILY cutoff rule (only for source_db_1) ----------------
_CUTOFF_DT = _dt(2025, 1, 15)
_METRIC_HINT_RX = re.compile(
    r"\b(defect|rej(?:ect|ection|n)?|prod(?:uction)?(?:\s*qty)?|production|qty|pieces?|pcs?|output)\b",
    re.I,
)

# Minimal date parsing helpers used to detect the asked window
_MON_ABBR = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
)}

def _parse_day_token(s: str) -> Optional[_dt]:
    s = s.strip()
    # 2025-08-20
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return _dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # 20-AUG-2025 or 20-AUG-25
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$", s)
    if m:
        d, mon3, y = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, _MON_ABBR.get(mon3, 1), d)
    # 20/08/2025 or 20/08/25
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", s)
    if m:
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, mth, d)
    # 20 Aug 2025 / 20 Aug 25
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})$", s)
    if m:
        d, mon3, y = int(m.group(1)), m.group(2).upper(), int(m.group(3))
        y = 2000 + y if y < 100 else y
        return _dt(y, _MON_ABBR.get(mon3, 1), d)
    return None

def _asked_range(uq: str) -> tuple[Optional[_dt], Optional[_dt]]:
    """
    Extract date range from user query.
    Returns (start_date, end_date) or (None, None) if no dates found.
    """
    # Try to find date tokens in the query
    day_tokens = re.findall(
        r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
        uq or "", re.IGNORECASE
    )
    
    parsed_days = []
    for token in day_tokens:
        dt = _parse_day_token(token)
        if dt:
            parsed_days.append(dt)
    
    if len(parsed_days) == 1:
        return (parsed_days[0], parsed_days[0])
    elif len(parsed_days) >= 2:
        return (min(parsed_days), max(parsed_days))
    
    return (None, None)

# -------------------------
# Enhanced Entity Recognition (Integrated from enhanced_entity_recognizer.py)
# -------------------------

def extract_enhanced_companies(query: str) -> List[Dict[str, str]]:
    """Extract company references from query."""
    company_mappings = {
        'CAL': {
            'full_name': 'Chorka Apparel Limited',
            'variations': ['cal', 'CAL', 'chorka', 'Chorka'],
            'floor_patterns': [r'CAL.*?Sewing-F\d+', r'Sewing.*?CAL-\d+[A-Z]?']
        },
        'WINNER': {
            'full_name': 'Winner',
            'variations': ['winner', 'Winner', 'WINNER'],
            'floor_patterns': [r'Winner.*?BIP.*?sewing', r'Sewing.*?Winner-\d+']
        },
        'BIP': {
            'full_name': 'BIP',
            'variations': ['bip', 'BIP'],
            'floor_patterns': [r'Winner.*?BIP']
        }
    }
    
    companies = []
    query_lower = query.lower()
    
    for company_code, company_info in company_mappings.items():
        for variation in company_info['variations']:
            if variation.lower() in query_lower:
                companies.append({
                    'code': company_code,
                    'full_name': company_info['full_name'],
                    'variation_found': variation
                })
                break
    
    return companies

def extract_enhanced_floors(query: str) -> List[Dict[str, str]]:
    """Extract floor references from query."""
    floor_patterns = {
        'sewing_floors': [
            r'Sewing\s+Floor-\d+[A-Z]?',  # Sewing Floor-5B
            r'Sewing\s+CAL-\d+[A-Z]?',    # Sewing CAL-2A
            r'CAL\s+Sewing-F\d+',         # CAL Sewing-F1
            r'Winner.*?BIP.*?sewing',      # Winner BIP sewing
            r'Sewing\s+Winner-\d+',       # Sewing Winner-1
        ],
        'cutting_floors': [
            r'Cutting\s+Floor-\d+[A-Z]?',
            r'Cutting\s+CAL-\d+[A-Z]?'
        ],
        'finishing_floors': [
            r'Finishing\s+Floor-\d+[A-Z]?'
        ]
    }
    
    floors = []
    
    for floor_type, patterns in floor_patterns.items():
        for pattern in patterns:
            matches = re.finditer(pattern, query, re.IGNORECASE)
            for match in matches:
                floors.append({
                    'type': floor_type.replace('_floors', ''),
                    'name': match.group(0),
                    'pattern_matched': pattern
                })
    
    return floors

def extract_enhanced_metrics(query: str) -> List[str]:
    """Extract metric-related terms from query."""
    metric_patterns = [
        r'\bproduction\s+qty\b',
        r'\bdefect\s+qty\b',
        r'\bDHU\b',
        r'\btotal\s+production\b',
        r'\bmax\s+defect\b',
        r'\bsalary\b',
        r'\bstock\b',
        r'\bon[-\s]?hand\s+qty\b'
    ]
    
    metrics = []
    for pattern in metric_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            metrics.append(pattern.strip(r'\b'))
    
    return metrics

def classify_enhanced_query_intent(query: str) -> str:
    """Enhanced query intent classification based on user patterns."""
    query_lower = query.lower()
    
    # Enhanced intent patterns
    intent_patterns = {
        'floor_production_summary': [r'floor.*wise.*production.*summary', r'show.*floor.*production'],
        'defect_analysis': [r'defect.*qty.*floor', r'max.*defect.*qty', r'total.*defect.*qty'],
        'employee_lookup': [r'who\s+is\s+\w+', r'salary.*president'],
        'ranking_query': [
            r'top.*\d+.*defect', r'max.*defect.*floor', r'biggest.*production',
            r'which.*floor.*produced.*most', r'which.*floor.*most.*production',
            r'most.*production.*floor', r'floor.*produced.*most',
            r'maximum.*production', r'highest.*production'
        ]
    }
    
    for intent, patterns in intent_patterns.items():
        if any(re.search(pattern, query_lower) for pattern in patterns):
            return intent
    
    if any(word in query_lower for word in ['production', 'defect', 'floor']):
        return 'production_data'
    elif any(word in query_lower for word in ['employee', 'salary', 'president']):
        return 'employee_data'
    elif any(word in query_lower for word in ['stock', 'inventory', 'item', 'product']):
        return 'inventory_data'
    
    return 'general'

def analyze_enhanced_query(query: str) -> Dict:
    """Comprehensive enhanced query analysis."""
    
    analysis = {
        'companies': extract_enhanced_companies(query),
        'floors': extract_enhanced_floors(query),
        'metrics': extract_enhanced_metrics(query),
        'intent': classify_enhanced_query_intent(query),
        'query_type': classify_enhanced_query_intent(query)
    }
    
    return analysis

def _asked_range(uq: str) -> tuple[Optional[_dt], Optional[_dt]]:
    """
    Extract date range from user query.
    Returns (start_date, end_date) or (None, None) if no dates found.
    """
    # 1) explicit range via query_engine (e.g., "between 01/01/2025 and 05/01/2025")
    rng = extract_explicit_date_range(uq or "")
    if rng and rng.get("start") and rng.get("end"):
        # pull literal out of TO_DATE('LIT','FMT')
        def _to_dt(to_date_expr: str) -> Optional[_dt]:
            m = re.search(r"TO_DATE\('([^']+)','([^']+)'\)", to_date_expr, re.I)
            if not m: 
                return None
            lit, fmt = m.group(1), (m.group(2) or "").upper()
            fmt_map = {
                "DD-MON-YYYY": "%d-%b-%Y", "DD-MON-YY": "%d-%b-%y",
                "YYYY-MM-DD": "%Y-%m-%d",
                "DD/MM/YYYY": "%d/%m/%Y", "DD/MM/YY": "%d/%m/%y",
                "MON-YYYY": "%b-%Y", "MON-YY": "%b-%y",
            }
            py = fmt_map.get(fmt)
            if not py: 
                return None
            try:
                return _dt.strptime(lit, py)
            except Exception:
                return None
        sdt = _to_dt(rng["start"]); edt = _to_dt(rng["end"])
        return (sdt, edt)

    # 2) single-day literals in the question
    m = re.search(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
        uq or "", re.I
    )
    if m:
        dt = _parse_day_token(m.group(1))
        if dt:
            return (dt, dt)

    # 3) month token like "Aug-2025" or "Aug 2025"
    m = re.search(r"\b([A-Za-z]{3,9})[-\s](\d{2,4})\b", uq or "", re.I)
    if m:
        mon_word, yy = m.group(1), m.group(2)
        mon3 = (_MONTH_ALIASES.get(mon_word.strip().upper())
                or mon_word[:3].upper())
        if mon3 in _MON_ABBR:
            from calendar import monthrange as _mr
            y = int(yy); y = 2000 + y if y < 100 else y
            start = _dt(y, _MON_ABBR[mon3], 1)
            end = _dt(y, _MON_ABBR[mon3], _mr(y, _MON_ABBR[mon3])[1])
            return (start, end)
    return (None, None)

@lru_cache(maxsize=128)
def _table_exists(selected_db: str, name: str) -> bool:
    try:
        with connect_to_source(selected_db) as (conn, _):
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1 FROM user_tables WHERE table_name = :t", t=name.upper())
                return cur.fetchone() is not None
            finally:
                try: cur.close()
                except: pass
    except Exception:
        return False


def _maybe_force_tprod_tables(uq: str, selected_db: str, candidates: list[str]) -> list[str]:
    """
    For source_db_1 'production/defect qty' style questions with a concrete asked window,
    constrain candidate tables strictly to T_PROD or T_PROD_DAILY so the planner cannot
    wander to similarly named daily tables with sparse data.
    """
    candidates = candidates or []
    if selected_db != "source_db_1":
        return candidates

    mentions_tables = bool(re.search(r"\bT_PROD(?:_DAILY)?\b", uq or "", re.I))
    mentions_kpi    = bool(_METRIC_HINT_RX.search(uq or ""))
    if not (mentions_tables or mentions_kpi):
        return candidates

    start_dt, end_dt = _asked_range(uq or "")
    if not (start_dt and end_dt):
        return candidates

    # decide which table to force
    forced = None
    if end_dt < _CUTOFF_DT:
        forced = "T_PROD"
    elif start_dt >= _CUTOFF_DT:
        forced = "T_PROD_DAILY"
    else:
        # straddles cutoff → don’t force
        return candidates

    if not _table_exists(selected_db, forced):
        return candidates

    if forced == "T_PROD" and _table_exists(selected_db, "T_PROD"):
        logger.info("[RAG] Forced table by cutoff rule → T_PROD (strict)")
        return ["T_PROD"]
    if forced == "T_PROD_DAILY" and _table_exists(selected_db, "T_PROD_DAILY"):
        logger.info("[RAG] Forced table by cutoff rule → T_PROD_DAILY (strict)")
        return ["T_PROD_DAILY"]
    return candidates

@lru_cache(maxsize=64)
def _discover_dailyish_tables(selected_db: str, limit: int = 6,
                              must_have_cols: tuple[str,...] = ('PRODUCTION_QTY',)) -> list[str]:
    sql = f"""
    SELECT ut.table_name
      FROM user_tables ut
     WHERE REGEXP_LIKE(ut.table_name, '(DAILY|DLY|_DAY)', 'i')
       AND NOT REGEXP_LIKE(ut.table_name, '(^|_)AI_', 'i')
       AND { " AND ".join([f"EXISTS (SELECT 1 FROM user_tab_columns c WHERE c.table_name = ut.table_name AND UPPER(c.column_name) = '{col}')" for col in must_have_cols]) }
     ORDER BY ut.table_name
     FETCH FIRST :lim ROWS ONLY
    """
    out = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        cur.execute(sql, lim=limit)
        out = [r[0] for r in cur.fetchall()]
    return out

# ---------------------------
# Retrieval
# ---------------------------

def _search_schema(user_query: str, selected_db: str, top_k: int = 12) -> List[Dict[str, Any]]:
    """Wrap Chroma hybrid search."""
    try:
        return hybrid_schema_value_search(user_query, selected_db=selected_db, top_k=top_k) or []
    except Exception as e:
        logger.warning(f"[RAG] Schema search failed: {e}")
        return []


def _extract_context_ids(results: List[Dict[str, Any]]) -> List[str]:
    """Stable-ish IDs for observability/debugging."""
    out: List[str] = []
    seen = set()
    for r in results or []:
        md = (r or {}).get("metadata", {}) or {}
        candidates = [
            r.get("id"),
            md.get("id"),
            md.get("chunk_id"),
            md.get("doc_id"),
            md.get("source_id"),
            md.get("collection_id"),
            md.get("table"),
            md.get("source_table"),
            md.get("file"),
            md.get("path"),
            md.get("source"),
        ]
        rid = next((c for c in candidates if c), None)
        if not rid:
            continue
        s = str(rid)
        if s not in seen:
            seen.add(s)
            out.append(s)
        if len(out) >= 50:
            break
    return out


def _tables_from_results(results: List[Dict[str, Any]]) -> List[str]:
    """Prefer table names from metadata; dedup while preserving order."""
    seen = set()
    out: List[str] = []
    for r in results or []:
        t = ((r or {}).get("metadata") or {}).get("source_table")
        if not t:
            continue
        u = str(t).upper()
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= 12:
            break
    return out


# ---------------------------
# Live metadata → runtime options
# ---------------------------
@lru_cache(maxsize=256)
def _fk_edges(selected_db: str, tables_key: tuple) -> List[Dict[str, str]]:
    """
    Build FK join edges among the provided tables using live metadata.
    Cached by (selected_db, tuple_of_tables).
    Returns edges like {"left":"CHILD.COL", "right":"PARENT.COL", "type":"INNER"}.
    """
    tables = list(tables_key)
    if not tables:
        return []
    placeholders = ",".join([f":t{i}" for i in range(len(tables))])
    qs = f"""
    SELECT ac.table_name child_table, acc.column_name child_col,
           pk.table_name parent_table, acc_pk.column_name parent_col
      FROM all_constraints ac
      JOIN all_cons_columns acc
        ON acc.owner = ac.owner AND acc.constraint_name = ac.constraint_name
      JOIN all_constraints pk
        ON pk.owner = ac.r_owner AND pk.constraint_name = ac.r_constraint_name
      JOIN all_cons_columns acc_pk
        ON acc_pk.owner = pk.owner AND acc_pk.constraint_name = pk.constraint_name AND acc_pk.position = acc.position
     WHERE ac.constraint_type = 'R'
       AND ac.owner = USER
       AND ac.table_name IN ({placeholders})
       AND pk.table_name IN ({placeholders})
    """
    edges: List[Dict[str, str]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        params = {f"t{i}": t for i, t in enumerate(tables)}
        try:
            cur.execute(qs, {**params, **params})
            for child_t, child_c, parent_t, parent_c in cur.fetchall():
                edges.append({
                    "left": f"{str(child_t).upper()}.{str(child_c).upper()}",
                    "right": f"{str(parent_t).upper()}.{str(parent_c).upper()}",
                    "type": "INNER",
                })
        except Exception as e:
            logger.warning(f"[RAG] FK edge discovery failed: {e}")
        finally:
            try: cur.close()
            except Exception: pass
    return edges



def _build_runtime_options(selected_db: str, tables: List[str],
                           limit_tables: int = 6, limit_cols: int = 60) -> Dict[str, Any]:
    """
    Build dynamic options strictly from live Oracle metadata for a *small* set of tables.
    Keeping this tight is what tends to make the planner accurate.
    """
    picked = _filter_banned_tables((tables or [])[:limit_tables])
    columns: Dict[str, List[Dict[str, str]]] = {}
    date_cols: Dict[str, List[str]] = {}
    num_cols: Dict[str, List[str]] = {}
    txt_cols: Dict[str, List[str]] = {}

    for t in picked:
        meta = _get_table_colmeta(selected_db, t)
        if not meta:
            continue

        # sorted by column name for determinism
        items = sorted(meta.items(), key=lambda kv: kv[0])

        # Per-type pools
        d = [c for c, dt in items if ("DATE" in dt) or ("TIMESTAMP" in dt)]
        n = [c for c, dt in items if any(k in dt for k in ("NUMBER", "FLOAT", "INTEGER", "BINARY"))]
        x = [c for c, dt in items if any(k in dt for k in ("CHAR", "VARCHAR", "NCHAR", "CLOB"))]

        date_cols[t] = d
        num_cols[t] = n
        txt_cols[t] = x

        columns[t] = [{"name": c, "type": dt} for c, dt in items[:limit_cols]]

    joins = _fk_edges(selected_db, tuple(t for t in picked if t in columns))


    return {
        "tables": [t for t in picked if t in columns],  # keep only tables that resolved to columns
        "columns": columns,
        "date_columns": date_cols,
        "numeric_columns": num_cols,
        "text_columns": txt_cols,
        "joins": joins,   # NEW: allowed join edges discovered from FKs
    }


# ---------------------------
# Planner
# ---------------------------

def _planner_prompt(user_query: str, options: Dict[str, Any]) -> str:
    """
    Planner prompt that returns JSON only. It now supports:
    - order_by, limit
    - optional 2-table join (restricted to OPTIONS.joins)
    - TO_CHAR(<date_col>,'MON-YY'|'MON-YYYY') dims via {"expr": "...", "as": "..."}
    """
    return f"""
You are a SQL planning assistant. Choose only from the provided tables, columns, and joins.
Do NOT invent names. Return ONLY valid JSON, no preface, no trailing text.

USER QUESTION:
{user_query}

OPTIONS (from live Oracle metadata):
{json.dumps(options, indent=2)}

Return JSON with one of these schemas:

1) Single-table plan
{{
  "table": "<one table from options.tables>",
  "dims": ["<0..2 column names>", {{ "expr": "TO_CHAR(<date_col>,'MON-YY')", "as": "MONTH" }}],
  "metrics": ["<0..3 numeric columns>"],
  "date_col": "<optional: one from options.date_columns[table]>",
  "filters": [{{"col":"<col>","op":"="|"LIKE"|"IN"|">="|"<="|">"|"<","val":<value>}}],
  "order_by": [{{"key":"<metric_or_dim_or_alias>","dir":"DESC|ASC"}}],
  "limit": <integer 1..500>
}}

2) Two-table plan (only if necessary, and only using OPTIONS.joins; at most two tables)
{{
  "tables": ["<t1>","<t2>"],
  "joins": [{{"left":"T1.COL","right":"T2.COL","type":"INNER"}}],
  "dims": ["<0..2 column names from the FIRST table only>", {{ "expr": "TO_CHAR(<date_col>,'MON-YY')", "as":"MONTH" }}],
  "metrics": ["<0..3 numeric columns from the FIRST table only>"],
  "date_col": "<optional date col from the FIRST table>",
  "filters": [{{"col":"<col from EITHER table>","op":"="|"LIKE"|...,"val":<value>}}],
  "order_by": [{{"key":"<metric_or_dim_or_alias>","dir":"DESC|ASC"}}],
  "limit": <integer 1..500>
}}

Rules:
- If the user asks for monthly rollups or a format like MON-YY/MON-YYYY, include a TO_CHAR(<date_col>,'MON-YY'|'MON-YYYY') dimension with alias "MONTH".
- If the user asks for "max", "top N", or "just one row", set order_by on the primary metric DESC and set limit accordingly.
- Prefer a single-table plan unless a join is clearly needed. If joining, you MUST use only a join present in OPTIONS.joins and only two tables.
- Use only columns present in OPTIONS.columns for the chosen table(s). Never invent names.
- If you are certain of the full SELECT, you MAY return {{ "sql": "<SELECT ...>" }} instead of a plan.
- If nothing matches the question, return {{ "decision": "fallback" }}.
- Never add a date/time filter unless the user explicitly mentions a date, month, year, or a relative window (e.g., "last month", "May 2024", "2024", "24/05/2024").
- If the user doesn't specify time, do NOT filter by date. You may include a TO_CHAR(<date_col>, ...) dimension for grouping if asked, but no WHERE on dates.
- Do NOT echo or copy OPTIONS back. If unsure, return {{ "decision":"fallback" }} only.
- If the user requests a time window, do not add equality/LIKE predicates on any other date columns (e.g., LAST_UPDATE = '...'). Use only the range on the chosen date column.
""".strip()


def _extract_first_json(text: str) -> Optional[dict]:
    """Tolerant JSON sniffer: accepts exact or first {...} block."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ask_planner(user_query: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call the planner LLM and parse JSON."""
    try:
        prompt = _planner_prompt(user_query, options)
        raw = ask_sql_planner(prompt)
        plan = _extract_first_json((raw or "").strip().strip("`"))
        logger.debug("[RAG] planner_raw=%s", (raw or "")[:1000])
        logger.debug("[RAG] planner_json=%s", plan)
        return plan
    except Exception as e:
        logger.warning(f"[Planner] failed: {e}")
        return None


def _validate_tochar_dim(dim_obj: dict, table: str, options: Dict[str, Any]) -> bool:
    """Allow dims with TO_CHAR(<date_col>,'FMT') AS <alias>."""
    expr = (dim_obj or {}).get("expr", "")
    m = _TOCHAR_RX.match(expr or "")
    if not m:
        return False
    col, fmt = m.group(1), (m.group(2) or "").upper()
    if fmt not in _TOCHAR_WHITELIST:
        return False
    # must be a real date/timestamp column of the base table
    date_cols = set(options.get("date_columns", {}).get(table, []))
    return col in date_cols


def _validate_plan(plan: Dict[str, Any], options: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Strict plan validator. Every identifier must exist in options.
    Supports either:
      - single-table {"table": ...}
      - two-table {"tables": [t1, t2], "joins": [...]} with joins restricted to options["joins"].

    Relaxed rule: filters may reference columns (or TO_CHAR of date columns) from either side
    of the join. Dimensions, metrics, and date_col remain restricted to the FIRST table.
    """
    if not plan or not isinstance(plan, dict):
        return False, "no plan"

    if plan.get("decision") == "fallback":
        return False, "fallback"

    # If planner returned raw SQL in 'sql'/'query', that's OK — caller will validate it later.
    if isinstance(plan.get("sql") or plan.get("query"), str):
        return True, None

    tables_opt = options.get("tables") or []
    cols_by_tbl = {tbl: {c["name"] for c in options.get("columns", {}).get(tbl, [])} for tbl in tables_opt}
    nums_by_tbl = {tbl: set(options.get("numeric_columns", {}).get(tbl, [])) for tbl in tables_opt}
    dates_by_tbl = {tbl: set(options.get("date_columns", {}).get(tbl, [])) for tbl in tables_opt}
    allowed_joins = options.get("joins") or []

    # Accept either "table" or "tables"+"joins"
    t = plan.get("table")
    tables = plan.get("tables") or []
    joins = plan.get("joins") or []

    use_two_tables = bool(tables and joins)
    base_table: Optional[str] = None

    if use_two_tables:
        if len(tables) > 2:
            return False, "too many tables"
        for tt in tables:
            if tt not in tables_opt:
                return False, "invalid table in join"

        # joins must be subset of allowed_joins (match left/right/type; allow either direction)
        edge_set = {(e["left"], e["right"], (e.get("type") or "INNER").upper()) for e in allowed_joins}
        for j in joins:
            left = (j.get("left") or "").upper()
            right = (j.get("right") or "").upper()
            jtype = (j.get("type") or "INNER").upper()
            if (left, right, jtype) not in edge_set and (right, left, jtype) not in edge_set:
                return False, "invalid join edge"
        base_table = tables[0]  # dims/metrics/date_col restricted to FIRST table
    else:
        if not t or t not in tables_opt:
            return False, "invalid table"
        base_table = t

    # Determine second_table for relaxed filter validation
    second_table = tables[1] if use_two_tables and len(tables) == 2 else None

    dims = plan.get("dims") or []
    metrics = plan.get("metrics") or []
    date_col = plan.get("date_col", None)
    filters = plan.get("filters") or []

    # ---- Dimensions: only columns of the base table or TO_CHAR(<date_col>,'FMT') ----
    for d in dims:
        if isinstance(d, str):
            if d in cols_by_tbl[base_table]:
                continue
            # allow a bare TO_CHAR(...) string as a dim
            m = _TOCHAR_RX.match(d or "")
            if m:
                dcol, fmt = m.group(1), (m.group(2) or "").upper()
                if fmt in _TOCHAR_WHITELIST and dcol in dates_by_tbl[base_table]:
                    continue
            return False, "invalid dim"
        elif isinstance(d, dict):
            if not _validate_tochar_dim(d, base_table, options):
                return False, "invalid tochar dim"
        else:
            return False, "invalid dim type"

    # ---- Metrics must be numeric columns of the base table (validate even if no dims) ----
    for mcol in metrics:
        if mcol not in nums_by_tbl[base_table]:
            return False, "invalid metric"

    # ---- date_col, if present, must be a date/timestamp column of the base table ----
    if date_col is not None and date_col not in dates_by_tbl[base_table]:
        return False, "invalid date_col"

    # ---- Filters: allow plain cols or TO_CHAR(<date_col>,'FMT')
    #               (now from either base_table OR second_table if present) ----
    ALLOWED_OPS = {"=", "LIKE", "IN", ">=", "<=", ">", "<", "BETWEEN"}
    for f in filters:
        c = f.get("col")
        op = f.get("op")
        if op not in ALLOWED_OPS:
            return False, "invalid op"
        if op == "BETWEEN" and not (isinstance(f.get("val"), list) and len(f["val"]) == 2):
            return False, "invalid op"
        
        okcol = False
        if isinstance(c, str):
            # plain column on base or second table
            if c in cols_by_tbl.get(base_table, set()):
                okcol = True
            elif second_table and c in cols_by_tbl.get(second_table, set()):
                okcol = True
            else:
                # TO_CHAR(date_col,'FMT') allowed from either table's date columns
                m = _TOCHAR_RX.match(c or "")
                if m:
                    dcol, fmt = m.group(1), (m.group(2) or "").upper()
                    if fmt in _TOCHAR_WHITELIST and (
                        dcol in dates_by_tbl.get(base_table, set())
                        or (second_table and dcol in dates_by_tbl.get(second_table, set()))
                    ):
                        okcol = True

        if not okcol:
            return False, "invalid filter content"

    # order_by/limit are optional; keys are checked later by the SQL builder
    return True, None

# ---------------------------
# Fallback: entity lookup
# ---------------------------
def _entity_lookup_path(user_query: str, selected_db: str,
                        schema_chunks: List[str],
                        schema_context_ids: List[str]) -> Dict[str, Any]:
    """
    Try to resolve queries like IDs, codes, job numbers, barcodes, names, etc.
    Uses quick column candidates + LIKE probe; never invents identifiers.
    """

    # NEW: ID/NO/CODE fast-path
    hit = _extract_id_lookup(user_query)
    if hit:
        id_val = hit["value"]
        hint = hit["hint_table"]
        id_cols = _list_id_like_columns(selected_db)

        # Prefer tables that match the hint (e.g., SHIPMENTS for "shipment id ...")
        if hint:
            id_cols = [x for x in id_cols if hint in x["table"].upper()] or id_cols

        # Probe a few promising columns quickly using equality (not LIKE)
        best = None
        try:
            with connect_to_source(selected_db) as (conn, _):
                cur = conn.cursor()
                _set_case_insensitive_session(cur)
                for x in id_cols:
                    t, c, dt = x["table"], x["column"], x["dtype"]
                    try:
                        if any(k in dt for k in ("NUMBER", "INTEGER", "FLOAT", "BINARY")):
                            cur.execute(f"SELECT 1 FROM {t} WHERE {c} = :v AND ROWNUM = 1", v=id_val)
                        else:
                            cur.execute(f"SELECT 1 FROM {t} WHERE {c} = :v AND ROWNUM = 1", v=str(id_val))
                        if cur.fetchone():
                            best = (t, c, dt)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

        if best:
            t, c, dt = best
            if any(k in dt for k in ("NUMBER", "INTEGER", "FLOAT", "BINARY")):
                sql = f"SELECT * FROM {t} WHERE {c} = {id_val} FETCH FIRST 200 ROWS ONLY"
            else:
                id_val_esc = str(id_val).replace("'", "''")
                sql = f"SELECT * FROM {t} WHERE {c} = '{id_val_esc}' FETCH FIRST 200 ROWS ONLY"
            try:
                rows = run_sql(sql, selected_db)
                display_mode = determine_display_mode(user_query, rows)
                rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
                py_sum = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
                if display_mode in ["summary", "both"]:
                    summary = (
                        summarize_with_mistral(
                            user_query=user_query,
                            columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                            rows=rows_for_summary,
                            backend_summary=py_sum,
                            sql=sql,
                        )
                        if SUMMARY_ENGINE == "llm"
                        else py_sum
                    )
                else:
                    summary = ""
                return {
                    "status": "success",
                    "summary": summary,
                    "sql": sql,
                    "display_mode": display_mode,
                    "results": {
                        "columns": (list(rows[0].keys()) if rows else []),
                        "rows": [list(r.values()) for r in rows] if rows else [],
                        "row_count": len(rows) if rows else 0,
                    },
                    "schema_context": schema_chunks,
                    "schema_context_ids": schema_context_ids,
                }
            except Exception as e:
                return {"status": "error", "message": f"Oracle query failed: {e}", "sql": sql}

    # … fall through to the existing name/text entity logic afterwards …

    needle = _needle_from_question(user_query)
    candidates = _candidate_columns(selected_db, user_query)
    if len(candidates) < 5:
        meta_cols = _list_name_like_columns(selected_db, query_text=user_query)
        candidates = _merge_candidates(candidates, meta_cols, cap=200)

    probe_hits = _quick_value_probe(selected_db, needle, candidates)
    if not probe_hits:
        return {
            "status": "success",
            "summary": "No matching entities found.",
            "sql": None,
            "display_mode": "summary",
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    # Select the most frequent (table, column) from probe hits
    from collections import Counter
    cc = Counter((h["table"], h["column"]) for h in probe_hits)
    ranked = sorted(cc.items(), key=lambda kv: kv[1], reverse=True)
    best_pair = next(((t, c) for (t, c), _cnt in ranked if not _is_banned_table(t)), None)
    if not best_pair:
        return {
            "status": "success",
            "summary": "No matching entities found.",
            "sql": None,
            "display_mode": "summary",
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    best_table, best_col = best_pair
    esc = needle.upper().replace("'", "''")
    sql = f"SELECT * FROM {best_table} WHERE UPPER({best_col}) LIKE '%{esc}%' FETCH FIRST 200 ROWS ONLY"

    try:
        rows = run_sql(sql, selected_db)
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
        if display_mode in ["summary", "both"]:
            summary = (
                summarize_with_mistral(
                    user_query=user_query,
                    columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                    rows=rows_for_summary,
                    backend_summary=python_summary,
                    sql=sql,
                )
                if SUMMARY_ENGINE == "llm"
                else python_summary
            )
        else:
            summary = ""
        return {
            "status": "success",
            "summary": summary,
            "sql": sql,
            "display_mode": display_mode,
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }
    except Exception as e:
        logger.error(f"[EntityLookup] Oracle error: {e}")
        return {"status": "error", "message": f"Oracle query failed: {str(e)}", "sql": sql}

def _generic_browse_fallback(user_query: str, selected_db: str, options: Dict[str, Any],
                             schema_chunks: List[str], schema_context_ids: List[str]) -> Dict[str, Any]:
    """
    If the planner fails, show *something sensible*:
    pick the best-matching table from options and return SELECT * ... FETCH FIRST 200.
    """
    tables = options.get("tables") or []
    if not tables:
        return {
            "status": "error",
            "message": "Planner failed and no candidate tables were available.",
            "schema_context_ids": schema_context_ids,
        }

    # score tables by overlap of user tokens with column names (lightweight & deterministic)
    toks = [t.lower() for t in re.findall(r"[A-Za-z0-9]+", user_query or "") if len(t) >= 3]
    def tscore(t: str) -> int:
        cols = [c["name"] for c in (options.get("columns", {}).get(t, []) or [])]
        score = sum(any(tok in (cname.lower()) for tok in toks) for cname in cols)
        # gentle boost for obvious domain cues in table name
        if re.search(r"(pay|payment|import|lc|bill)", t, re.I):
            score += 3
        return score

    best = max(tables, key=tscore)
    sql = f"SELECT * FROM {best} FETCH FIRST 200 ROWS ONLY"

    try:
        rows = run_sql(sql, selected_db)
        display_mode = determine_display_mode(user_query, rows)
        rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
        python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
        summary = (summarize_with_mistral(
            user_query=user_query,
            columns=(list(rows_for_summary[0].keys()) if rows_for_summary else []),
            rows=rows_for_summary,
            backend_summary=python_summary,
            sql=sql,
        ) if SUMMARY_ENGINE == "llm" and display_mode in ["summary", "both"] else python_summary)

        return {
            "status": "success",
            "summary": summary if display_mode in ["summary","both"] else "",
            "sql": sql,
            "display_mode": display_mode,
            "results": {
                "columns": (list(rows[0].keys()) if rows else []),
                "rows": [list(r.values()) for r in rows] if rows else [],
                "row_count": len(rows) if rows else 0,
            },
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }
    except Exception as e:
        logger.error(f"[Fallback] Oracle error: {e}")
        return {"status": "error", "message": f"Oracle query failed: {str(e)}", "sql": sql}

# ---------------------------
# Public API
# ---------------------------

def answer(user_query: str, selected_db: str) -> Dict[str, Any]:
    """
    RAG pipeline:
      (fast paths) → retrieval → runtime options → planner (JSON or raw SQL) → build/validate → execute → summarize.
    Returns the envelope the frontend expects.
    """
    logger.info(f"[RAG] Q: {user_query} (DB: {selected_db})")
    uq = (user_query or "").strip()
    
    # Enhanced query analysis (integrated from enhanced modules)
    enhanced_analysis = analyze_enhanced_query(uq)
    logger.info(f"[RAG] Enhanced analysis: {enhanced_analysis['intent']} with companies: {[c['code'] for c in enhanced_analysis['companies']]}")
    
    # Try enhanced date extraction from query_engine first, fallback to existing methods
    enhanced_date_range = None
    try:
        # Import the enhanced date function from query_engine to avoid naming conflict
        from app.query_engine import extract_enhanced_date_range as enhanced_date_extractor
        enhanced_date_range = enhanced_date_extractor(uq)
        if enhanced_date_range and isinstance(enhanced_date_range, dict) and 'type' in enhanced_date_range:
            logger.info(f"[RAG] Enhanced date range detected: {enhanced_date_range['type']}")
    except Exception as e:
        logger.warning(f"[RAG] Enhanced date extraction failed: {e}")

    # 0) Fast paths -------------------------------------------------------------
    # 0.a) Raw SELECT passthrough (validated)
    if re.match(r'(?is)^\s*select\b', uq):
        sql = normalize_dates(uq.rstrip(";"))
        try:
            enforce_predicate_type_compat(sql, selected_db)
            if not is_valid_sql(sql, selected_db):
                return {"status": "error", "message": "Invalid SQL", "sql": sql}
            rows = run_sql(sql, selected_db)
            display_mode = determine_display_mode(user_query, rows)
            rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
            python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""
            summary = (summarize_with_mistral(
                user_query=user_query,
                columns=list(rows_for_summary[0].keys()) if rows_for_summary else [],
                rows=rows_for_summary,
                backend_summary=python_summary,
                sql=sql,
            ) if SUMMARY_ENGINE == "llm" and display_mode in ["summary", "both"] else python_summary)
            return {
                "status": "success",
                "summary": summary if display_mode in ["summary","both"] else "",
                "sql": sql,
                "display_mode": display_mode,
                "results": {
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows) if rows else 0,
                },
                "schema_context": [],
                "schema_context_ids": [],
            }
        except Exception as e:
            return {"status": "error", "message": f"Oracle query failed: {e}", "sql": sql}

    # 0.b) “all table name(s)” quick path
    if re.search(r'\ball\s+table\s+name(s)?\b', uq, re.I):
        try:
            with connect_to_source(selected_db) as (conn, _):
                cur = conn.cursor()
                cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
                rows = [{"TABLE_NAME": r[0]} for r in cur.fetchall()]
            return {
                "status": "success",
                "summary": "",
                "sql": "SELECT table_name FROM user_tables ORDER BY table_name",
                "display_mode": "table",
                "results": {"columns": ["TABLE_NAME"], "rows": [[r["TABLE_NAME"]] for r in rows], "row_count": len(rows)},
                "schema_context": [],
                "schema_context_ids": [],
            }
        except Exception as e:
            return {"status": "error", "message": f"Oracle query failed: {e}"}

    # 1) Retrieve schema context from vector store -----------------------------
    results = _search_schema(user_query, selected_db, top_k=12)
    schema_chunks = [r.get("document") for r in results] if results else []
    schema_context_ids = _extract_context_ids(results)
    candidate_tables = _tables_from_results(results)
    candidate_tables = _filter_banned_tables(candidate_tables)
    candidate_tables = _bias_tables_for_day(candidate_tables, uq)
    # NEW: if it’s a single-day/“day” query, make sure daily tables are present
    if _DAILY_HINT_RX.search(uq):
        extras = _discover_dailyish_tables(selected_db, must_have_cols=('PRODUCTION_QTY','FLOOR_NAME'))
        extras = _filter_banned_tables(extras)
        # keep order: already-retrieved tables first, then extras not already present
        seen = {t.upper() for t in candidate_tables}
        candidate_tables += [t for t in extras if t.upper() not in seen]

    # Force T_PROD vs T_PROD_DAILY ordering when applicable
    candidate_tables = _maybe_force_tprod_tables(uq, selected_db, candidate_tables)

    # (optional safety) re-filter in case the forcing step ever reintroduces something
    candidate_tables = _filter_banned_tables(candidate_tables)

    # 2) Build runtime options from live metadata (keep this **tight**) --------
    options = _build_runtime_options(selected_db, candidate_tables)
    if not options.get("tables"):
        # If retrieval gave nothing usable, still try an entity lookup if that fits
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        return {
            "status": "error",
            "message": "No relevant tables found.",
            "schema_context_ids": schema_context_ids
        }

    # 3) Planner → STRICT validation ------------------------------------------
    plan = _ask_planner(user_query, options)
    ok, why = _validate_plan(plan or {}, options)
    if not ok:
        logger.info(f"[RAG] Planner not directly usable ({why}).")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        # NEW: graceful table-browse fallback
        return _generic_browse_fallback(user_query, selected_db, options, schema_chunks, schema_context_ids)

    plan = _augment_plan_with_metrics(uq, plan, options)
    ok, why = _validate_plan(plan or {}, options)
    if not ok:
        logger.info(f"[RAG] Plan invalid after augmentation ({why}).")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        # NEW: graceful table-browse fallback
        return _generic_browse_fallback(uq, selected_db, options, schema_chunks, schema_context_ids)


    # If planner returned raw SQL, validate and use it; otherwise build from plan
    maybe_sql = (plan or {}).get("sql") or (plan or {}).get("query")
    try:
        if isinstance(maybe_sql, str) and maybe_sql.strip().lower().startswith("select"):
            sql = maybe_sql.strip().rstrip(";")
        else:
            sql = build_sql_from_plan(plan, selected_db, user_query)

        sql = normalize_dates(sql)
        sql = enforce_wide_projection_for_generic(user_query, sql)
        sql = value_aware_text_filter(sql, selected_db)
        sql = ensure_label_filter(sql, user_query, selected_db)

        enforce_predicate_type_compat(sql, selected_db)
        if not is_valid_sql(sql, selected_db):
            raise ValueError("Generated SQL failed prepare() validation")
    except Exception as e:
        logger.warning(f"[RAG] SQL build/validation error: {e}")
        if _is_entity_lookup(user_query):
            return _entity_lookup_path(user_query, selected_db, schema_chunks, schema_context_ids)
        return {
            "status": "error",
            "message": f"SQL generation failed: {str(e)}",
            "schema_context_ids": schema_context_ids
        }

    # 4) Execute ---------------------------------------------------------------
    try:
        rows = run_sql(sql, selected_db)
    except Exception as e:
        logger.error(f"[RAG] Oracle error during execute: {e}")
        return {
            "status": "error",
            "message": f"Oracle query failed: {str(e)}",
            "sql": sql,
            "schema_context_ids": schema_context_ids
        }
    # --- Retry path for day-level questions that returned 0 rows -----------------
    if not rows and _DAILY_HINT_RX.search(uq):
        # Prefer only daily-ish tables from the earlier retrieval set
        daily_only = _filter_banned_tables([t for t in candidate_tables if _DAILY_NAME_RX.search(t)])
        if daily_only:
            # Apply T_PROD vs T_PROD_DAILY forcing within the daily-only set
            forced_daily = _maybe_force_tprod_tables(uq, selected_db, daily_only)
            options2 = _build_runtime_options(selected_db, forced_daily)

            plan2 = _ask_planner(uq, options2)
            ok2, _ = _validate_plan(plan2 or {}, options2)
            if ok2:
                try:
                    sql2 = build_sql_from_plan(plan2, selected_db, uq)
                    sql2 = normalize_dates(sql2)
                    sql2 = enforce_wide_projection_for_generic(uq, sql2)
                    sql2 = value_aware_text_filter(sql2, selected_db)
                    sql2 = ensure_label_filter(sql2, uq, selected_db) 
                    enforce_predicate_type_compat(sql2, selected_db)
                    if is_valid_sql(sql2, selected_db):
                        rows2 = run_sql(sql2, selected_db)
                        if rows2:
                            # promote the successful retry to the main flow
                            sql, rows = sql2, rows2
                except Exception as e:
                    logger.warning(f"[RAG] Daily retry failed: {e}")

    # Special UX for explicit date-range queries → no data
    if not rows and extract_explicit_date_range(user_query):
        return {
            "status": "success",
            "summary": "No data found for the requested date range.",
            "sql": sql,
            "display_mode": determine_display_mode(user_query, []),
            "results": {"columns": [], "rows": [], "row_count": 0},
            "schema_context": schema_chunks,
            "schema_context_ids": schema_context_ids,
        }

    # 5) Summarize + format envelope ------------------------------------------
    display_mode = determine_display_mode(user_query, rows)
    rows_for_summary = widen_results_if_needed(rows, sql, selected_db, display_mode, user_query)
    python_summary = summarize_results(rows_for_summary, user_query) if display_mode in ["summary", "both"] else ""

    if display_mode in ["summary", "both"]:
        try:
            cols_for_llm = list(rows_for_summary[0].keys()) if rows_for_summary else []
            summary = summarize_with_mistral(
                user_query=user_query,
                columns=cols_for_llm,
                rows=rows_for_summary,
                backend_summary=python_summary,
                sql=sql,
            ) if SUMMARY_ENGINE == "llm" else python_summary
        except Exception as e:
            logger.warning(f"[RAG] LLM summary failed; falling back. Reason: {e}")
            summary = python_summary
    else:
        summary = ""

    return {
        "status": "success",
        "summary": summary,
        "sql": sql,
        "display_mode": display_mode,
        "results": {
            "columns": (list(rows[0].keys()) if rows else []),
            "rows": [list(r.values()) for r in rows] if rows else [],
            "row_count": len(rows) if rows else 0,
        },
        "schema_context": schema_chunks,
        "schema_context_ids": schema_context_ids,
    }