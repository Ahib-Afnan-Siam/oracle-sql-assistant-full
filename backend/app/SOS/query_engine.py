# app/query_engine.py
"""
Lightweight SQL utilities used by the RAG pipeline.

This module intentionally contains **no** LLM orchestration logic.
It exposes a stable set of helpers for:
- Date normalization & detection
- Safe SQL building from a validated plan
- Predicate/type guards
- Execution utilities
- Display decisions & summarization
- Entity-lookup fallbacks (needle → candidates → probes)

Used by: app/rag_engine.py
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional, Tuple, Callable, Set
import time
from decimal import Decimal
from functools import lru_cache
from calendar import monthrange

# Import connect_to_source from db_connector
from app.db_connector import connect_to_source
# Import hybrid_schema_value_search from vector_store_chroma
from app.SOS.vector_store_chroma import hybrid_schema_value_search

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# near other helpers
_ID_QUERY_RX = re.compile(
    r"\b(?:(?P<table>[A-Za-z][A-Za-z0-9_]{1,})\s+)?(?P<label>id|no|number|code)\s+(?P<val>\d+)\b",
    re.IGNORECASE,
)

def _extract_id_lookup(q: str) -> Optional[dict]:
    # Existing numeric ID detection
    m = _ID_QUERY_RX.search(q or "")
    if m:
        return {
            "hint_table": (m.group("table") or "").upper(),
            "value": int(m.group("val")),
            "label": m.group("label").upper(),
        }
    
    # Enhanced patterns for various ID formats
    extended_patterns = [
        # CTL codes (CTL-25-01175, CTL-Fb-22-02071)
        (r'\b(CTL-\d{2}-\d{5,6})\b', 'CTL_CODE'),
        (r'\b(CTL-[A-Z]{2,4}-\d{2}-\d{5})\b', 'CTL_EXTENDED'),
        # Barcode numbers
        (r'\b(\d{11,14})\b', 'BARCODE'),
        # Challan numbers
        (r'\b(\d{4,5}-\d{2}\.\d{2}\.\d{4})\b', 'CHALLAN'),
        # Inventory IDs
        (r'inventory\s+(?:id\s+)?(\d+)', 'INVENTORY_ID'),
        (r'\bid\s+(\d+)', 'GENERIC_ID')
    ]
    
    for pattern, code_type in extended_patterns:
        m = re.search(pattern, q or "", re.IGNORECASE)
        if m:
            return {
                "hint_table": "",
                "value": m.group(1),
                "label": code_type,
            }
    
    return None

def _list_id_like_columns(selected_db: str, limit_tables: int = 800) -> List[Dict[str,str]]:
    sql = """
    SELECT table_name, column_name, data_type
      FROM user_tab_columns
     WHERE REGEXP_LIKE(column_name, '(^|_)(ID|NO|NUM|NUMBER|CODE)$', 'i')
     FETCH FIRST :lim ROWS ONLY
    """
    out = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        cur.execute(sql, lim=limit_tables)
        for t, c, dt in cur.fetchall():
            out.append({"table": t, "column": c, "dtype": (dt or "").upper()})
    return [x for x in out if not _is_banned_table(x["table"])]


# Whitelist for TO_CHAR date buckets
_TOCHAR_WHITELIST = {"MON-YY", "MON-YYYY", "YYYY-MM", "YYYY", "DD-MON-YYYY"}
_TOCHAR_RX = re.compile(r"""(?is)^\s*TO_CHAR\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*'([A-Za-z\-]+)'\s*\)\s*$""")

_DATE_YMD  = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_DMY  = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_DATE_DMON = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_YEAR_TOKEN = re.compile(r"\b(19|20)\d{2}\b")
_MON_YYYY  = re.compile(r"^[A-Za-z]{3}-\d{2,4}$")

# e.g. "24 May 2024" or "1 Jan 24"
_DATE_DMON_SPACE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}$")

# below _MON3/_MON_ABBR
_MONTH_ALIASES = {
    "JANUARY":"JAN","FEBRUARY":"FEB","MARCH":"MAR","APRIL":"APR","MAY":"MAY",
    "JUNE":"JUN","JULY":"JUL","AUGUST":"AUG","SEPTEMBER":"SEP","SEPT":"SEP",
    "OCTOBER":"OCT","NOVEMBER":"NOV","DECEMBER":"DEC",
    "AUGUEST":"AUG",  # common typo seen in logs
}

def _mon_to_abbr(word: str) -> Optional[str]:
    w = (word or "").strip().upper()
    if w in _MON_ABBR:       # already 3-letter abbr
        return w
    return _MONTH_ALIASES.get(w)

# now finds "Jan 2025" inside a sentence
_MON_YYYY_ANY = re.compile(r"\b([A-Za-z]{3,9})[-\s]\d{2,4}\b", re.I)
# NEW: strip standalone month words like "Jan" / "January"
_MONTH_WORD_RX = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", re.I
)

# NEW: common filler words we never want as a literal
_STOPWORDS = {
    "total","of","in","with","list","name","names","the","a","an","by","for",
    "qty","quantity","production","output","report","summary","show","table",
    "and","or","please","kindly","give","provide"    
}

# ---- Known org full-name → short code mappings (all source DBs) -------------
_ORG_SYNONYMS = [
    # CAL — Chorka Apparels Ltd (handle minor spelling variations)
    (re.compile(r"\bchorka\s+app(?:arel|arels?)\s+ltd\b", re.I), "CAL"),
    # CTL — Chorka Textile
    (re.compile(r"\bchorka\s+textile\b", re.I), "CTL"),
]

def _get_table_denylist():
    """Get the table denylist from environment variable, evaluated lazily."""
    return {
        t.strip().upper()
        for t in (os.getenv("TABLE_DENYLIST") or "").split(",")
        if t.strip()
    }

def _is_banned_table(name: str) -> bool:
    return (name or "").upper() in _get_table_denylist()

def _filter_banned_tables(names: list[str]) -> list[str]:
    return [n for n in (names or []) if n and not _is_banned_table(n)]

def _shortcode_for_org(label: str) -> Optional[str]:
    for rx, code in _ORG_SYNONYMS:
        if rx.search(label or ""):
            return code
    return None

DEFAULT_TIME_DAYS = int(os.getenv("DEFAULT_TIME_DAYS", "0"))  # 0 = no implicit range


def _is_single_day_literal(s: str) -> bool:
    s = (s or "").strip()
    return bool(_DATE_YMD.match(s) or _DATE_DMY.match(s) or _DATE_DMON.match(s) or _DATE_DMON_SPACE.match(s))

def _parse_tochar_expr(expr: str) -> Optional[Tuple[str, str]]:
    m = _TOCHAR_RX.match(expr or "")
    if not m:
        return None
    col, fmt = m.group(1), m.group(2).upper()
    if fmt not in _TOCHAR_WHITELIST:
        return None
    return (col, fmt)

# --- Single-day literal → range(start=end=that day) --------------------------
_SINGLE_DAY_RX = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b",
    re.IGNORECASE,
)

def _parse_single_day_literal(s: str) -> Optional[datetime]:
    s = s.strip()
    if _DATE_YMD.match(s):
        return datetime.strptime(s, "%Y-%m-%d")
    if _DATE_DMY.match(s):
        # 21/08/25 or 21/08/2025
        d, m, y = [int(x) for x in re.split(r"[/-]", s)]
        if y < 100: y += 2000 if y < 50 else 1900
        return datetime(y, m, d)
    if _DATE_DMON_SPACE.match(s):
        # 21 Aug 2025 / 21 Aug 25
        d_str, mon_str, y_str = s.split()
        y = int(y_str);  y = 2000 + y if y < 100 else y
        return datetime(y, _MON_ABBR[mon_str[:3].upper()], int(d_str))
    if _DATE_DMON.match(s):
        # 21-AUG-25 / 21-AUG-2025
        match = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$", s)
        if match:
            d, mon3, y = match.groups()
            y = int(y); y = 2000 + y if y < 100 else y
            return datetime(y, _MON_ABBR[mon3.upper()], int(d))
        return None
    return None

def extract_single_day_range(user_query: str) -> Optional[Dict[str, str]]:
    m = _SINGLE_DAY_RX.search(user_query or "")
    if not m: return None
    dt = _parse_single_day_literal(m.group(1))
    if not dt: return None
    d = _to_oracle_date(dt)
    return {"start": d, "end": d}

# -------------------------
# Enhanced Date Parser (Integrated from enhanced_date_parser.py)
# -------------------------

def extract_enhanced_date_range(query: str) -> Optional[Dict[str, str]]:
    """
    Enhanced date extraction that handles various date formats from user queries.
    Based on analysis of actual user query patterns.
    """
    if not query:
        return None
        
    query_upper = query.upper()
    
    # Enhanced date patterns from user queries
    enhanced_patterns = [
        # DD/MM/YYYY format (most common)
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy_slash'),
        # DD-MM-YYYY format
        (r'(\d{1,2})-(\d{1,2})-(\d{4})', 'dmy_dash'),
        # DD-MON-YY format (Oracle style)
        (r'(\d{1,2})-([A-Z]{3})-(\d{2,4})', 'dd_mon_yy'),
        # MON-YY format (month-year)
        (r'([A-Z]{3})-(\d{2,4})', 'mon_yy'),
        # Month YYYY format
        (r'([A-Z]{3,9})\s+(\d{4})', 'month_yyyy'),
        # YYYY-MM-DD ISO format
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'iso_date'),
    ]
    
    for pattern, format_type in enhanced_patterns:
        match = re.search(pattern, query_upper)
        if match:
            try:
                date_obj = _parse_enhanced_date_match(match, format_type)
                if date_obj:
                    return _to_enhanced_oracle_date_range(date_obj, format_type)
            except Exception as e:
                logger.warning(f"Enhanced date parsing failed for {match.group(0)}: {e}")
                continue
    
    # Try relative date parsing
    relative_result = _extract_relative_dates(query)
    if relative_result:
        return relative_result
    
    return None

def _parse_enhanced_date_match(match, format_type: str) -> Optional[datetime]:
    """Parse regex match based on format type."""
    
    if format_type == 'dmy_slash' or format_type == 'dmy_dash':
        day, month, year = match.groups()
        return datetime(int(year), int(month), int(day))
        
    elif format_type == 'dd_mon_yy':
        day, month_str, year = match.groups()
        month = _MON_ABBR.get(month_str.upper())
        if not month:
            return None
        year_int = int(year)
        if year_int < 100:
            year_int += 2000
        return datetime(year_int, month, int(day))
        
    elif format_type == 'mon_yy':
        month_str, year = match.groups()
        month = _MON_ABBR.get(month_str.upper())
        if not month:
            return None
        year_int = int(year)
        if year_int < 100:
            year_int += 2000
        return datetime(year_int, month, 1)  # First day of month
        
    elif format_type == 'month_yyyy':
        month_str, year = match.groups()
        month = _MON_ABBR.get(month_str.upper())
        if not month:
            # Try full month names
            month = _MONTH_ALIASES.get(month_str.upper())
            if month:
                month = _MON_ABBR.get(month)
        if not month:
            return None
        return datetime(int(year), month, 1)
        
    elif format_type == 'iso_date':
        year, month, day = match.groups()
        return datetime(int(year), int(month), int(day))
        
    return None

def _to_enhanced_oracle_date_range(date_obj: datetime, format_type: str) -> Dict[str, str]:
    """Convert datetime to Oracle date range."""
    
    if format_type in ['mon_yy', 'month_yyyy']:
        # For month-year formats, create month range
        start_date = date_obj.replace(day=1)
        # Get last day of month
        if date_obj.month == 12:
            end_date = date_obj.replace(year=date_obj.year + 1, month=1, day=1)
        else:
            end_date = date_obj.replace(month=date_obj.month + 1, day=1)
        end_date = end_date - timedelta(days=1)
        
        return {
            'start': f"TO_DATE('{start_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'end': f"TO_DATE('{end_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'type': 'month_range'
        }
    else:
        # For specific dates, use single day
        oracle_date = f"TO_DATE('{date_obj.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')"
        return {
            'start': oracle_date,
            'end': oracle_date,
            'type': 'single_day'
        }

def _extract_relative_dates(query: str) -> Optional[Dict[str, Any]]:
    """Handle relative date expressions like 'last month', 'last 7 days', 'last day'."""
    
    query_lower = query.lower()
    today = datetime.now()
    
    # Handle "last day" - find the most recent date with data
    if 'last day' in query_lower or 'yesterday' in query_lower:
        # For "last day", we'll return a special marker that can be handled by the SQL generator
        # to use (SELECT MAX(PROD_DATE) FROM T_PROD_DAILY)
        return {
            'start': 'LAST_DAY_MARKER',
            'end': 'LAST_DAY_MARKER',
            'type': 'last_day'
        }
    
    # Last week (7 days)
    if 'last week' in query_lower:
        end_date = today
        start_date = today - timedelta(days=7)
        
        return {
            'start': f"TO_DATE('{start_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'end': f"TO_DATE('{end_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'type': 'week_range'
        }
    
    # Last N days patterns
    days_match = re.search(r'last\s+(\d+)\s+days?', query_lower)
    if days_match:
        days = int(days_match.group(1))
        end_date = today
        start_date = today - timedelta(days=days)
        
        return {
            'start': f"TO_DATE('{start_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'end': f"TO_DATE('{end_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'type': 'days_range',
            'days': days
        }
    
    # Last month
    if 'last month' in query_lower:
        if today.month == 1:
            last_month = today.replace(year=today.year - 1, month=12, day=1)
        else:
            last_month = today.replace(month=today.month - 1, day=1)
        
        # Get last day of previous month
        if last_month.month == 12:
            end_date = last_month.replace(year=last_month.year + 1, month=1, day=1)
        else:
            end_date = last_month.replace(month=last_month.month + 1, day=1)
        end_date = end_date - timedelta(days=1)
        
        return {
            'start': f"TO_DATE('{last_month.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'end': f"TO_DATE('{end_date.strftime('%d-%b-%Y')}', 'DD-MON-YYYY')",
            'type': 'month_range'
        }
    
    return None

def _build_date_filter_from_relative_expression(expression: str, date_column: str = 'PROD_DATE') -> Optional[str]:
    """
    Build an appropriate Oracle SQL WHERE clause for relative date expressions.
    """
    # Handle "last day" expressions
    if 'last day' in expression.lower() or 'yesterday' in expression.lower():
        return f"{date_column} = (SELECT MAX({date_column}) FROM T_PROD_DAILY)"
    
    # Handle "last week" expressions
    if 'last week' in expression.lower():
        return f"{date_column} BETWEEN TRUNC(SYSDATE) - 7 AND TRUNC(SYSDATE) - 1"
    
    # Handle "last N days" patterns
    days_match = re.search(r'last\s+(\d+)\s+days?', expression.lower())
    if days_match:
        days = int(days_match.group(1))
        return f"{date_column} BETWEEN TRUNC(SYSDATE) - {days} AND TRUNC(SYSDATE) - 1"
    
    # Handle "last month"
    if 'last month' in expression.lower():
        return f"{date_column} BETWEEN TRUNC(SYSDATE, 'MM') - INTERVAL '1' MONTH AND TRUNC(SYSDATE, 'MM') - INTERVAL '1' DAY"
    
    return None

# replace the old _NAME_LITERAL_RX usage with:
_WHERE_BLOCK_RX = re.compile(r"(?is)\bWHERE\b(.*?)(?=\bGROUP\b|\bORDER\b|\bFETCH\b|\bOFFSET\b|\bLIMIT\b|$)")

def _has_text_literal_predicate(sql: str) -> bool:
    m = _WHERE_BLOCK_RX.search(sql or "")
    if not m:
        return False
    w = m.group(1) or ""

    # strip date/function literals
    w = re.sub(r"(?is)TO_DATE\s*\(\s*'[^']+'\s*,\s*'[^']+'\s*\)", "X", w)
    w = re.sub(r"(?is)TO_CHAR\s*\(\s*[^)]+?\s*,\s*'[^']+'\s*\)", "X", w)

    # any remaining quoted literal likely belongs to a text predicate
    return bool(re.search(r"'[^']+'", w))

def ensure_label_filter(sql: str, user_query: str, selected_db: str) -> str:
    """
    Add a label/code filter inferred from the user's query to the main table in `sql`,
    but only if the SQL does not already contain a text literal predicate.

    Behaviors:
      - Skips English "X-wise" phrasing (meaning "by X") — not a label filter.
      - First, tries code detection (e.g., IDs like CTL-22-004522, barcodes, challan nos.)
        using _extract_id_lookup(). If found, injects an equality-style predicate on a
        suitable text/code column; if not found on base table, tries direct FK parents.
      - Otherwise, scans candidate literals from the question, maps known org names to
        shortcodes, and injects a LIKE/normalized-LIKE predicate on a suitable text column.
        If no base-table match, tries direct FK parents.
    """

    # Fast exits
    if not sql or _has_text_literal_predicate(sql):
        return sql

    # Skip English "X-wise" phrasing ("by X"), not a label
    if re.search(r"\b\w+(?:\s*-\s*|\s+)wise\b", (user_query or "").lower()):
        logger.debug("[ensure_label_filter] skip: '-wise' phrasing detected")
        return sql

    table = extract_main_table(sql or "")
    if not table:
        return sql

    # Helper: inject a predicate at the right spot (before GROUP/ORDER/... or append)
    def _inject_predicate(_sql: str, _pred: str) -> str:
        parts = re.split(r"(?i)\bWHERE\b", _sql, maxsplit=1)
        if len(parts) == 2:
            head, tail = parts[0], (parts[1] or "").strip()
            return f"{head}WHERE {_pred} AND {tail}" if tail else f"{head}WHERE {_pred}"
        m = re.search(r"(?i)\b(GROUP|ORDER|FETCH|OFFSET|LIMIT)\b", _sql or "")
        return (_sql[:m.start()] + f" WHERE {_pred} " + _sql[m.start():]) if m else (_sql + f" WHERE {_pred}")

    # ---------- 1) Code detection path (strict/equality style) ----------
    # Example: CTL-22-004522, barcode 22990000228077, etc.
    try:
        code_info = _extract_id_lookup(user_query)
    except Exception:
        code_info = None

    if code_info:
        code_value = str(code_info.get("value", "")).strip()
        logger.debug("[ensure_label_filter] code_info=%r table=%s", code_info, table)
        if code_value:
            # Try base table first
            best_col = _guess_text_column_for_literal(selected_db, table, code_value)
            if best_col:
                esc = code_value.replace("'", "''")
                norm = re.sub(r"[\s\-]", "", esc).upper()
                pred = (
                    f"( UPPER({best_col}) = UPPER('{esc}') "
                    f"  OR UPPER(REPLACE(REPLACE({best_col},'-',''),' ','')) = UPPER('{norm}') )"
                )
                return _inject_predicate(sql, pred)

            # If no column on the base table matched, try direct FK parents (e.g., JOBS → JOB_CODE)
            try:
                parents = _fk_parents_for_child(selected_db, table)
            except Exception:
                parents = []
            for fk in parents:
                ptab = fk.get("parent_table")
                if not ptab:
                    continue
                ptext = _guess_text_column_for_literal(selected_db, ptab, code_value)
                if not ptext:
                    continue
                # Check that we have all required fields
                child_fk_col = fk.get("child_col")
                parent_pk_col = fk.get("parent_col")
                if not child_fk_col or not parent_pk_col:
                    continue
                # Found a matching text/code column on parent: inject EXISTS join filter
                esc = code_value.replace("'", "''")
                norm = re.sub(r"[\s\-]", "", esc).upper()
                # Build parent-side equality predicate
                parent_pred = (
                    f"( UPPER({ptext}) = UPPER('{esc}') "
                    f"  OR UPPER(REPLACE(REPLACE({ptext},'-',''),' ','')) = UPPER('{norm}') )"
                )
                return _inject_exists_on_parent(
                    sql,
                    child_table=table,
                    parent_table=ptab,
                    parent_text_col=ptext,
                    child_fk_col=child_fk_col,
                    parent_pk_col=parent_pk_col,
                    literal=code_value,
                    parent_pred_override=parent_pred,
                )

    # ---------- 2) Generic literal path (LIKE / normalized LIKE) ----------
    cands = _candidate_literals_from_question(user_query)
    logger.debug("[ensure_label_filter] cands=%r table=%s", cands, table)

    for literal in cands:
        # Map known full names to their short codes (e.g., "Chorka Apparels Ltd" → "CAL")
        mapped = _shortcode_for_org(literal) or literal

        # Try base table first
        best_col = _guess_text_column_for_literal(selected_db, table, mapped)
        if best_col:
            esc = mapped.replace("'", "''")
            norm = re.sub(r"[\s\-]", "", esc).upper()
            pred = (
                f"( UPPER({best_col}) LIKE UPPER('%{esc}%') "
                f"  OR UPPER(REPLACE(REPLACE({best_col},'-',''),' ','')) LIKE UPPER('%{norm}%') )"
            )
            return _inject_predicate(sql, pred)

        # If no column on the base table matched, try direct FK parents (e.g., JOBS → JOB_TITLE)
        try:
            parents = _fk_parents_for_child(selected_db, table)
        except Exception:
            parents = []
        for fk in parents:
            ptab = fk.get("parent_table")
            if not ptab:
                continue
            ptext = _guess_text_column_for_literal(selected_db, ptab, mapped)
            if not ptext:
                continue
            # Found a matching text column on parent: inject EXISTS join filter
            esc = mapped.replace("'", "''")
            norm = re.sub(r"[\s\-]", "", esc).upper()
            parent_pred = (
                f"( UPPER({ptext}) LIKE UPPER('%{esc}%') "
                f"  OR UPPER(REPLACE(REPLACE({ptext},'-',''),' ','')) LIKE UPPER('%{norm}%') )"
            )
            # Check that we have all required fields
            child_fk_col = fk.get("child_col")
            parent_pk_col = fk.get("parent_col")
            if child_fk_col and parent_pk_col:
                return _inject_exists_on_parent(
                    sql,
                    child_table=table,
                    parent_table=ptab,
                    parent_text_col=ptext,
                    child_fk_col=child_fk_col,
                    parent_pk_col=parent_pk_col,
                    literal=mapped,
                    parent_pred_override=parent_pred,
                )

    # Nothing to add
    return sql

def _fk_parents_for_child(selected_db: str, child_table: str) -> List[Dict[str, str]]:
    """
    Get foreign key parent relationships for a child table.
    Returns a list of FK relationships with parent table and column information.
    """
    sql = """
    SELECT pk.table_name parent_table, acc_pk.column_name parent_col, 
           acc.column_name child_col
      FROM all_constraints ac
      JOIN all_cons_columns acc
        ON acc.owner = ac.owner AND acc.constraint_name = ac.constraint_name
      JOIN all_constraints pk
        ON pk.owner = ac.r_owner AND pk.constraint_name = ac.r_constraint_name
      JOIN all_cons_columns acc_pk
        ON acc_pk.owner = pk.owner AND acc_pk.constraint_name = pk.constraint_name 
       AND acc_pk.position = acc.position
     WHERE ac.constraint_type = 'R'
       AND ac.owner = USER
       AND ac.table_name = :child_table
    """
    
    parents = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        try:
            cur.execute(sql, child_table=child_table.upper())
            for parent_table, parent_col, child_col in cur.fetchall():
                parents.append({
                    "parent_table": str(parent_table),
                    "parent_col": str(parent_col),
                    "child_col": str(child_col)
                })
        except Exception as e:
            logger.warning(f"[FK Parents] Failed to get FK parents for {child_table}: {e}")
        finally:
            try: cur.close()
            except: pass
    return parents

def _inject_exists_on_parent(
    sql: str, 
    child_table: str, 
    parent_table: str, 
    parent_text_col: str, 
    child_fk_col: str, 
    parent_pk_col: str, 
    literal: str,
    parent_pred_override: Optional[str] = None
) -> str:
    """
    Inject an EXISTS clause to join a child table with its parent table
    and apply a filter on the parent table's text column.
    """
    # Build the EXISTS predicate
    if parent_pred_override:
        parent_pred = parent_pred_override
    else:
        esc = literal.replace("'", "''")
        norm = re.sub(r"[\s\-]", "", esc).upper()
        parent_pred = (
            f"( UPPER({parent_text_col}) LIKE UPPER('%{esc}%') "
            f"  OR UPPER(REPLACE(REPLACE({parent_text_col},'-',''),' ','')) LIKE UPPER('%{norm}%') )"
        )
    
    exists_clause = (
        f"EXISTS (SELECT 1 FROM {parent_table} "
        f"WHERE {parent_table}.{parent_pk_col} = {child_table}.{child_fk_col} "
        f"AND {parent_pred})"
    )
    
    # Inject the EXISTS clause into the SQL
    parts = re.split(r"(?i)\bWHERE\b", sql, maxsplit=1)
    if len(parts) == 2:
        head, tail = parts[0], (parts[1] or "").strip()
        return f"{head}WHERE {exists_clause} AND {tail}" if tail else f"{head}WHERE {exists_clause}"
    
    # If no WHERE clause, add one before GROUP/ORDER/FETCH/OFFSET/LIMIT or at the end
    m = re.search(r"(?i)\b(GROUP|ORDER|FETCH|OFFSET|LIMIT)\b", sql or "")
    if m:
        return sql[:m.start()] + f" WHERE {exists_clause} " + sql[m.start():]
    
    return sql + f" WHERE {exists_clause}"

# --- table exclude patterns used during runtime metadata build ---
EXCLUDE_TABLE_PATTERNS = [
    p.strip() for p in os.getenv("EXCLUDE_TABLE_PATTERNS", "AI_%").split(",") if p.strip()
]

def _like_to_regex(pat: str) -> re.Pattern:
    # Convert SQL LIKE to regex: % -> .*, _ -> .
    pat = pat.replace(".", r"\.")
    pat = pat.replace("%", ".*").replace("_", ".")
    return re.compile(rf"^{pat}$", re.IGNORECASE)

_EXCLUDE_TABLE_RX = [_like_to_regex(p) for p in EXCLUDE_TABLE_PATTERNS]

def _is_excluded_table(name: str) -> bool:
    return any(rx.match(name) for rx in _EXCLUDE_TABLE_RX)

# ------------------------------------------------------------------------------
# Small, optional cache stubs (no-op by default)
# ------------------------------------------------------------------------------
def _cache_get_result(db: str, sql: str) -> Optional[Dict[str, Any]]:
    return None

def _cache_set_result(db: str, sql: str, columns, rows, *, cache_ok: bool = True) -> None:
    return None

# ------------------------------------------------------------------------------
# Core execution utilities
# ------------------------------------------------------------------------------
def to_jsonable(value):
    if hasattr(value, "read"):
        return value.read()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value

def _set_case_insensitive_session(cursor):
    try:
        cursor.execute("ALTER SESSION SET NLS_COMP=LINGUISTIC")
        cursor.execute("ALTER SESSION SET NLS_SORT=BINARY_CI")
    except Exception as e:
        logger.warning(f"Could not set case-insensitive session: {e}")

def run_sql(sql: str, selected_db: str, *, cache_ok: bool = True, cancellation_token: Optional[Callable[[], bool]] = None) -> List[Dict[str, Any]]:
    cached = _cache_get_result(selected_db, sql)
    if cached:
        logger.debug("[DB] cache_hit=1 db=%s", selected_db)
        return cached["rows"]

    logger.debug("[DB] SQL: %s", (sql or "").replace("\n", " ")[:2000])
    
    # Check for cancellation before executing
    if cancellation_token and cancellation_token():
        from .query_engine import QueryCancellationError
        raise QueryCancellationError("Query was cancelled before execution")

    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        _set_case_insensitive_session(cur)
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [{cols[i]: to_jsonable(r[i]) for i in range(len(cols))} for r in cur]
        
        # Check for cancellation after execution
        if cancellation_token and cancellation_token():
            from .query_engine import QueryCancellationError
            raise QueryCancellationError("Query was cancelled during execution")

    logger.debug("[DB] rows=%d cols=%d", len(rows), len(cols))

    _cache_set_result(selected_db, sql, cols, rows, cache_ok=cache_ok)
    return rows

# ------------------------------------------------------------------------------
# Date normalization & explicit/relative/month-token date-range parsing
# ------------------------------------------------------------------------------
_MON3 = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
_MON_ABBR = {m: i+1 for i, m in enumerate(_MON3)}

def _to_oracle_date(dt: datetime) -> str:
    return f"TO_DATE('{dt.day:02d}-{_MON3[dt.month-1]}-{dt.year}','DD-MON-YYYY')"

_TO_DATE_RX = re.compile(r"(?is)TO_DATE\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")

def _parse_literal_with_format(lit: str, fmt: str) -> Optional[datetime]:
    fmt = (fmt or "").upper().strip()
    py_map = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "MM/DD/YYYY": "%m/%d/%Y",
        "DD/MM/YYYY": "%d/%m/%Y",
        "DD/MM/YY":   "%d/%m/%y",
        "DD-MON-YY":  "%d-%b-%y",
        "DD-MON-YYYY":"%d-%b-%Y",
        "MON-DD-YYYY":"%b-%d-%Y",
    }
    pat = py_map.get(fmt)
    if not pat:
        return None
    try:
        dt = datetime.strptime(lit, pat)
        return dt
    except Exception:
        return None

def normalize_dates(sql: str) -> str:
    def repl(m: re.Match) -> str:
        lit, fmt = m.group(1), m.group(2)
        dt = _parse_literal_with_format(lit, fmt)
        return _to_oracle_date(dt) if dt else m.group(0)
    return _TO_DATE_RX.sub(repl, sql or "")

# --- Explicit date-range detection in natural text --------------------------------
def _parse_day_first_date(s: str) -> Optional[datetime]:
    try:
        s = s.strip()

        # NEW: "24 May 2024" / "24 May 24"
        if _DATE_DMON_SPACE.match(s):
            d_str, mon_str, y_str = s.split()
            d = int(d_str)
            y = int(y_str)
            if y < 100:
                y += 2000 if y < 50 else 1900
            mon3 = mon_str[:3].upper()
            if mon3 in _MON_ABBR:
                return datetime(y, _MON_ABBR[mon3], d)

        # existing: numeric "24/05/2024" or "24-05-2024"
        parts = re.split(r"[/-]", s)
        if len(parts) == 3 and parts[1].isdigit():
            d, m, y = [int(p) for p in parts]
            if y < 100:
                y += 2000 if y < 50 else 1900
            return datetime(y, m, d)
        return None
    except Exception:
        return None

_DATE_RANGE_PATTERNS = [
    re.compile(
        r"\b(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s*(?:is|was|are|were|will\s+be|shall\s+be)\s+between\s+"
        r"(?P<d1>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:and|to)\s+(?P<d2>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s*(?:between|from)\s+"
        r"(?P<d1>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:and|to)\s+(?P<d2>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        re.IGNORECASE,
    ),
]
_DATE_RANGE_STOPWORDS = {"be","is","was","are","were","will","shall"}

def _try_match_date_range(text: str):
    for rx in _DATE_RANGE_PATTERNS:
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

# add near the top (helpers)
_GENERIC_TOKENS_RX = re.compile(r'\b(sewing|cutting|finishing|ironing|knitting|printing|embroidery|washing|qty|quantity|production|output|pieces?|pcs?|floor|line|department|section|unit)\b', re.I)

def _candidate_literals_from_question(q: str) -> list[str]:
    q = q or ""
    # strip dates & months
    q = _SINGLE_DAY_RX.sub(" ", q)
    q = _MON_YYYY_ANY.sub(" ", q)   # catches "Jan 2025", "May-24", etc.
    q = _MONTH_WORD_RX.sub(" ", q)  # catches "Jan", "January"
    q = _YEAR_TOKEN.sub(" ", q)

    # tokenize and drop stopwords/generics
    raw = re.findall(r"[A-Za-z0-9]+", q)
    tokens = [t for t in raw if t.lower() not in _STOPWORDS]
    tokens = [t for t in tokens if not _GENERIC_TOKENS_RX.fullmatch(t)]

    if not tokens:
        return []

    cands: list[str] = []

    # 1) prefer short ALL-CAPS codes (3–6 chars) like "CAL"
    for t in tokens:
        if 3 <= len(t) <= 6 and t.isupper():
            cands.append(t)

    # 2) short phrases for label-y things ("Winner BIP")
    if len(tokens) >= 2:
        cands.append(" ".join(tokens[:2]))
    if len(tokens) >= 3:
        cands.append(" ".join(tokens[:3]))

    # 3) a compact “longest” phrase (cap to keep it sane)
    phrase = " ".join(tokens[:6]).strip()
    if phrase:
        cands.append(phrase)

    # uniq + length rule (allow 3 chars when ALL-CAPS, e.g., CAL)
    out, seen = [], set()
    for c in cands:
        k = c.lower()
        if k in seen:
            continue
        if len(c) >= 4 or (len(c) == 3 and c.isupper()):
            seen.add(k)
            out.append(c)
    return out

def extract_explicit_date_range(user_query: str) -> Optional[Dict[str, str]]:
    hit = _try_match_date_range(user_query)
    if not hit:
        return None
    col, d1, d2 = hit
    return {"column": col, "start": _to_oracle_date(d1), "end": _to_oracle_date(d2)}

# --- NEW: Month-token and relative-date parsing -----------------------------------
def _month_token_to_range(tok: str) -> Optional[Tuple[datetime, datetime]]:
    s = tok.strip()
    m = re.match(r'^([A-Za-z]{3,9})[-\s](\d{2,4})$', s, re.I)
    if not m: return None
    mon_word, yy = m.group(1), m.group(2)
    mon3 = _mon_to_abbr(mon_word) or mon_word[:3].upper()
    if mon3 not in _MON_ABBR: return None
    year = int(yy);  year = 2000 + year if year < 100 else year
    month = _MON_ABBR[mon3]
    start = datetime(year, month, 1)
    end = datetime(year, month, monthrange(year, month)[1])
    return start, end

def _extract_relative_date_range(uq: str) -> Optional[Tuple[datetime, datetime]]:
    uq = uq.lower()
    today = datetime.now().date()
    
    # last 7 days (inclusive) - handle multiple variations
    if "last 7 days" in uq or "last seven days" in uq:
        start = datetime.combine(today - timedelta(days=6), datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        return start, end
        
    # last 30 days
    if "last 30 days" in uq or "last thirty days" in uq:
        start = datetime.combine(today - timedelta(days=29), datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        return start, end
        
    # last month
    if "last month" in uq:
        y, m = (today.year, today.month-1) if today.month > 1 else (today.year-1, 12)
        start = datetime(y, m, 1)
        end = datetime(y, m, monthrange(y, m)[1])
        return start, end
        
    # last quarter
    if "last quarter" in uq:
        q = (today.month-1)//3 + 1
        prev_q = 4 if q == 1 else q-1
        y = today.year-1 if q == 1 else today.year
        m0 = 3*(prev_q-1)+1
        start = datetime(y, m0, 1)
        end = datetime(y, m0+2, monthrange(y, m0+2)[1])
        return start, end
        
    # last year
    if "last year" in uq:
        y = today.year - 1
        start = datetime(y, 1, 1)
        end = datetime(y, 12, 31)
        return start, end
        
    return None

def extract_month_token_range(user_query: str) -> Optional[Dict[str, str]]:
#    m = re.search(r'\b([A-Za-z]{3,9})[-\s](\d{2,4})\b', user_query or "", re.IGNORECASE)
    m = re.search(r'(?<!\d-)\b([A-Za-z]{3,9})[-\s](\d{2,4})\b', user_query or "", re.IGNORECASE)
    if not m: return None
    rng = _month_token_to_range(m.group(0))
    if not rng: return None
    s, e = rng
    return {"start": _to_oracle_date(s), "end": _to_oracle_date(e)}

def extract_relative_date_range(user_query: str) -> Optional[Dict[str, str]]:
    hit = _extract_relative_date_range(user_query or "")
    if not hit:
        return None
    s, e = hit
    return {"start": _to_oracle_date(s), "end": _to_oracle_date(e)}

def apply_date_range_constraint(sql: str, rng: Optional[Dict[str, str]]) -> str:
    if not rng:
        return sql
    col = rng["column"]
    between = f"{col} BETWEEN {rng['start']} AND {rng['end']}"
    parts = re.split(r"(?i)\bWHERE\b", sql or "", maxsplit=1)
    if len(parts) == 2:
        before, after = parts[0], parts[1].strip()
        if after:
            return f"{before}WHERE ({between}) AND ({after})"
        else:
            return f"{before}WHERE {between}"
    m = re.search(r"(?i)\b(GROUP|ORDER|FETCH|OFFSET|LIMIT)\b", sql or "")
    if m:
        return sql[:m.start()] + f" WHERE {between} " + sql[m.start():]
    return sql + f" WHERE {between}"

def extract_year_only_range(user_query: str) -> Optional[Dict[str, str]]:
    m = re.search(_YEAR_TOKEN, user_query or "")
    if not m:
        return None
    y = int(m.group(0))
    return {
        "start": f"TO_DATE('01-JAN-{y}','DD-MON-YYYY')",
        "end":   f"TO_DATE('31-DEC-{y}','DD-MON-YYYY')",
    }


# ------------------------------------------------------------------------------
# Display decisions & wideners
# ------------------------------------------------------------------------------

def determine_display_mode(user_query: str, rows: list) -> str:
    uq = (user_query or "").strip().lower()
    want_table = bool(re.search(r'\b(show|list|display|table|tabular|rows|grid|data)\b', uq))
    want_summary = bool(re.search(r'\b(summary|summarise|summarize|overview|report|insights?|analysis|analyze|describe|explain|update|status)\b', uq))
    
    # Check for specific data requests (should show table even if they start with what/when/where/who)
    specific_data_request = bool(re.search(r'\b(finish date|start date|task number|job.?no|po.?number|style.?ref|buyer.?name|actual.?finish|task.?finish|shipment.?date|user.?id|username|full.?name|email|phone|address|salary|employee|person|user|staff)\b', uq))
    
    # Check for "who is" queries - these should show person details, not just summary
    who_is_query = bool(re.match(r'^\s*who\s+is\b', uq))
    
    # Check for "what is" queries asking for specific values
    what_is_specific = bool(re.match(r'^\s*what\s+is\s+(the\s+)?(finish|start|actual|task|shipment|po|job)', uq))
    
    if not rows:
        return "summary"
    if want_summary and want_table:
        return "both"
    if want_table:
        # Always return "both" when user asks for table/data to ensure a short summary is included
        return "both"
    if want_summary:
        return "summary"
    
    # For questions starting with what/who/when/where/why/how
    if re.match(r'^\s*(who|what|which|when|where|why|how)\b', uq):
        # Show table for "who is" queries (employee lookups)
        if who_is_query:
            return "both"  # Changed from "table" to "both" to include summary
        # Show table for specific "what is" queries
        if what_is_specific:
            return "both"  # Changed from "table" to "both" to include summary
        # Show table if asking for specific data fields
        if specific_data_request:
            return "both"  # Changed from "table" to "both" to include summary
        # Otherwise, show summary
        return "summary"
    
    return "both"

# --- generic-ness detector used by wide projection & widener ------------------
_GENERIC_MAX_TOKENS = 5
_SPECIFIC_HINTS_RX = re.compile(
    r"\b(sum|total|avg|average|count|max|min|rate|percent|percentage|ratio|"
    r"where|=|>=|<=|between|group\s+by|order\s+by|top\s+\d+|limit|fetch)\b",
    re.IGNORECASE
)
_SINGLE_DATE_RX = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")

def _tokenize_words(q: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9]+", q or "")

def _user_requested_time_window(q: str) -> bool:
    _TIME_KEYWORDS_RX = re.compile(
        r"\b(today|yesterday|this (?:week|month|quarter|year)|last (?:week|month|quarter|year)|"
        r"last \d+\s+days?|past \d+\s+days?|last \d+\s+months?|from \d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+(?:to|and)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        re.IGNORECASE,
    )
    _MONTH_WITH_YEAR_RX = re.compile(
        r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|'
        r'aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{2,4}\b', re.I)
    return (
        bool(_TIME_KEYWORDS_RX.search(q or "")) or
        extract_explicit_date_range(q) is not None or
        bool(_MON_YYYY_ANY.search(q or "")) or
        bool(_MONTH_WITH_YEAR_RX.search(q or "")) or
        bool(_SINGLE_DAY_RX.search(q or ""))
    )


def _looks_specific_question(q: str) -> bool:
    uq = (q or "").strip()
    if not uq:
        return False
    if _SPECIFIC_HINTS_RX.search(uq):
        return True
    if _user_requested_time_window(uq) or _SINGLE_DATE_RX.search(uq):
        return True
    toks = _tokenize_words(uq)
    return any(any(ch.isdigit() for ch in t) for t in toks)

def _is_generic_browse(q: str) -> bool:
    toks = _tokenize_words(q)
    if not toks:
        return False
    if len(toks) > _GENERIC_MAX_TOKENS:
        return False
    return not _looks_specific_question(q)

_SELECT_HEAD_RX = re.compile(r"(?is)^\s*select\s+.*?\bfrom\b")
_GROUP_BY_TAIL = re.compile(
    r'(?is)\s+group\s+by\b.*?(?=(\s*\border\b|\s*\bfetch\b|\s*\boffset\b|\s*\blimit\b|$))'
)


def _strip_group_by_with_star(sql: str) -> str:
    if re.match(r'(?is)^\s*select\s+\*\s+from\b', sql or '') and re.search(r'(?is)\bgroup\s+by\b', sql or ''):
        # keep a spacer so "DEPT ORDER BY" doesn’t become "DEPTORDER BY"
        out = _GROUP_BY_TAIL.sub(' ', sql)
        # normalize double spaces that can appear after rewrites
        out = re.sub(r'\s{2,}', ' ', out)
        return out.strip()
    return sql

def enforce_wide_projection_for_generic(user_query: str, sql: str) -> str:
    if not sql or not _is_generic_browse(user_query):
        return sql
    if re.search(r"(?is)^\s*select\s+\*\s+from\b", sql):
        out = sql
    else:
        out = _SELECT_HEAD_RX.sub("SELECT * FROM ", sql, count=1)
    if not re.search(r"(?is)\bfetch\s+first\s+\d+\s+rows\s+only\b", out):
        m = re.search(r"(?is)\b(offset|limit)\b", out)
        if m:
            out = out[:m.start()].rstrip() + " FETCH FIRST 200 ROWS ONLY " + out[m.start():]
        else:
            out = out.rstrip() + " FETCH FIRST 200 ROWS ONLY"
    out = _strip_group_by_with_star(out)
    return out

_FROM_BLOCK_RE = re.compile(r'(?is)\bfrom\b\s+(.*?)\s*(?:\bwhere\b|\bgroup\b|\border\b|\bfetch\b|\bunion\b|\bminus\b|\bintersect\b|$)')

def extract_main_table(sql: str) -> Optional[str]:
    if not sql:
        return None
    m = _FROM_BLOCK_RE.search(sql)
    if not m:
        return None
    block = m.group(1).strip()
    head = re.split(r'(?i)\bjoin\b|\bnatural\b|\bon\b|,', block)[0].strip()
    m2 = re.match(r'\s*(?:"([^"]+)"|([A-Za-z0-9_\.]+))', head)
    if not m2:
        return None
    t = m2.group(1) or m2.group(2)
    return t.strip()

def widen_results_if_needed(rows: list, original_sql: str, selected_db: str, display_mode: str, user_query: str) -> list:
    # Only widen for generic browse-style queries
    generic = _is_generic_browse(user_query)
    if not generic:
        return rows

    # Don’t widen non-tabular or empty results
    if not rows or not isinstance(rows[0], dict):
        return rows

    # Never widen aggregates or grouped queries
    if re.search(r'(?is)\b(sum|avg|count|min|max)\s*\(', original_sql or '') or re.search(r'(?is)\bgroup\s+by\b', original_sql or ''):
        return rows

    table = extract_main_table(original_sql or "")
    if not table:
        return rows

    # Preserve original WHERE when widening
    m = re.search(r'(?is)\bwhere\b(.*?)(?=\bgroup\b|\border\b|\bfetch\b|\boffset\b|\blimit\b|$)', original_sql or '')
    widened_sql = f"SELECT * FROM {table}"
    if m and m.group(1).strip():
        widened_sql += f" WHERE {m.group(1).strip()}"
    widened_sql += " FETCH FIRST 200 ROWS ONLY"

    try:
        widened = run_sql(widened_sql, selected_db, cache_ok=False)
        # If widening didn’t help (no rows), keep original
        return widened or rows
    except Exception as e:
        logger.warning(f"Widen failed for {table}: {e}")
        return rows

# ------------------------------------------------------------------------------
# Descriptive summarizer (pure Python – stable)
# ------------------------------------------------------------------------------
def summarize_results(rows: list, user_query: str) -> str:
    """
    Generate a very concise, plain-language summary (1–2 sentences) focused on the user's ask.
    Avoid matrices, lists, totals, and unrelated KPIs.
    """
    from decimal import Decimal
    import re

    # No data / scalar single-value cases
    if not rows:
        return "No data found matching your criteria."
    if not isinstance(rows[0], dict):
        return f"Found {len(rows)} records."
    if len(rows) == 1 and len(rows[0]) == 1:
        k, v = next(iter(rows[0].items()))
        if isinstance(v, Decimal):
            v = float(v)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            s = f"{v:,.2f}".rstrip("0").rstrip(".")
        else:
            s = str(v)
        return f"{k.replace('_',' ').title()}: {s}"

    # Helper to safely format one number
    def fmt_num(x):
        if x is None:
            return "—"
        if isinstance(x, Decimal):
            x = float(x)
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            s = f"{x:,.2f}".rstrip("0").rstrip(".")
            return s
        return str(x)

    cols = list(rows[0].keys())

    # If the user asked for an average explicitly (avg/average), compute ONLY that for the most
    # relevant metric column and return one short sentence. Prefer columns containing 'EFF' or 'EFFICIENCY'.
    uq = (user_query or "").lower()
    asked_for_avg = bool(re.search(r"\b(avg|average)\b", uq))

    if asked_for_avg:
        # Pick a metric column: prioritize efficiency-like columns, otherwise first numeric
        metric_col = None
        eff_candidates = [c for c in cols if re.search(r"eff|efficiency", c, re.I)]
        if eff_candidates:
            metric_col = eff_candidates[0]
        else:
            # find first numeric-looking column
            for c in cols:
                for r in rows:
                    v = r.get(c)
                    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
                        metric_col = c
                        break
                if metric_col:
                    break

        if metric_col:
            vals = []
            for r in rows:
                v = r.get(metric_col)
                if isinstance(v, Decimal):
                    v = float(v)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append(float(v))
            if vals:
                avg_val = sum(vals) / len(vals)
                avg_txt = fmt_num(avg_val)
                # Try to recover a category label to optionally add lowest/highest name
                label_col = None
                for c in cols:
                    if re.search(r"name|label|desc|description|floor|buyer|line", c, re.I):
                        label_col = c; break
                # Identify lows/highs only for context, not as a list
                low_name = high_name = None
                if label_col:
                    try:
                        low_row = min(rows, key=lambda r: (float(r.get(metric_col)) if isinstance(r.get(metric_col),(int,float,Decimal)) else float('inf')))
                        high_row = max(rows, key=lambda r: (float(r.get(metric_col)) if isinstance(r.get(metric_col),(int,float,Decimal)) else float('-inf')))
                        low_name = low_row.get(label_col)
                        high_name = high_row.get(label_col)
                    except Exception:
                        pass
                # Build one or two short sentences
                base = f"Average {metric_col.replace('_',' ').title()} is {avg_txt}."
                if low_name and high_name and str(low_name) != "inf" and str(high_name) != "-inf":
                    return f"{base} Lowest: {low_name}; highest: {high_name}."
                return base

    # Fallback: generic one-liner
    return f"Found {len(rows)} records. Focus on the key metric requested and avoid unrelated totals."
# ------------------------------------------------------------------------------
# Plan → SQL (deterministic)
# ------------------------------------------------------------------------------
from functools import lru_cache

@lru_cache(maxsize=512)
def _get_table_colmeta(selected_db: str, table: str) -> Dict[str, str]:
    """
    Return {COL_NAME_UPPER: DATA_TYPE_UPPER} for a table.
    Supports OWNER.TABLE too.
    """
    owner = None
    tbl = table
    if "." in table:
        owner, tbl = table.split(".", 1)

    sql = (
        "SELECT column_name, data_type FROM user_tab_columns WHERE table_name = :tbl"
        if not owner else
        "SELECT column_name, data_type FROM all_tab_columns WHERE owner=:own AND table_name=:tbl"
    )
    meta: Dict[str, str] = {}
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        try:
            if owner:
                cur.execute(sql, own=owner.upper(), tbl=tbl.upper())
            else:
                cur.execute(sql, tbl=tbl.upper())
            for name, dtype in cur.fetchall():
                meta[str(name).upper()] = str(dtype).upper()
        finally:
            try: cur.close()
            except: pass
    return meta

def _is_numeric(selected_db: str, table: str, col: str) -> bool:
    meta = _get_table_colmeta(selected_db, table)
    dt = meta.get(col.upper(), "")
    return any(k in dt for k in ("NUMBER","INTEGER","FLOAT","BINARY"))

def _is_char(selected_db: str, table: str, col: str) -> bool:
    dt = _get_table_colmeta(selected_db, table).get(col.upper(), "")
    return any(k in dt for k in ("CHAR","VARCHAR","NCHAR","CLOB"))

def _is_date(selected_db: str, table: str, col: str) -> bool:
    meta = _get_table_colmeta(selected_db, table)
    dt = meta.get(col.upper(), "")
    return "DATE" in dt or "TIMESTAMP" in dt

def _quote_value(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, list):
        parts = ", ".join(_quote_value(x) for x in v)
        return f"({parts})"
    s = str(v)
    return "'" + s.replace("'", "''") + "'"

def pick_best_date_column(table: str, rng: Dict[str, str], selected_db: str) -> Optional[str]:
    """Probe candidate date columns to see which one has rows in the range."""
    meta = _get_table_colmeta(selected_db, table)
    date_cols = [c for c, dt in meta.items() if "DATE" in dt or "TIMESTAMP" in dt]
    if not date_cols:
        return None
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        for c in date_cols:
            probe = f"""
            SELECT 1 FROM {table}
             WHERE {c} BETWEEN {rng['start']} AND {rng['end']}
               AND ROWNUM = 1
            """
            try:
                cur.execute(probe)
                r = cur.fetchone()
                if r:
                    try: cur.close()
                    except: pass
                    return c
            except Exception:
                continue
        try: cur.close()
        except: pass
    return None

def build_sql_from_plan(plan: Dict[str, Any], selected_db: str, user_query: str) -> str:
    """
    Compose SELECT from a validated plan.
    Supports:
      - dims: strings OR {"expr": "TO_CHAR(date_col,'MON-YY')", "as": "MONTH"}
      - metrics: numeric cols
      - optional filters, date range (from user question), order_by, limit
      - (optional) two-table join if plan includes {"tables":[...], "joins":[{"left":"T1.COL","right":"T2.COL","type":"INNER"}]}

    Note: dims/metrics/date_col are validated against the FIRST table (see _validate_plan).
          Filters may reference columns from either side of a 2-table join; in SQL we will
          qualify those columns with their owning table to avoid ambiguity and check types
          against the correct table.
    """
    table = plan.get("table")
    dims = plan.get("dims") or []
    metrics = plan.get("metrics") or []
    date_col = plan.get("date_col") or None
    filters = plan.get("filters") or []
    order_by = plan.get("order_by") or []
    limit = plan.get("limit", None)

    asked_window = _user_requested_time_window(user_query)
    # Optional multi-table support (strict planner/validator governs correctness)
    tables_in_plan: List[str] = plan.get("tables") or []
    joins = plan.get("joins") or []

    # Helpers to resolve a filter column's owning table (when joined) and qualify it
    def _owner_table_for(col: str) -> Optional[str]:
        candidates = tables_in_plan[:] if tables_in_plan else ([table] if table else [])
        for tt in candidates:
            if col and col.upper() in _get_table_colmeta(selected_db, tt):
                return tt
        return None

    def _qcol(col: str) -> str:
        owner = _owner_table_for(col)
        return f"{owner}.{col}" if owner and tables_in_plan else col

    select_parts: List[str] = []
    group_by_parts: List[str] = []
    where_parts: List[str] = []

    # Decide base table early (we need this to validate dims/metrics later)
    type_table = table or (tables_in_plan[0] if tables_in_plan else None)

    # -----------------
    # Filters (owner-aware & qualified)
    # -----------------
    for f in filters:
        col, op, val = f["col"], f["op"], f["val"]
        parsed = _parse_tochar_expr(col) if isinstance(col, str) else None

        if parsed:
            # Handle TO_CHAR(<date_col>,'FMT') predicates safely (expression already unambiguous)
            dcol, fmt = parsed
            if isinstance(val, str) and op == "=":
                sval = val.strip()
                # Normalize MON-YY <-> MON-YYYY as needed
                if re.match(r"^[A-Za-z]{3}-\d{4}$", sval, re.I) and fmt == "MON-YY":
                    col = f"TO_CHAR({dcol}, 'MON-YYYY')"
                elif re.match(r"^[A-Za-z]{3}-\d{2}$", sval, re.I) and fmt == "MON-YYYY":
                    col = f"TO_CHAR({dcol}, 'MON-YY')"
                where_parts.append(f"UPPER({col}) = UPPER({_quote_value(sval)})")
            elif op == "LIKE":
                lit = val
                if isinstance(val, str) and not any(ch in val for ch in ("%","_")):
                    lit = f"%{val.strip()}%"
                where_parts.append(f"UPPER({col}) LIKE UPPER({_quote_value(lit)})")
            elif op == "IN" and isinstance(val, list):
                where_parts.append(f"{col} IN {_quote_value(val)}")
            else:
                where_parts.append(f"{col} {op} {_quote_value(val)}")

        else:
            # Non-TO_CHAR columns — resolve owner for type checks and qualification
            if op == "BETWEEN" and isinstance(val, list) and len(val) == 2:
                v1, v2 = val[0], val[1]
                owner_tbl = _owner_table_for(col)
                # Date-safe BETWEEN (avoid implicit NLS conversions)
                if owner_tbl and _is_date(selected_db, owner_tbl, col):
                    def _date_lit(s: str) -> str:
                        s = str(s).strip()
                        if _DATE_YMD.match(s):
                            return f"DATE '{s}'"
                        if _DATE_DMON.match(s):
                            fmt = "DD-MON-YYYY" if len(s.split('-')[-1]) == 4 else "DD-MON-YY"
                            return f"TO_DATE('{s}','{fmt}')"
                        if _DATE_DMON_SPACE.match(s):
                            d_str, mon_str, y_str = s.split()
                            mon3 = mon_str[:3].upper()
                            fmt = "DD-MON-YYYY" if len(y_str) == 4 else "DD-MON-YY"
                            lit = f"{int(d_str):02d}-{mon3}-{y_str}"
                            return f"TO_DATE('{lit}','{fmt}')"
                        if _DATE_DMY.match(s):
                            fmt = "DD/MM/YYYY" if len(s.split('/')[-1]) == 4 else "DD/MM/YY"
                            return f"TO_DATE('{s}','{fmt}')"
                        # fallback: keep as-is (won't break validation)
                        return _quote_value(s)
                    where_parts.append(
                        f"{_qcol(col)} BETWEEN {_date_lit(v1)} AND {_date_lit(v2)}"
                    )
                else:
                    where_parts.append(f"{_qcol(col)} BETWEEN {_quote_value(v1)} AND {_quote_value(v2)}")
                continue
            elif op == "LIKE":
                owner_tbl = _owner_table_for(col)
                if owner_tbl and _is_date(selected_db, owner_tbl, col) and isinstance(val, str):
                    sval = val.strip()
                    if not asked_window and (_is_single_day_literal(sval) or _MON_YYYY_ANY.match(sval) or _YEAR_TOKEN.match(sval)):
                        # avoid accidental single-day/month/year LIKE on date col if no window requested
                        continue

                    lit = val  # default literal for LIKE
                    if _MON_YYYY_ANY.match(sval):
                        year = (sval.split()[-1] if " " in sval else sval.split("-")[-1])
                        fmt = "MON-YYYY" if len(year) == 4 else "MON-YY"
                        sval = sval.replace(" ", "-")
                        lit = sval
                    elif _MON_YYYY.match(sval):
                        fmt = "MON-YYYY" if len(sval.split("-")[1]) == 4 else "MON-YY"
                        lit = sval
                    elif _DATE_DMON_SPACE.match(sval):
                        d_str, mon_str, y_str = sval.split()
                        mon3 = mon_str[:3].upper()
                        fmt = "DD-MON-YYYY" if len(y_str) == 4 else "DD-MON-YY"
                        lit = f"{int(d_str):02d}-{mon3}-{y_str}"
                    elif _DATE_YMD.match(sval):
                        fmt = "YYYY-MM-DD"
                    elif _DATE_DMY.match(sval):
                        fmt = "DD/MM/YYYY" if len(sval.split("/")[-1]) == 4 else "DD/MM/YY"
                    else:
                        fmt = "DD-MON-YYYY"

                    if isinstance(lit, str) and not any(ch in lit for ch in ("%","_")):
                        lit = f"%{lit.strip()}%"
                    where_parts.append(
                        f"UPPER(TO_CHAR({_qcol(col)}, '{fmt}')) LIKE UPPER({_quote_value(lit)})"
                    )
                else:
                    lit = val
                    if isinstance(val, str) and not any(ch in val for ch in ("%","_")):
                        lit = f"%{val.strip()}%"
                    where_parts.append(f"UPPER({_qcol(col)}) LIKE UPPER({_quote_value(lit)})")

            else:
                # Equality / inequality etc.
                owner_tbl = _owner_table_for(col)
                if owner_tbl and _is_date(selected_db, owner_tbl, col):
                    # Skip planner’s JSON placeholders for dates (e.g., {"$gte": ...})
                    if isinstance(val, dict):
                        continue  # rely on rng (explicit/month/relative) added later

                    if not isinstance(val, str):
                        continue  # unsafe equality on date without a parsable string

                    sval = val.strip()

                    # If user did not ask for a window, drop single-day/month/year equals
                    if (not asked_window and (op in ("=", "LIKE")) and
                        (_is_single_day_literal(sval) or _MON_YYYY_ANY.match(sval) or _YEAR_TOKEN.match(sval))):
                        continue

                    if _DATE_YMD.match(sval):
                        where_parts.append(f"{_qcol(col)} {op} DATE '{sval}'")
                    elif _DATE_DMON.match(sval):
                        fmt = "DD-MON-YYYY" if len(sval.split('-')[-1]) == 4 else "DD-MON-YY"
                        where_parts.append(f"{_qcol(col)} {op} TO_DATE('{sval}','{fmt}')")
                    elif _DATE_DMON_SPACE.match(sval):
                        d_str, mon_str, y_str = sval.split()
                        mon3 = mon_str[:3].upper()
                        fmt = "DD-MON-YYYY" if len(y_str) == 4 else "DD-MON-YY"
                        lit = f"{int(d_str):02d}-{mon3}-{y_str}"
                        where_parts.append(f"{_qcol(col)} {op} TO_DATE('{lit}','{fmt}')")
                    elif _DATE_DMY.match(sval):
                        fmt = "DD/MM/YYYY" if len(sval.split('/')[-1]) == 4 else "DD/MM/YY"
                        where_parts.append(f"{_qcol(col)} {op} TO_DATE('{sval}','{fmt}')")
                    elif _MON_YYYY_ANY.match(sval) and op == "=":
                        year = (sval.split()[-1] if " " in sval else sval.split("-")[-1])
                        fmt = "MON-YYYY" if len(year) == 4 else "MON-YY"
                        sval_norm = sval.replace(" ", "-")
                        where_parts.append(f"UPPER(TO_CHAR({_qcol(col)}, '{fmt}')) = UPPER({_quote_value(sval_norm)})")
                    elif _YEAR_TOKEN.match(sval):
                        y = int(sval)
                        where_parts.append(
                            f"{_qcol(col)} BETWEEN TO_DATE('01-JAN-{y}','DD-MON-YYYY') "
                            f"AND TO_DATE('31-DEC-{y}','DD-MON-YYYY')"
                        )
                    # IMPORTANT: do NOT fall back to a generic quoted compare for date cols
                else:
                    where_parts.append(f"{_qcol(col)} {op} {_quote_value(val)}")
    # --- before deriving rng ---
    # If a date BETWEEN already exists, skip adding rng to avoid duplicates
    has_date_between = False
    if date_col:
        qd = _qcol(date_col)
        for w in where_parts:
            if re.search(rf'(?i)\b{re.escape(qd)}\b\s+BETWEEN\b', w):
                has_date_between = True
                break
    # User explicit date range (explicit > single-day > month-token > relative)
    rng = (None if has_date_between else
        extract_explicit_date_range(user_query)
        or extract_single_day_range(user_query)
        or extract_month_token_range(user_query)
        or extract_relative_date_range(user_query)
    )

    # If no explicit/month/relative/year, try a single-day token (e.g., 21-AUG-25)
    if not rng:
        rng2 = extract_single_day_range(user_query)
        if rng2:
            candidate_table = table or (tables_in_plan[0] if tables_in_plan else None)
            if candidate_table:
                if date_col and _is_date(selected_db, candidate_table, date_col):
                    rng = {"column": date_col, "start": rng2["start"], "end": rng2["end"]}
                else:
                    best = pick_best_date_column(candidate_table, rng2, selected_db)
                    if best:
                        rng = {"column": best, "start": rng2["start"], "end": rng2["end"]}

    # Optional deterministic default time policy
    if not rng and not asked_window and DEFAULT_TIME_DAYS > 0:
        today = datetime.now().date()
        start = datetime(today.year, today.month, today.day) - timedelta(days=DEFAULT_TIME_DAYS - 1)
        end   = datetime(today.year, today.month, today.day)
        rng2 = {"start": _to_oracle_date(start), "end": _to_oracle_date(end)}
        candidate_table = table or (tables_in_plan[0] if tables_in_plan else None)
        if candidate_table:
            if date_col and _is_date(selected_db, candidate_table, date_col):
                rng = {"column": date_col, "start": rng2["start"], "end": rng2["end"]}
            else:
                best = pick_best_date_column(candidate_table, rng2, selected_db)
                if best:
                    rng = {"column": best, "start": rng2["start"], "end": rng2["end"]}

    # If we had explicit range but no column yet, choose now
    if rng and "column" not in rng:
        candidate_table = table or (tables_in_plan[0] if tables_in_plan else None)
        if candidate_table:
            if date_col and _is_date(selected_db, candidate_table, date_col):
                rng = {"column": date_col, "start": rng["start"], "end": rng["end"]}
            else:
                best = pick_best_date_column(candidate_table, rng, selected_db)
                if best:
                    rng = {"column": best, "start": rng["start"], "end": rng["end"]}
                else:
                    rng = None

    # If we added a month/date/year range, remove redundant predicates on the same date column
    if rng:
        _RE_TOCHAR_ANY = re.compile(
            r"TO_CHAR\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*'([A-Za-z\-]+)'\s*\)",
            re.IGNORECASE,
        )
        rng_col = (rng.get("column") or "").upper()

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "")).strip().upper()

        cleaned = []
        for w in where_parts:
            wn = _norm(w)
            drop = False

            # 3a) Drop TO_CHAR(MON-YY|MON-YYYY) equality on the same date column
            mm = _RE_TOCHAR_ANY.search(w)
            if mm:
                dcol = (mm.group(1) or "").upper()
                if dcol == rng_col and re.search(r"=\s*UPPER\('[A-Za-z]{3}-\d{2,4}'\)", w, re.IGNORECASE):
                    drop = True

            # 3b) Drop direct single-day equality on the same date column
            if not drop:
                if wn.startswith(f"{rng_col} = DATE '") and re.search(r"DATE '\d{4}-\d{2}-\d{2}'$", wn):
                    drop = True
                elif wn.startswith(f"{rng_col} = TO_DATE("):
                    drop = True
                elif wn.startswith(f"{rng_col} = '"):
                    drop = True

            # 3c) NEW — when a window is applied, drop date predicates on *other* date columns
            if not drop:
                other_date_pred = re.search(
                    r"(?is)\b([A-Za-z_][A-Za-z0-9_\.]*)\s*(=|<=|>=|<|>|LIKE)\s*"
                    r"(?:DATE\s*'\d{4}-\d{2}-\d{2}'|TO_DATE\s*\(|UPPER\s*\(\s*TO_CHAR\s*\()",
                    w,
                )
                if other_date_pred:
                    other_col = other_date_pred.group(1).split(".")[-1].upper()
                    if other_col != rng_col:
                        drop = True

            if not drop:
                cleaned.append(w)

        where_parts = cleaned

    # Dims: strings or expr-as
    dim_aliases = set()
    for d in dims:
        if isinstance(d, str):
            select_parts.append(d); group_by_parts.append(d)
        elif isinstance(d, dict) and "expr" in d:
            parsed = _parse_tochar_expr(d["expr"])
            if not parsed:
                raise ValueError(f"Invalid TO_CHAR dimension: {d}")
            col, fmt = parsed
            candidate_table = table or (tables_in_plan[0] if tables_in_plan else None)
            if not candidate_table:
                raise ValueError("No table provided for TO_CHAR dimension")
            if not _is_date(selected_db, candidate_table, col):
                raise ValueError(f"TO_CHAR used on non-date column: {col}")
            alias = d.get("as")
            if alias:
                select_parts.append(f"TO_CHAR({col}, '{fmt}') AS {alias}")
                dim_aliases.add(alias)
            else:
                select_parts.append(f"TO_CHAR({col}, '{fmt}')")
            group_by_parts.append(f"TO_CHAR({col}, '{fmt}')")
        else:
            raise ValueError("Unsupported dim type")

    # Metrics
    type_table = table or (tables_in_plan[0] if tables_in_plan else None)
    if metrics:
        for m in metrics:
            if type_table and _is_numeric(selected_db, type_table, m):
                select_parts.append(f"SUM({m}) AS {m}")
            else:
                select_parts.append(f"COUNT(*) AS ROWS")
    else:
        if not select_parts:
            select_parts.append("*")

    # Build base FROM (support optional 2-table join)
    if tables_in_plan and joins:
        tnames = [t for t in tables_in_plan if t][:2]
        if len(tnames) < 2:
            base_from = f"FROM {tnames[0]}" if tnames else f"FROM {table}"
        else:
            j = joins[0]
            jtype = (j.get("type") or "INNER").upper()
            left_key = j.get("left")
            right_key = j.get("right")
            if not (left_key and right_key):
                base_from = f"FROM {tnames[0]}"
            else:
                base_from = f"FROM {tnames[0]} {jtype} JOIN {tnames[1]} ON {left_key} = {right_key}"
    else:
        base_from = f"FROM {table}"

    sql = f"SELECT {', '.join(select_parts)} {base_from}"

    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if rng:
        sql = apply_date_range_constraint(sql, rng)

    # GROUP BY (only when both dims and metrics exist)
    if metrics and group_by_parts:
        sql += " GROUP BY " + ", ".join(group_by_parts)

    # ORDER BY (only by selected metric/dim or alias)
    if order_by:
        safe_keys = set(metrics) | set([d for d in dims if isinstance(d, str)]) | dim_aliases
        order_items = []
        for ob in order_by:
            key = ob.get("key"); direction = ob.get("dir", "DESC")
            if key in safe_keys:
                order_items.append(f"{key} {direction}")
        if order_items:
            sql += " ORDER BY " + ", ".join(order_items)

    # LIMIT (FETCH FIRST N ROWS ONLY)
    if limit is not None:
        try:
            n = int(limit)
        except Exception:
            n = 200
        n = min(max(n, 1), 500)
        sql += f" FETCH FIRST {n} ROWS ONLY"

    return sql

# ------------------------------------------------------------------------------
# Type/predicate guards
# ------------------------------------------------------------------------------
_ALIAS_ITEM_RX = re.compile(r'(?is)\bfrom\b\s+(.*?)\s*(?:\bwhere\b|\bgroup\b|\border\b|\bfetch\b|$)')
_SPLIT_ITEMS_RX = re.compile(r'(?is)\bjoin\b|,')
_TABLE_ALIAS_RX = re.compile(r'(?is)^\s*(?:"([^"]+)"|([A-Za-z0-9_\.]+))\s*(?:AS\s+)?([A-Za-z0-9_]+)?')

def _parse_tables_and_aliases(sql: str) -> Dict[str, str]:
    out = {}
    m = _ALIAS_ITEM_RX.search(sql or "")
    if not m: return out
    block = m.group(1)
    for it in [s.strip() for s in _SPLIT_ITEMS_RX.split(block) if s.strip()]:
        mm = _TABLE_ALIAS_RX.match(it)
        if not mm: continue
        table = mm.group(1) or mm.group(2)
        alias = (mm.group(3) or table.split(".")[-1]).upper()
        out[alias] = table
    return out

def enforce_predicate_type_compat(sql: str, selected_db: str) -> None:
    alias2table = _parse_tables_and_aliases(sql)
    def dtype(alias, col):
        tbl = alias2table.get(alias.upper()) if alias else (next(iter(alias2table.values())) if len(alias2table)==1 else None)
        if not tbl: return None
        return _get_table_colmeta(selected_db, tbl).get(col.upper(), "")
    # TRUNC(col)
    for m in re.finditer(r'(?is)TRUNC\s*\(\s*(?:"([^"]+)"\.)?([A-Za-z0-9_]+)\s*\)', sql or ""):
        dt = dtype(m.group(1), m.group(2)) or ""
        if "DATE" not in dt and "TIMESTAMP" not in dt:
            raise ValueError(f"TRUNC used on non-date column {m.group(2)}")
    # col LIKE ...
    for m in re.finditer(r'(?is)\b(?:"([^"]+)"\.)?([A-Za-z0-9_]+)\s+LIKE\s+', sql or ""):
        dt = dtype(m.group(1), m.group(2)) or ""
        if not any(k in dt for k in ("CHAR","VARCHAR","NCHAR","CLOB")):
            raise ValueError(f"LIKE used on non-text column {m.group(2)}")
    # col = TO_DATE(...)
    for m in re.finditer(r'(?is)\b(?:"([^"]+)"\.)?([A-Za-z0-9_]+)\s*(=|<>|<=|>=|<|>|between)\s*TO_DATE\s*\(', sql or ""):
        dt = dtype(m.group(1), m.group(2)) or ""
        if "DATE" not in dt and "TIMESTAMP" not in dt:
            raise ValueError(f"TO_DATE compared to non-date column {m.group(2)}")

_ORPHAN_LITERAL_WHERE = re.compile(r"(?is)\bwhere\s*'[^']+'\s*(?:group|order|fetch|offset|limit|$)")
def _has_orphan_literal_where(sql: str) -> bool:
    return bool(_ORPHAN_LITERAL_WHERE.search(sql or ""))

def is_valid_sql(sql: str, source_id: str) -> bool:
    s = (sql or "").strip()
    if not s.lower().startswith("select"): return False
    if ";" in s: return False
    if re.search(r":\w+", s, re.IGNORECASE): return False
    if len(s) > 100000: return False
    if _has_orphan_literal_where(s): return False
    try:
        with connect_to_source(source_id) as (conn, _):
            cursor = conn.cursor()
            cursor.prepare(s)  # early sanity check
            return True
    except Exception as e:
        logger.warning(f"[Validation Fail] {e}")
        return False

# ------------------------------------------------------------------------------
# Value-aware WHERE rewrite for human labels
# ------------------------------------------------------------------------------
from functools import lru_cache as _lru_cache_cols

@_lru_cache_cols(maxsize=512)
def _get_table_columns(selected_db: str, table: str) -> Set[str]:
    cols: Set[str] = set()
    owner = None
    tbl = table
    if "." in table:
        owner, tbl = table.split(".", 1)
    sql = (
        "SELECT column_name FROM user_tab_columns WHERE table_name=:tbl"
        if not owner else
        "SELECT column_name FROM all_tab_columns WHERE owner=:own AND table_name=:tbl"
    )
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        try:
            if owner:
                cur.execute(sql, own=owner.upper(), tbl=tbl.upper())
            else:
                cur.execute(sql, tbl=tbl.upper())
            for (c,) in cur.fetchall():
                cols.add(str(c).upper())
        finally:
            try: cur.close()
            except: pass
    return cols

@lru_cache(maxsize=512)
def _guess_text_column_for_literal(selected_db: str, table: str, literal: str) -> Optional[str]:
    meta = _get_table_colmeta(selected_db, table)
    text_cols = [c for c, dt in meta.items()
                 if any(k in dt for k in ("CHAR", "VARCHAR", "NCHAR", "CLOB"))]
    if not text_cols:
        return None

    esc_full = literal.upper().replace("'", "''")
    tokens = [t for t in re.findall(r"[A-Za-z0-9]+", literal.upper()) if len(t) >= 2]
    tokens = [t for t in tokens if t.lower() not in _STOPWORDS]
    tokens = [t for t in tokens if not _GENERIC_TOKENS_RX.fullmatch(t)]

    def _score(col: str, cur) -> int:
        try:
            cur.execute(f"SELECT 1 FROM {table} WHERE UPPER({col}) LIKE '%{esc_full}%' AND ROWNUM = 1")
            if cur.fetchone(): return 2
        except: pass
        if 1 <= len(tokens) <= 4:
            and_clause = " AND ".join([f"UPPER({col}) LIKE '%{t}%'" for t in tokens])
            try:
                cur.execute(f"SELECT 1 FROM {table} WHERE {and_clause} AND ROWNUM = 1")
                if cur.fetchone(): return 1
            except: pass
        return 0

#    best = None; best_score = -1
    best = None; best_score = 0
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        for c in text_cols:
            s = _score(c, cur)
            if s > best_score:
                best, best_score = c, s
                # hard-prefer label-ish columns when matched
                if s >= 1 and re.search(r'(FLOOR|LINE|PM_OR_APM|NAME|TITLE|DESC|DESCRIPTION|LABEL)$', c, re.I):
                    break
    # Only trust a column if we actually saw a hit in the DB
    return best if best_score >= 1 else None

def value_aware_text_filter(sql: str, selected_db: str) -> str:
    """
    Make human-entered labels robust to space/hyphen differences.
    Rewrites the first simple text predicate into:
      UPPER(col) LIKE '%VAL%' OR UPPER(REPLACE(REPLACE(col,'-',''),' ','')) LIKE '%NORM%'
    If the matched predicate is already inside (...), we do NOT add another pair of ().
    Also ensures the WHERE block has balanced parentheses before the next clause.
    """
    table = extract_main_table(sql or "")
    if not table:
        return sql

    m = _WHERE_BLOCK_RX.search(sql or "")
    if not m:
        return sql

    w_start, w_end = m.span(1)
    where_part = m.group(1)

    # Match a single column =/LIKE 'literal' (tolerate UPPER(...) on either side)
    pred_rx = re.compile(
        r"(?is)(?<!\w)(?:UPPER\(\s*)?([A-Za-z_][A-Za-z0-9_\.]*)\s*(?:\)\s*)?"
        r"(=|LIKE)\s*(?:UPPER\(\s*)?'([^']+)'(?:\)\s*)?(?=\s*[)\s]|$)"
    )
    pm = pred_rx.search(where_part)
    if not pm:
        return sql

    raw_val = pm.group(3)
    esc = raw_val.replace("'", "''")
    esc_like = esc if any(ch in esc for ch in ("%","_")) else f"%{esc}%"
    norm = re.sub(r"[\s\-]", "", esc).upper()

    best_col = _guess_text_column_for_literal(selected_db, table, raw_val)
    if not best_col:
        return sql

    # Enhanced pattern matching for company names in floor names
    # If the value contains company identifiers, create additional flexible patterns
    additional_patterns = []
    company_identifiers = ['CAL', 'WINNER', 'BIP']
    
    # Check if this is a company-related filter
    if any(company in raw_val.upper() for company in company_identifiers):
        # Add a more flexible pattern to match company identifiers anywhere in the value
        for company in company_identifiers:
            if company in raw_val.upper():
                additional_patterns.append(f"UPPER({best_col}) LIKE UPPER('%{company}%')")
                break  # Only add one company pattern to avoid over-complication

    # Build predicate WITHOUT outer () — we’ll add them only if the match isn’t already wrapped
    pred_core = (
        f"UPPER({best_col}) LIKE UPPER('{esc_like}') "
        f"OR UPPER(REPLACE(REPLACE({best_col},'-',''),' ','')) LIKE UPPER('%{norm}%')"
    )
    
    # Add additional company patterns if applicable
    if additional_patterns:
        pred_core = " OR ".join([pred_core] + additional_patterns)

    s, e = pm.span()
    left = where_part[:s]
    right = where_part[e:]

    # Is the matched predicate already inside parentheses?
    left_trim  = left.rstrip()
    right_trim = right.lstrip()
    already_wrapped = left_trim.endswith("(") and right_trim.startswith(")")

    replacement = pred_core if already_wrapped else f"({pred_core})"
    new_where = left + replacement + right

    # Final safety: ensure WHERE block has balanced parentheses
    opens = new_where.count("(")
    closes = new_where.count(")")
    if closes < opens:
        new_where = new_where + (")" * (opens - closes))

    # Keep a space before the next clause token (GROUP|ORDER|...)
    if not new_where.endswith(" "):
        new_where = new_where + " "

    return sql[:w_start] + new_where + sql[w_end:]

# ------------------------------------------------------------------------------
# Entity-lookup helpers (needle → candidate columns → probe)
# ------------------------------------------------------------------------------
_BASE_NAMEISH: Set[str] = {
    "NAME","FULL_NAME","FIRST_NAME","LAST_NAME","GIVEN_NAME","SURNAME",
    "TITLE","JOB","POSITION","ROLE","DESIGNATION","DESC","DESCRIPTION","LABEL"
}
def _nameish_for_query(q: str) -> Set[str]:
    tokens = set(_BASE_NAMEISH); uq = (q or "").lower()
    if re.search(r'\b(product|sku|item|model|brand|category|upc|ean)\b', uq):
        tokens.update({"PRODUCT","PRODUCT_NAME","ITEM","ITEM_NAME","SKU","MODEL","BRAND","CATEGORY","UPC","EAN"})
    if re.search(r'\b(order|po|purchase\s*order|invoice|bill|so|sales\s*order)\b', uq):
        tokens.update({"ORDER","ORDER_NO","ORDER_NUM","ORDER_NUMBER","PO","PO_NO","PO_NUMBER","INVOICE","INVOICE_NO","INVOICE_NUM"})
    if re.search(r'\b(customer|client|buyer)\b', uq):
        tokens.update({"CUSTOMER","CLIENT","BUYER","COMPANY","ACCOUNT_NAME"})
    if re.search(r'\b(supplier|vendor|manufacturer)\b', uq):
        tokens.update({"SUPPLIER","VENDOR","MANUFACTURER","COMPANY","ORG","ORGANIZATION"})
    return tokens

_GENERIC_SHORT_WORDS = {
    "order","orders","summary","report","reports","status","table","tables","grid",
    "list","display","show","overview","analysis","analytics","trend","trends",
    "update","updates","kpi","kpis","metrics","revenue","sales","inventory",
    "backlog","dashboard","data","info","information","help"
}
def _is_entity_lookup(q: str) -> bool:
    q = (q or "").strip()
    if re.match(r"^\s*(who|what)\s+is\b", q, re.I): return True
    toks = re.findall(r"[A-Za-z0-9]+", q)
    if not toks or len(toks) > 3: return False
    low = [t.lower() for t in toks]
    if all(t in _GENERIC_SHORT_WORDS for t in low): return False
    if any(any(ch.isdigit() for ch in t) for t in toks): return True
    return False

def _needle_from_question(q: str) -> str:
    """
    Extract a search term (needle) from a user question for entity lookup.
    This function identifies the key term to search for in the database.
    """
    q = q or ""
    # Remove common stopwords and generic terms
    q_clean = re.sub(r'\b(?:the|a|an|of|in|on|at|to|for|with|by|from|up|down|over|under|between|through|during|before|after|above|below|into|onto|upon|about|against|across|along|among|around|behind|beneath|beside|between|beyond|inside|outside|throughout|within)\b', ' ', q, flags=re.IGNORECASE)
    # Remove extra whitespace
    q_clean = re.sub(r'\s+', ' ', q_clean).strip()
    
    # If we have a "who is" or "what is" question, extract the entity name
    who_what_match = re.match(r'^\s*(?:who|what)\s+(?:is|are|was|were)\s+(.+)', q_clean, re.IGNORECASE)
    if who_what_match:
        return who_what_match.group(1).strip()
    
    # For other questions, try to extract the main noun or entity
    # Split into words and take the most relevant ones
    words = re.findall(r'[A-Za-z0-9]+', q_clean)
    if not words:
        return q_clean.strip()
    
    # Filter out generic words and take the first few meaningful words
    meaningful_words = [w for w in words if w.lower() not in _GENERIC_SHORT_WORDS and len(w) > 1]
    if meaningful_words:
        # Take up to 3 meaningful words
        return ' '.join(meaningful_words[:3])
    
    # Fallback to the cleaned query
    return q_clean.strip()

def _list_name_like_columns(selected_db: str, limit_tables: int = 400, query_text: str = "") -> List[Dict[str, str]]:
    dyn_tokens = sorted(_nameish_for_query(query_text))
    like_clauses = " OR ".join([f"UPPER(column_name) LIKE '%{t}%'" for t in dyn_tokens])
    sql = f"""
    SELECT /*+ FIRST_ROWS(200) */
           table_name, column_name
      FROM user_tab_columns
     WHERE data_type IN ('VARCHAR2','CHAR','NVARCHAR2','NCHAR')
       AND (
            { " OR ".join([f"UPPER(column_name) = '{c}'" for c in ("ENAME","NAME","FULL_NAME","TITLE","JOB","POSITION","ROLE","DESIGNATION")]) }
            OR {like_clauses if like_clauses else "1=0"}
       )
     FETCH FIRST {limit_tables} ROWS ONLY
    """
    out: List[Dict[str, str]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        _set_case_insensitive_session(cur)
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [{cols[i]: to_jsonable(r[i]) for i in range(len(cols))} for r in cur]
        try: cur.close()
        except Exception: pass
    return rows[:50]

# Add this near the top of the file with other imports and classes
class QueryCancellationError(Exception):
    """Exception raised when a query is cancelled."""
    pass

# Add threading import for cancellation support
import threading
from typing import Callable

# Add a global registry for active queries and a lock for thread safety
_ACTIVE_QUERIES = {}
_ACTIVE_QUERIES_LOCK = threading.Lock()

# Add a function to cancel all active queries
def cancel_all_active_queries():
    """Cancel all currently active queries."""
    with _ACTIVE_QUERIES_LOCK:
        cancelled_count = 0
        for query_id, query_info in list(_ACTIVE_QUERIES.items()):
            try:
                cursor = query_info.get('cursor')
                if cursor:
                    # For Oracle, we can't directly cancel a query, but we can close the cursor
                    # In a more sophisticated implementation, we would use database-specific 
                    # mechanisms to terminate the query on the server side
                    cursor.close()
                    cancelled_count += 1
            except Exception as e:
                logger.warning(f"Error cancelling query {query_id}: {e}")
        _ACTIVE_QUERIES.clear()
        return cancelled_count

# Enhanced version of run_sql with cancellation support
def run_sql_with_cancellation(sql: str, selected_db: str, *, cache_ok: bool = True, cancellation_token: Optional[Callable[[], bool]] = None) -> List[Dict[str, Any]]:
    cached = _cache_get_result(selected_db, sql)
    if cached:
        logger.debug("[DB] cache_hit=1 db=%s", selected_db)
        return cached["rows"]

    logger.debug("[DB] SQL: %s", (sql or "").replace("\n", " ")[:2000])
    
    # Generate a unique query ID for tracking
    query_id = f"{selected_db}_{hash(sql)}_{int(time.time() * 1000)}"
    
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor()
        _set_case_insensitive_session(cur)
        
        # Register the active query
        with _ACTIVE_QUERIES_LOCK:
            _ACTIVE_QUERIES[query_id] = {
                'cursor': cur,
                'connection': conn,
                'start_time': time.time(),
                'sql': sql
            }
        
        try:
            # Check for cancellation before executing
            if cancellation_token and cancellation_token():
                raise QueryCancellationError("Query was cancelled before execution")
            
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = [{cols[i]: to_jsonable(r[i]) for i in range(len(cols))} for r in cur]
            
            # Periodically check for cancellation during execution (for long-running queries)
            # This is a simplified check - in a more sophisticated implementation, you might want to check more frequently
            # or use database-specific mechanisms
            if cancellation_token:
                # Check once after execution completes
                if cancellation_token():
                    raise QueryCancellationError("Query was cancelled during execution")
            
        finally:
            # Remove the query from active queries
            with _ACTIVE_QUERIES_LOCK:
                _ACTIVE_QUERIES.pop(query_id, None)

    logger.debug("[DB] rows=%d cols=%d", len(rows), len(cols))

    _cache_set_result(selected_db, sql, cols, rows, cache_ok=cache_ok)
    return rows

def _merge_candidates(primary: List[Dict[str, str]], fallback: List[Dict[str, str]], cap: int = 200) -> List[Dict[str, str]]:
    seen = set(); merged = []
    for lst in (primary, fallback):
        for x in lst:
            k = (x["table"], x["column"])
            if k not in seen:
                merged.append(x); seen.add(k)
            if len(merged) >= cap: return merged
    return merged

def _candidate_columns(selected_db: str, query_text: str, top_k: int = 12) -> List[Dict[str, str]]:
    hits = hybrid_schema_value_search(query_text, selected_db=selected_db, top_k=top_k)
    cols = []
    for h in hits:
        meta = (h or {}).get("metadata", {})
        if meta.get("kind") == "column" and meta.get("source_table") and meta.get("column"):
            cols.append({"table": meta["source_table"], "column": meta["column"]})
    seen = set(); dedup = []
    for c in cols:
        key = (c["table"], c["column"])
        if key not in seen:
            dedup.append(c); seen.add(key)
    dedup = [c for c in dedup if not _is_banned_table(c["table"])]
    nameish = _nameish_for_query(query_text)
    dedup.sort(key=lambda c: 0 if any(k in (c["column"] or "").upper() for k in nameish) else 1)
    return dedup[:25]

def _quick_value_probe(selected_db: str, needle: str, candidates: List[Dict[str, str]], limit_per_col: int = 5) -> List[Dict[str, Any]]:
    if not needle or not candidates:
        return []
    esc = needle.upper().replace("'", "''")
    results: List[Dict[str, Any]] = []
    with connect_to_source(selected_db) as (conn, _):
        cur = conn.cursor(); _set_case_insensitive_session(cur)
        for c in candidates:
            table = c["table"]; col = c["column"]
            if _is_banned_table(table):
                continue
            sql = f"SELECT {col} FROM {table} WHERE UPPER({col}) LIKE '%{esc}%' AND ROWNUM <= {limit_per_col}"
            try:
                cur.execute(sql)
                for r in cur.fetchall():
                    results.append({"table": table, "column": col, "value": to_jsonable(r[0])})
            except Exception:
                continue
        try: cur.close()
        except Exception: pass
    return results[:50]


def execute_query(sql: str, selected_db: str = "source_db_1") -> Dict[str, Any]:
    """
    Execute a SQL query against the SOS database.
    
    Args:
        sql: The SQL query to execute
        selected_db: The database ID to connect to (default: source_db_1)
        
    Returns:
        Dictionary containing query results with columns and rows
    """
    try:
        # Execute the SQL query
        rows = run_sql_with_cancellation(sql, selected_db)
        
        # Convert rows to the expected format
        if rows:
            # Extract column names from the first row
            columns = list(rows[0].keys()) if rows else []
            # Convert rows to list of lists
            rows_as_lists = [list(row.values()) for row in rows]
            
            return {
                "columns": columns,
                "rows": rows_as_lists,
                "row_count": len(rows)
            }
        else:
            return {
                "columns": [],
                "rows": [],
                "row_count": 0
            }
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        raise e

    return results[:50]