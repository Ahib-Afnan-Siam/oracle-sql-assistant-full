# app/summarizer.py
import os
import re
import json
import logging
from typing import Sequence, Dict, Any, List, Optional, Tuple
from decimal import Decimal

# Keep the import to avoid breakage elsewhere; we mostly don't call it here.
from app.ollama_llm import ask_analytical_model
from app.config import SUMMARY_MAX_ROWS, SUMMARY_CHAR_BUDGET

logger = logging.getLogger(__name__)

# -------------------------
# Tunables / Env switches
# -------------------------
MAX_BULLETS              = int(os.getenv("SUMMARY_BULLETS", "6"))
TOPN_BULLETS             = int(os.getenv("SUMMARY_TOPN_BULLETS", "6"))
TREND_BULLETS            = int(os.getenv("SUMMARY_TREND_BULLETS", "6"))
QUICK_WORD_LIMIT         = int(os.getenv("SUMMARY_QUICK_WORD_LIMIT", "24"))
DIRECT_ANSWER_ENABLED    = os.getenv("SUMMARY_DIRECT_ANSWER", "1") == "1"
ALLOW_LLM_FALLBACK       = os.getenv("SUMMARY_ALLOW_LLM_FALLBACK", "0") == "1"  # default OFF for speed
ENTITY_MAX_RESULTS       = int(os.getenv("SUMMARY_ENTITY_MAX_RESULTS", "6"))
HEAVY_ROW_THRESHOLD      = int(os.getenv("SUMMARY_HEAVY_ROW_THRESHOLD", "2500"))

# -------------------------
# Light cleaners
# -------------------------
_TABLE_BLOCK_RX = re.compile(
    r"(^|\n)(\s*\|.*\|\s*\n\s*\|(?:\s*:?-+:?\s*\|)+\s*\n(?:\s*\|.*\|\s*\n?)+)",
    re.MULTILINE,
)
def _strip_tables_and_code(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return _TABLE_BLOCK_RX.sub("\n", text).strip()

# -------------------------
# Small helpers
# -------------------------
_NUM_HINT   = re.compile(r'(qty|quantity|amount|amt|value|total|sum|sales|revenue|cost|price|on[_-]?hand|stock|count|dhu)$', re.I)
_ID_HINT    = re.compile(r'(?:^|_)(id|code|no|num|number)$', re.I)
_LABEL_PREF = re.compile(r'(FLOOR|LINE|NAME|BUYER|STYLE|DEPT|DEPARTMENT|FACTORY|COMPANY|SUPPLIER|CUSTOMER|MONTH|PERIOD|DATE)$', re.I)
_DATE_STR   = re.compile(r'^\d{2}-[A-Za-z]{3}-\d{2,4}$|^\d{4}-\d{2}-\d{2}$', re.I)
# Broader entity-style openers (supports “who’s/whos/what’s/whats/which …” and polite prefixes)
_ENTITY_Q_RX = re.compile(r"""
^\s*
(?:tell\s+me\s+|show\s+me\s+|list\s+|find\s+)?          # optional prefixes
(?:who|whom|what|which|who'?s|whos|what'?s|whats|which'?s)
(?:\s+(?:is|are|was|were|will\s+be))?                   # optional copula
\b
""", re.I | re.X)

# Also catch “name of …”, “… named …”, “… with name …”
_NAME_OF_RX     = re.compile(r"\b(?:name|full\s+name|customer\s+name|buyer\s+name|supplier\s+name)\s+of\s+(.+?)(?:\?|$)", re.I)
_NAMED_RX       = re.compile(r"\b(?:named|called)\s+([A-Za-z0-9 ._\-]{1,64})\b", re.I)
_WITH_NAME_RX   = re.compile(r"\bwith\s+(?:the\s+)?name\s+(?:of\s+)?['\"]?([A-Za-z0-9 ._\-]{1,64})['\"]?", re.I)

# Guard: terms that imply a metric/aggregate ask; if present, don't treat as entity lookup
_METRIC_TERMS_RX = re.compile(
    r"(?:total|sum|count|avg|average|max|min|top|trend|daily|weekly|monthly|"
    r"qty|quantity|production|output|rate|pct|percent|dhu|eff|efficiency|"
    r"revenue|sales|cost|price|amount|value|stock|on[-_ ]?hand|"
    r"salary|pay|wage|compensation)\b", re.I)

# --- NEW: metric intent + rate detectors
_REQ_METRIC_RX = re.compile(
    r"(prod|production|qty|quantity|pcs?|pieces?|defect|rej|rejection|dhu|eff|efficiency|rate|pct|percent|"
    r"stain|dirty|salary|pay|wage|compensation)", re.I)
_RATE_RX       = re.compile(r'(rate|pct|percent|dhu|eff)', re.I)

def _entity_needle(user_query: str) -> str:
    q = user_query or ""

    # who/what/which/whos/what's … [is/are] <needle>
    m = re.search(
        r"^\s*(?:tell\s+me\s+|show\s+me\s+|list\s+|find\s+)?"
        r"(?:who|whom|what|which|who'?s|whos|what'?s|whats|which'?s)"
        r"(?:\s+(?:is|are|was|were|will\s+be))?\s+(.*?)(?:\?|$)",
        q, re.I
    )
    if m and m.group(1):
        return m.group(1).strip()

    # “… name of <needle>”
    m = _NAME_OF_RX.search(q)
    if m and m.group(1):
        return m.group(1).strip()

    # “… named <needle>”, “… called <needle>”
    m = _NAMED_RX.search(q)
    if m and m.group(1):
        return m.group(1).strip()

    # “… with name (of) <needle>”
    m = _WITH_NAME_RX.search(q)
    if m and m.group(1):
        return m.group(1).strip()

    return ""


def _pretty(name: str) -> str:
    return name.replace('_', ' ').title()

def _agg_metric(values: List[float], colname: str) -> tuple[str, float]:
    """Use Avg for rate-like metrics; Total for qty-like."""
    if not values:
        return ("total", 0.0)
    if _RATE_RX.search(colname):
        return ("avg", sum(values) / len(values))
    return ("total", sum(values))


def _is_num(v): return isinstance(v, (int, float, Decimal)) and not isinstance(v, bool)

def _fmt_num(v):
    if isinstance(v, Decimal): v = float(v)
    s = f"{v:,.2f}"
    return s.rstrip("0").rstrip(".")

def _month_token_from_query(q: str) -> Optional[str]:
    m = re.search(r'\b([A-Za-z]{3}-\d{2,4})\b', q or "")
    return m.group(1) if m else None

def _main_table_from_sql(sql: Optional[str]) -> Optional[str]:
    if not sql: return None
    m = re.search(r'(?is)\bfrom\b\s+([A-Za-z0-9_\."]+)', sql)
    if not m: return None
    t = m.group(1).strip().strip('"')
    return t

def _first(iterable, pred):
    for x in iterable:
        if pred(x): return x
    return None

def _pick_label_columns(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> List[str]:
    if not columns or not rows: return []
    # Prefer non-numeric columns; bias towards *_NAME, FLOOR_NAME, LINE, DEPT, etc.
    nonnum = []
    for c in columns:
        sample = _first((r.get(c) for r in rows if c in r), lambda v: v is not None)
        if sample is None: continue
        if not _is_num(sample):
            nonnum.append(c)
    nonnum.sort(key=lambda c: (0 if _LABEL_PREF.search(c) else 1, c.lower()))
    return nonnum

def _pick_metric_columns(
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    user_query: str = "",
    sql: Optional[str] = None
) -> List[str]:
    if not columns or not rows: return []
    nums = []

    # optional: honor SELECT alias order (helps match planner output)
    alias_order = {}
    if sql:
        for i, m in enumerate(re.finditer(r'\bAS\s+([A-Za-z0-9_]+)', sql or "", re.I)):
            alias_order[m.group(1).upper()] = i

    for c in columns:
        sample = _first((r.get(c) for r in rows if c in r), lambda v: v is not None)
        if sample is None: continue
        if _is_num(sample):
            # Base scoring (keep existing preferences)
            score = 0
            if _NUM_HINT.search(c): score -= 2
            if _ID_HINT.search(c):  score += 3

            # Domain priority: prod/qty > rate-ish > defects (tunable, small nudges)
            cl = c.lower()
            if 'prod' in cl or 'output' in cl or cl.endswith('qty'): score -= 4
            if re.search(r'(eff|rate|pct|percent|dhu)', cl):         score -= 2
            if re.search(r'(defect|rej|stain|dirty)', cl):           score -= 1

            # If user asked for a metric family, give it a boost
            if _REQ_METRIC_RX.search(user_query or "") and _REQ_METRIC_RX.search(c):
                score -= 5

            ao = alias_order.get(c.upper(), 999)  # tiebreaker by planner alias order
            nums.append((score, ao, c))
    nums.sort(key=lambda kv: (kv[0], kv[1], kv[2].lower()))
    return [c for _, __, c in nums]

def _find_date_like_column(columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    for c in columns:
        v = _first((r.get(c) for r in rows if c in r), lambda x: x is not None)
        if v is None: continue
        if hasattr(v, "isoformat"): return c  # datetime/date
        if isinstance(v, str) and _DATE_STR.match(v): return c
        if c.upper().endswith(("DATE","DT")): return c
    return None

def _topn_lines(rows: Sequence[Dict[str, Any]], label: str, metric: str, n: int) -> str:
    safe = [r for r in rows if r.get(label) not in (None, "") and _is_num(r.get(metric))]
    safe.sort(key=lambda r: float(r[metric]), reverse=True)
    top = safe[:n]
    return "; ".join(f"{i+1}) {r[label]} — {_fmt_num(r[metric])}" for i, r in enumerate(top))

def _group_totals(rows: Sequence[Dict[str, Any]], label: str, metric: str) -> Tuple[float, Optional[Tuple[str,float]], Optional[Tuple[str,float]]]:
    if not rows: return 0.0, None, None
    agg = {}
    for r in rows:
        k = r.get(label)
        v = r.get(metric)
        if k in (None, "") or not _is_num(v): continue
        agg[k] = agg.get(k, 0.0) + float(v)
    total = sum(agg.values())
    if not agg: return total, None, None
    best = max(agg.items(), key=lambda kv: kv[1])
    worst = min(agg.items(), key=lambda kv: kv[1])
    return total, (best[0], best[1]), (worst[0], worst[1])

# -------------------------
# Intent classification
# -------------------------
_SUMMARY_WORDS = {"summary", "summarise", "summarize", "overview", "report"}
_TREND_WORDS   = {"day wise", "day-wise", "daily", "weekly", "month wise", "mon-yy", "mon-yyyy", "last 7 days", "last month", "yesterday", "today"}
_TOPN_WORDS    = {"top", "max", "maximum", "big", "biggest", "largest", "highest", "min", "minimum", "lowest", "least"}
_KPI_WORDS     = {"total", "sum", "count", "overall"}
_TABLE_SRC     = {"from which table", "which table this data came"}

def _norm(s: str) -> str:
    return (s or "").lower().strip()

def _classify(user_query: str, columns: Sequence[str], rows: Sequence[Dict[str, Any]]) -> str:
    q = _norm(user_query)
    rc = len(rows or [])

    # Entity lookup: identity/name-style asks ONLY if they don't look metric/aggregate-y
    if ((_ENTITY_Q_RX.match(q) or _NAME_OF_RX.search(q) or _NAMED_RX.search(q) or _WITH_NAME_RX.search(q))
            and not _METRIC_TERMS_RX.search(q)):
        return "entity_lookup"

    # Single KPI one-liner
    if DIRECT_ANSWER_ENABLED and rc == 1:
        row = rows[0] if rows else {}
        num_items = [(k, v) for k, v in row.items() if _is_num(v)]
        if len(num_items) == 1:
            return "kpi_one"

    if any(w in q for w in _TABLE_SRC):
        return "table_source"

    if any(w in q for w in _TOPN_WORDS):
        return "topn"

    if any(w in q for w in _TREND_WORDS):
        return "trend"

    if any(w in q for w in _SUMMARY_WORDS):
        return "group_summary"

    # generic “list”, “stock”, “items”, “table”
    if re.search(r'\b(list|table|items?|stock|barcode|order|employee|dept|department)\b', q):
        return "listish"

    # default: group summary if grouped-looking; else compact bullets
    return "group_summary"

# -------------------------
# Renderers (no LLM)
# -------------------------
def _render_kpi_one(user_query, columns, rows) -> str:
    row = rows[0]
    num_key, num_val = next((k, v) for k, v in row.items() if _is_num(v))
    label_cols = _pick_label_columns(columns, rows)
    ctx_bits = []
    if label_cols:
        # pick most meaningful label
        label_key = label_cols[0]
        label_val = row.get(label_key)
        if label_val not in (None, ""):
            ctx_bits.append(str(label_val))
    month_tok = _month_token_from_query(user_query)
    if month_tok:
        ctx_bits.append(month_tok)

    metric_name = num_key.replace("_", " ").title()
    if ctx_bits:
        return f"{metric_name} — {', '.join(ctx_bits)}: {_fmt_num(num_val)}"
    return f"{metric_name}: {_fmt_num(num_val)}"

def _render_topn(user_query, columns, rows) -> str:
    label_cols = _pick_label_columns(columns, rows)
    metric_cols = _pick_metric_columns(columns, rows, user_query)
    if not label_cols or not metric_cols:
        return _render_group_summary(user_query, columns, rows)

    label = label_cols[0]
    metric = metric_cols[0]

    # ask for N? e.g., "top list 2", "top 5"
    m = re.search(r'\btop(?:\s+list)?\s+(\d{1,2})\b', _norm(user_query))
    n = int(m.group(1)) if m else 1 if re.search(r'\bjust one row\b', _norm(user_query)) else min(5, len(rows))
    lines = _topn_lines(rows, label, metric, n)
    title = f"Top {n} {label.replace('_',' ').title()} by {metric.replace('_',' ').title()}:"
    return f"{title} {lines}"

def _render_trend(user_query, columns, rows) -> str:
    date_col = _find_date_like_column(columns, rows)
    metric_cols = _pick_metric_columns(columns, rows, user_query)
    if not date_col or not metric_cols:
        return _render_group_summary(user_query, columns, rows)

    metric = metric_cols[0]
    safe = [r for r in rows if _is_num(r.get(metric))]
    if not safe:
        return _render_group_summary(user_query, columns, rows)

    total = sum(float(r[metric]) for r in safe)
    avg = total / max(1, len(safe))

    # best/worst day
    best = max(safe, key=lambda r: float(r[metric]))
    worst = min(safe, key=lambda r: float(r[metric]))

    bullets = []
    bullets.append(f"Total {metric.replace('_',' ').title()}: {_fmt_num(total)} over {len(safe)} day(s)")
    bullets.append(f"Average per day: {_fmt_num(avg)}")
    bullets.append(f"Best day: {best.get(date_col)} — {_fmt_num(best[metric])}")
    bullets.append(f"Worst day: {worst.get(date_col)} — {_fmt_num(worst[metric])}")

    return " • ".join(bullets[:TREND_BULLETS])

def _render_group_summary(user_query, columns, rows, sql: Optional[str] = None) -> str:
    metric_cols = _pick_metric_columns(columns, rows, user_query, sql)
    label_cols  = _pick_label_columns(columns, rows)

    # If we have a clear grouping label, summarize totals & extremes on the primary metric
    if metric_cols and label_cols:
        metric = metric_cols[0]
        label  = label_cols[0]
        total, best, worst = _group_totals(rows, label, metric)

        bullets = []
        bullets.append(f"Total {_pretty(metric)}: {_fmt_num(total)}")
        if best:
            bullets.append(f"Top {_pretty(label)}: {best[0]} — {_fmt_num(best[1])}")
        if worst:
            bullets.append(f"Bottom {_pretty(label)}: {worst[0]} — {_fmt_num(worst[1])}")

        # NEW: include other requested KPI totals/avgs (limit 4 overall)
        requested = []
        if _REQ_METRIC_RX.search(user_query or ""):
            for m in metric_cols:
                if _REQ_METRIC_RX.search(m):
                    requested.append(m)
        wanted = list(dict.fromkeys((requested or metric_cols)))[:4]

        kpis = []
        for m in wanted:
            # skip the primary if already summarized as "Total ..."
            if m == metric:
                continue
            vals = [float(v) for v in (r.get(m) for r in rows) if _is_num(v)]
            if not vals:
                continue
            kind, agg = _agg_metric(vals, m)
            label_kind = "Avg" if kind == "avg" else "Total"
            kpis.append(f"{label_kind} {_pretty(m)}: {_fmt_num(agg)}")
        if kpis:
            bullets.append(" ; ".join(kpis))

        if len({r.get(label) for r in rows if r.get(label) not in (None, "")}) > 2:
            bullets.append(_render_topn("top 3", columns, rows))

        return " • ".join(bullets[:MAX_BULLETS])

    # If only numeric columns (no clear label) → totals/avgs across up to 4 metrics
    if metric_cols and not label_cols:
        parts = []
        for m in metric_cols[:4]:
            vals = [float(v) for v in (r.get(m) for r in rows) if _is_num(v)]
            if not vals:
                continue
            kind, agg = _agg_metric(vals, m)
            prefix = "Avg" if kind == "avg" else "Total"
            parts.append(f"{prefix} {_pretty(m)}: {_fmt_num(agg)}")
        return " ; ".join(parts) if parts else f"{len(rows)} row(s)."

    # Otherwise, treat as list/lookup
    return _render_listish(user_query, columns, rows)

def _render_listish(user_query, columns, rows) -> str:
    if not rows:
        return "No rows returned."
    rc = len(rows)
    label_cols = _pick_label_columns(columns, rows)
    # Provide quick count + a few examples
    ex_vals = []
    if label_cols:
        lk = label_cols[0]
        for r in rows:
            v = r.get(lk)
            if v in (None, ""): continue
            ex_vals.append(str(v))
            if len(ex_vals) >= 5: break
    if ex_vals:
        return f"{rc} row(s). Examples: " + "; ".join(ex_vals)
    return f"{rc} row(s) returned."

def _render_table_source(sql: Optional[str]) -> str:
    t = _main_table_from_sql(sql)
    return f"Source table: {t}" if t else "Source table could not be determined."

def _render_entity_lookup(user_query, columns, rows) -> str:
    if not rows:
        return "No matches found."

    needle = _entity_needle(user_query)
    label_cols = _pick_label_columns(columns, rows) or list(columns or [])
    if not label_cols:
        label_cols = [c for c in columns if not _is_num(rows[0].get(c))] or list(columns)

    # score label columns by how often they contain the needle; bias *_NAME, FLOOR, LINE, etc.
    def _score_col(c: str) -> int:
        n = 0
        if needle:
            n = sum(
                1
                for r in rows
                if isinstance(r.get(c), str) and needle.lower() in r[c].lower()
            )
        if _LABEL_PREF.search(c):
            n += 2
        return n

    label_cols.sort(key=lambda c: (-_score_col(c), c.lower()))

    # 🔧 KEY CHANGE: harvest from top few label columns (helps 1-row aggregator outputs)
    harvest_cols = label_cols[:3]  # small, safe number
    # collect distinct values across chosen columns; show those containing the needle first
    raw_vals = []
    for c in harvest_cols:
        for r in rows:
            v = r.get(c)
            if v not in (None, ""):
                raw_vals.append(str(v))

    seen, uniq = set(), []
    for s in raw_vals:
        k = s.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(s)

    if needle:
        low = needle.lower()
        uniq.sort(key=lambda s: (0 if low in s.lower() else 1, s.lower()))
    else:
        uniq.sort(key=str.lower)

    picks = uniq[:ENTITY_MAX_RESULTS]
    count = len(uniq)
    if picks:
        prefix = f"Matches for “{needle}”" if needle else "Matches"
        tail = "" if count <= len(picks) else f" (showing {len(picks)} of {count})"
        return f"{prefix}: " + " • ".join(picks) + tail

    return "No matches found."

# -------------------------
# Public API (drop-in)
# -------------------------
def summarize_with_mistral(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    backend_summary: str,
    sql: Optional[str] = None,
    max_rows: int = SUMMARY_MAX_ROWS,
    char_budget: int = SUMMARY_CHAR_BUDGET,
) -> str:
    """
    Fast, deterministic summarizer optimized for your query set.
    Avoids LLM calls in the hot path.
    """
    try:
        style = _classify(user_query, columns, rows)

        # NEW: direct entity answers (fast, readable)
        if style == "entity_lookup":
            return _render_entity_lookup(user_query, columns, rows)

        if style == "kpi_one":
            return _render_kpi_one(user_query, columns, rows)

        if style == "table_source":
            return _render_table_source(sql)

        if style == "topn":
            return _render_topn(user_query, columns, rows)

        if style == "trend":
            if ALLOW_LLM_FALLBACK and len(rows) > HEAVY_ROW_THRESHOLD:
                text, _ = summarize_with_mistral_with_prompt(
                    user_query, columns, rows, backend_summary, sql, max_rows, char_budget
                )
                return _strip_tables_and_code(text)
            return _render_trend(user_query, columns, rows)

        if style == "group_summary":
            if ALLOW_LLM_FALLBACK and len(rows) > HEAVY_ROW_THRESHOLD:
                text, _ = summarize_with_mistral_with_prompt(
                    user_query, columns, rows, backend_summary, sql, max_rows, char_budget
                )
                return _strip_tables_and_code(text)
            return _render_group_summary(user_query, columns, rows, sql)

        if style == "listish":
            return _render_listish(user_query, columns, rows)

        # Fallback to compact backend summary if nothing matched
        return _compact_backend_summary(backend_summary)

    except Exception as e:
        logger.error(f"[summarizer] error: {e}")
        # Extremely rare: optionally allow tiny LLM rephrase of backend summary
        if ALLOW_LLM_FALLBACK:
            prompt = f"""
Answer the USER QUESTION in one or two short sentences (≤ {QUICK_WORD_LIMIT} words).
Use ONLY numbers that already appear below. No bullets, no headings.

USER QUESTION
{user_query}

BACKEND SUMMARY
{backend_summary}
""".strip()
            resp = ask_analytical_model(prompt)
            return _strip_tables_and_code((resp or "").strip() or backend_summary)
        return _compact_backend_summary(backend_summary)

def _compact_backend_summary(backend_summary: str) -> str:
    """
    Shrink the Python backend summary to a single concise line.
    Used only as a safety fallback.
    """
    if not backend_summary:
        return ""
    text = re.sub(r"\s+", " ", backend_summary)
    # Clip hard to avoid verbose slabs
    return text[:280].rstrip(" .") + ("…" if len(text) > 280 else "")

# -------------------------
# (Optional) slower variant with snapshot + LLM
# -------------------------
def _pipe_snapshot(
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    max_rows: int,
    char_budget: int
) -> str:
    if not columns:
        return ""
    header = " | ".join(map(str, columns))
    lines = [header]
    if not rows:
        return "\n".join(lines)

    head_n = min(max_rows // 2, len(rows))
    tail_n = min(max_rows - head_n, max(0, len(rows) - head_n))
    sample = rows[:head_n] + (rows[-tail_n:] if tail_n else [])

    def clean(val: Any) -> str:
        s = "" if val is None else str(val)
        return s.replace("\n", " ").replace("\r", " ").strip()

    for r in sample:
        lines.append(" | ".join(clean(r.get(c)) for c in columns))

    snap = "\n".join(lines)
    if len(snap) <= char_budget:
        return snap
    keep = max(1, int((len(sample) * char_budget) / max(1, len(snap))))
    keep = min(keep, len(sample))
    return "\n".join([header] + lines[1:1 + keep])

def summarize_with_mistral_with_prompt(
    user_query: str,
    columns: Sequence[str],
    rows: Sequence[Dict[str, Any]],
    backend_summary: str,
    sql: Optional[str] = None,
    max_rows: int = SUMMARY_MAX_ROWS,
    char_budget: int = SUMMARY_CHAR_BUDGET,
) -> tuple[str, str]:
    """
    Rarely used, slower path that can include a tiny data snapshot and
    (optionally) invoke the LLM. Kept for compatibility / debugging.
    """
    snapshot = _pipe_snapshot(columns, rows, max_rows=max_rows, char_budget=char_budget)
    prompt = f"""
You are a senior data analyst. Provide a concise business-ready summary that directly answers the user's EXACT question.
Use ONLY the provided BACKEND STATS and DATA SNAPSHOT. Never invent numbers.
One short paragraph + up to {MAX_BULLETS} bullets. No tables, no code fences.

USER QUESTION
{user_query}

SQL USED
{sql or '—'}

BACKEND STATS (from Python)
{backend_summary}

DATA SNAPSHOT (pipe-delimited)
{snapshot}
""".strip()

    if not ALLOW_LLM_FALLBACK:
        # deterministic compact output without model
        text = f"{backend_summary.splitlines()[0] if backend_summary else ''}".strip()
        return (text or "Summary generated."), prompt

    response = ask_analytical_model(prompt)
    cleaned = _strip_tables_and_code((response or "").strip() or backend_summary)
    return cleaned, prompt

# -------------------------
# Streaming (unchanged API)
# -------------------------
def extract_insights(response: str) -> List[str]:
    # Keep identical behavior to prior version
    if re.search(r'\n\d+\.', response or ""):
        insights, current = [], []
        for line in (response or "").splitlines():
            line = line.strip()
            if re.match(r'^\d+\.', line):
                if current:
                    insights.append("\n".join(current))
                    current = []
                current.append(line)
            elif line:
                current.append(line)
        if current:
            insights.append("\n".join(current))
        return insights

    for delimiter in ["\n- ", "\n* ", "\n• "]:
        if delimiter in (response or ""):
            parts = (response or "").split(delimiter)
            insights = [parts[0].strip()]
            insights.extend([delimiter.strip() + p.strip() for p in parts[1:]])
            return insights

    return [s.strip() for s in (response or "").split('\n\n') if s.strip()]

def stream_summary(user_query: str, data_snippet: str = ""):
    """
    Streaming wrapper that can call the LLM if ALLOW_LLM_FALLBACK=1.
    Not used by the main RAG flow.
    """
    try:
        full_input = f"""
You are a senior data analyst. Provide insights based on the user's EXACT query and the data preview.

USER'S EXACT QUERY: "{user_query}"

DATA PREVIEW (first row is header):
{data_snippet}

INSTRUCTIONS:
- Respond in clear, concise bullet points
- Do NOT include any tables and do NOT use code fences
- Calculate simple metrics when appropriate (min, max, avg)
- Focus exclusively on the user's exact query
- Never invent data
""".strip()

        yield json.dumps({"stage": "summary_start", "prompt": full_input, "snapshot": data_snippet})
        yield json.dumps({"phase": "Generating summary..."})

        if not ALLOW_LLM_FALLBACK:
            # Deterministic placeholder to keep the stream API intact
            yield json.dumps({"summary": "Summary prepared."})
            yield json.dumps({"phase": "Summary complete"})
            return

        resp = ask_analytical_model(full_input)
        resp = _strip_tables_and_code(resp)
        yield json.dumps({"summary": resp})
        yield json.dumps({"phase": "Summary complete"})
    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
        yield json.dumps({"error": f"Summary generation failed: {str(e)}"})