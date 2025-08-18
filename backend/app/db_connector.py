# db_connector.py
import cx_Oracle
import json
import os
import logging
import itertools
import re
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple
from app.config import FEEDBACK_DB_ID


# --- Lightweight SQL helpers (no hardcoding) ---------------------------------
def _normalize_ident(tok: str) -> str:
    tok = (tok or "").strip()
    if tok.startswith('"') and tok.endswith('"'):
        tok = tok[1:-1]
    return tok.upper()

def _split_top_level_unions(sql: str):
    """
    Split on top-level UNION / UNION ALL only (outside quotes/parentheses).
    Returns a list of SELECT arms (1+).
    """
    s = sql or ""
    parts, buf = [], []
    par = 0
    in_sq = False  # '...'
    in_dq = False  # "..."
    i, n = 0, len(s)

    while i < n:
        ch = s[i]

        if ch == "'" and not in_dq:
            in_sq = not in_sq
            buf.append(ch); i += 1; continue
        if ch == '"' and not in_sq:
            in_dq = not in_dq
            buf.append(ch); i += 1; continue

        if not in_sq and not in_dq:
            if ch == '(':
                par += 1
            elif ch == ')':
                par = max(0, par - 1)

            if par == 0 and s[i:i+5].upper() == "UNION":
                # token boundary check
                before = s[i-1] if i > 0 else " "
                after = s[i+5] if i+5 < n else " "
                if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                    part = "".join(buf).strip()
                    if part:
                        parts.append(part)
                    buf = []
                    i += 5
                    if s[i:i+4].upper() == " ALL":
                        i += 4
                    continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts if parts else [s.strip()]

def _extract_tables_and_aliases(sql_arm: str):
    """
    Find tables from FROM/JOIN and map aliases -> table.
    """
    import re
    rx = re.compile(
        r'\b(?:FROM|JOIN)\s+("?[A-Z0-9_$#]+"?)'
        r'(?:\s+(?:AS\s+)?("?[A-Z0-9_$#]+"?))?',
        re.IGNORECASE,
    )
    tables = set()
    alias_map = {}
    for m in rx.finditer(sql_arm or ""):
        t = _normalize_ident(m.group(1))
        tables.add(t)
        alias = m.group(2)
        if alias:
            a = _normalize_ident(alias)
            alias_map[a] = t
        # allow qualifiers using the table name itself as alias
        alias_map.setdefault(t, t)
    return tables, alias_map

def _collect_columns(sql_arm: str):
    """
    Collect qualified (a.col) and raw tokens (for unqualified columns),
    skipping function tokens (tokens followed by '(').
    """
    import re
    qual = []
    qual_rx = re.compile(
        r'("?[A-Z0-9_$#]+"?)\s*\.\s*("?[A-Z0-9_$#]+"?)',
        re.IGNORECASE,
    )
    for a, c in qual_rx.findall(sql_arm or ""):
        qual.append((_normalize_ident(a), _normalize_ident(c)))

    raw = set()
    # tokens not followed by '(' (to avoid function names)
    tok_rx = re.compile(r'(?<![\.\w])("?[A-Z_][A-Z0-9_$#]*"?)(?!\s*\()', re.IGNORECASE)
    for t in tok_rx.findall(sql_arm or ""):
        raw.add(_normalize_ident(t))

    return qual, raw
# ----------------------------------------------------------------------------- 


# Load all source DBs from sources.json (now a list)
with open(os.path.join("config", "sources.json")) as f:
    SOURCE_DBS: List[Dict[str, Any]] = json.load(f)

# Create a mapping from DB ID to configuration
SOURCE_DBS_MAP = {db["id"]: db for db in SOURCE_DBS}

from app.config import VECTOR_DB

logger = logging.getLogger(__name__)

class SchemaValidator:
    def __init__(self, conn):
        self.conn = conn
        self._column_cache = {}
        self._table_cache = set()
        
    def refresh_cache(self):
        """Refresh the schema cache from database metadata"""
        with self.conn.cursor() as cur:
            try:
                # Cache tables
                cur.execute("SELECT table_name FROM user_tables")
                self._table_cache = {row[0].upper() for row in cur.fetchall()}
                
                # Cache columns
                cur.execute("""
                    SELECT table_name, column_name, data_type 
                    FROM user_tab_columns
                    ORDER BY table_name, column_id
                """)
                
                # Group columns by table
                self._column_cache = {
                    table.upper(): {
                        'columns': {col[1].upper() for col in cols},
                        'types': {col[1].upper(): col[2] for col in cols}
                    }
                    for table, cols in itertools.groupby(
                        cur.fetchall(),
                        key=lambda x: x[0]
                    )
                }
                
                logger.info(f"Refreshed schema cache with {len(self._table_cache)} tables")
            except cx_Oracle.Error as e:
                logger.error(f"Failed to refresh schema cache: {e}")
                raise

def validate_sql(self, sql: str) -> Dict[str, Any]:
    """
    Per-SELECT-arm validation that stays friendly:
    - Split on top-level UNION/UNION ALL
    - For each arm, resolve tables/aliases and check:
        * qualified t.col exists in resolved table
        * unqualified col exists in ANY table in that arm
    - Falls back softly (never blocks execution) — DB parse remains the hard guard.
    """
    try:
        SQL_KEYWORDS = {
            'SELECT','FROM','WHERE','GROUP','ORDER','BY','HAVING','JOIN','INNER','OUTER','LEFT','RIGHT','FULL',
            'CROSS','ON','AND','OR','NOT','IN','LIKE','BETWEEN','IS','NULL','TRUE','FALSE','EXISTS','DISTINCT',
            'AS','WITH','UNION','INTERSECT','EXCEPT','CASE','WHEN','THEN','ELSE','END','LIMIT','OFFSET','FETCH',
            'NEXT','ONLY','NVL','DECODE','TO_DATE','TO_CHAR','TO_NUMBER','DUAL','ROWNUM','ROWID','LEVEL',
            'CONNECT','PRIOR','START','COUNT','SUM','AVG','MIN','MAX','COALESCE'
        }

        # dynamic keyword candidates from the SQL text (keeps it robust)
        keyword_candidates = {
            w.upper()
            for w in re.findall(r'\b[a-z_]+\b', sql or "", re.IGNORECASE)
            if len(w) > 2
        }
        all_keywords = SQL_KEYWORDS | keyword_candidates

        arms = _split_top_level_unions(sql or "")
        overall_missing_tables = set()
        overall_valid_cols = set()
        overall_invalid_cols = set()

        for arm in arms:
            tables_in_arm, alias_map = _extract_tables_and_aliases(arm)

            # mark missing tables vs cache
            present_tables = set()
            for t in tables_in_arm:
                if t in self._table_cache:
                    present_tables.add(t)
                else:
                    overall_missing_tables.add(t)

            # union of columns/types across present tables in this arm
            arm_union_cols = set()
            for t in present_tables:
                info = self._column_cache.get(t)
                if not info:
                    continue
                arm_union_cols |= (info.get('columns') or set())

            # collect columns (qualified & raw tokens)
            qual_pairs, raw_tokens = _collect_columns(arm)

            # drop obvious non-columns from raw_tokens: keywords, table names, aliases
            to_remove = all_keywords | tables_in_arm | set(alias_map.keys())
            candidates = {c for c in raw_tokens if c not in to_remove}

            # validate qualified: alias must resolve; col must be in that table
            for a, c in qual_pairs:
                t = alias_map.get(a)
                if not t or t not in self._column_cache:
                    overall_invalid_cols.add(f"{a}.{c}")
                    continue
                t_cols = self._column_cache[t]['columns']
                if c not in t_cols:
                    overall_invalid_cols.add(f"{a}.{c}")
                else:
                    overall_valid_cols.add(c)

            # validate unqualified: ok if present in ANY table used in this arm
            for c in candidates:
                if c in arm_union_cols:
                    overall_valid_cols.add(c)
                else:
                    overall_invalid_cols.add(c)

        # Oracle-specific date literal hint (kept)
        oracle_date_pattern = re.compile(
            r"TO_DATE\s*\(\s*'[^']+'\s*,\s*'[^']+'\s*\)",
            re.IGNORECASE
        )
        if (not oracle_date_pattern.search(sql or "")) and re.search(r'\bDATE\b', sql or "", re.IGNORECASE):
            # don't add duplicates
            for c in list(overall_invalid_cols):
                if c.upper().endswith('DATE'):
                    overall_invalid_cols.add(c)

        return {
            'valid': (len(overall_missing_tables) == 0 and len(overall_invalid_cols) == 0),
            'missing_tables': sorted(overall_missing_tables),
            'invalid_columns': sorted(overall_invalid_cols),
            'valid_columns': sorted(overall_valid_cols),
            'column_types': {},   # (optional) can be filled if you want
            'error': None
        }

    except Exception as e:
        logger.error(f"SQL validation error: {e}", exc_info=True)
        return {
            'valid': False,
            'missing_tables': [],
            'invalid_columns': [],
            'valid_columns': [],
            'column_types': {},
            'error': str(e)
        }

# Store all live Oracle connections for selected DBs
DB_CONNECTIONS: Dict[str, cx_Oracle.Connection] = {}
DB_VALIDATORS: Dict[str, SchemaValidator] = {}

def initialize_connection(cfg: Dict[str, Any]) -> Tuple[cx_Oracle.Connection, SchemaValidator]:
    """Initialize a single database connection and validator"""
    dsn = cx_Oracle.makedsn(
        cfg["host"], 
        cfg["port"], 
        service_name=cfg["service_name"]
    )
    conn = cx_Oracle.connect(
        user=cfg["user"],
        password=cfg["password"],
        dsn=dsn,
        encoding="UTF-8",
        nencoding="UTF-8",
        threaded=True
    )
    
    # Create validator
    validator = SchemaValidator(conn)
    validator.refresh_cache()
    
    return conn, validator


@contextmanager
def connect_to_source(db_key: str) -> Tuple[cx_Oracle.Connection, SchemaValidator]:
    """
    Context manager that connects to a source database using its ID
    Returns a connection and validator tuple
    """
    cfg = SOURCE_DBS_MAP.get(db_key)
    if not cfg:
        raise ValueError(f"Unknown database: {db_key}")
    
    dsn = cx_Oracle.makedsn(
        cfg["host"], 
        cfg["port"], 
        service_name=cfg["service_name"]
    )
    conn = None
    try:
        conn = cx_Oracle.connect(
            user=cfg["user"],
            password=cfg["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True
        )
        
        # Create validator for this temporary connection
        validator = SchemaValidator(conn)
        validator.refresh_cache()
        
        yield conn, validator
    except cx_Oracle.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

@contextmanager
def connect_vector():
    """Connect to vector database with PDB support"""
    dsn = cx_Oracle.makedsn(
        VECTOR_DB["host"],
        VECTOR_DB["port"],
        service_name=VECTOR_DB["service_name"]
    )
    conn = None
    try:
        conn = cx_Oracle.connect(
            user=VECTOR_DB["user"],
            password=VECTOR_DB["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True
        )

        # Switch to PDB if specified
        if "pdb" in VECTOR_DB and VECTOR_DB["pdb"]:
            with conn.cursor() as cur:
                cur.execute(f"ALTER SESSION SET CONTAINER = {VECTOR_DB['pdb']}")

        yield conn
    except cx_Oracle.Error as e:
        logger.error(f"Vector DB connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def refresh_all_schemas():
    """Refresh schema cache for all configured sources (on-demand, no long-lived connections)."""
    for cfg in SOURCE_DBS:
        db_key = cfg["id"]
        try:
            with connect_to_source(db_key) as (conn, validator):
                validator.refresh_cache()
                logger.info(f"Refreshed schema cache for {db_key}")
        except Exception as e:
            logger.error(f"Failed to refresh schema for {db_key}: {e}")


@contextmanager
def connect_feedback():
    """Connect to the Oracle DB that stores AI feedback/labels."""
    cfg = SOURCE_DBS_MAP.get(FEEDBACK_DB_ID)
    if not cfg:
        raise ValueError(f"Unknown FEEDBACK_DB_ID: {FEEDBACK_DB_ID}")
    dsn = cx_Oracle.makedsn(cfg["host"], cfg["port"], service_name=cfg["service_name"])
    conn = None
    try:
        conn = cx_Oracle.connect(
            user=cfg["user"],
            password=cfg["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True
        )
        yield conn
    finally:
        if conn:
            conn.close()