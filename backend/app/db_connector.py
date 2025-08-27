# db_connector.py
import cx_Oracle
import json
import time, os
import logging
import itertools
import re
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple
from app.config import FEEDBACK_DB_ID
from threading import Lock

_SCHEMA_TTL_SEC = int(os.getenv("SCHEMA_TTL_SEC", "600"))  # 10 min default
_SCHEMA_LAST_REFRESH: Dict[str, float] = {}                # per-DB last refresh
_SCHEMA_LOCK = Lock()

def _maybe_refresh_schema_cache(db_key: str, validator: "SchemaValidator") -> None:
    """
    Refresh the validator's schema cache at most once per TTL *per source DB*.
    """
    now = time.time()
    with _SCHEMA_LOCK:
        last = _SCHEMA_LAST_REFRESH.get(db_key, 0.0)
        # if the validator is "cold", force refresh regardless of TTL
        if (now - last) < _SCHEMA_TTL_SEC:
            logging.getLogger(__name__).debug(
                f"[SchemaCache] skip refresh for {db_key}; age={now-last:.1f}s < TTL"
            )
            return
        validator.refresh_cache()
        _SCHEMA_LAST_REFRESH[db_key] = now

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
        _maybe_refresh_schema_cache(db_key, validator)
        
        yield conn, validator
    except cx_Oracle.Error as e:
        logger.error("Database error during operation: %s", e)
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