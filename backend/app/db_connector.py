# db_connector.py
import cx_Oracle
import json
import time, os
import logging
import itertools
import re
from contextlib import contextmanager
from typing import List, Dict, Any, Tuple, Callable, Optional

from app.config import FEEDBACK_DB_ID
from threading import Lock
import threading

# Add connection pooling
from cx_Oracle import SessionPool

_SCHEMA_TTL_SEC = int(os.getenv("SCHEMA_TTL_SEC", "600"))  # 10 min default
# Add separate TTL for ERP databases which have many more tables
_ERP_SCHEMA_TTL_SEC = int(os.getenv("ERP_SCHEMA_TTL_SEC", "3600"))  # 1 hour default for ERP
_SCHEMA_LAST_REFRESH: Dict[str, float] = {}                # per-DB last refresh
_SCHEMA_LOCK = Lock()

# Connection pool configuration
_CONNECTION_POOLS: Dict[str, SessionPool] = {}
_POOL_LOCK = Lock()
_POOL_MIN = int(os.getenv("DB_POOL_MIN", "5"))  # Increased minimum pool size
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))  # Increased maximum pool size
_POOL_INCREMENT = int(os.getenv("DB_POOL_INCREMENT", "2"))  # Increased increment

def _get_connection_pool(db_key: str) -> SessionPool:
    """Get or create a connection pool for a database."""
    with _POOL_LOCK:
        if db_key not in _CONNECTION_POOLS:
            cfg = SOURCE_DBS_MAP.get(db_key)
            if not cfg:
                raise ValueError(f"Unknown database: {db_key}")
            
            dsn = cx_Oracle.makedsn(
                cfg["host"], 
                cfg["port"], 
                service_name=cfg["service_name"]
            )
            
            # Get timeout values from configuration
            from app.config import DATABASE_CONFIG
            connection_timeout_ms = DATABASE_CONFIG.get("connection_timeout_ms", 3000)
            retry_attempts = DATABASE_CONFIG.get("retry_attempts", 1)
            
            # Create connection pool with timeout settings
            pool = cx_Oracle.SessionPool(
                user=cfg["user"],
                password=cfg["password"],
                dsn=dsn,
                min=_POOL_MIN,
                max=_POOL_MAX,
                increment=_POOL_INCREMENT,
                encoding="UTF-8",
                nencoding="UTF-8",
                threaded=True,
                getmode=cx_Oracle.SPOOL_ATTRVAL_WAIT,
                timeout=int(connection_timeout_ms / 1000),  # Convert to seconds
                wait_timeout=int(connection_timeout_ms / 1000),  # Convert to seconds
                max_lifetime_session=600,  # Increased to 10 minutes max lifetime
                # Add performance optimization parameters
                homogeneous=True,  # All connections use the same credentials
                externalauth=False,  # Use standard authentication
            )
            
            _CONNECTION_POOLS[db_key] = pool
            logger.debug(f"Created connection pool for {db_key} (min={_POOL_MIN}, max={_POOL_MAX}, timeout={connection_timeout_ms}ms)")
        
        return _CONNECTION_POOLS[db_key]

def _maybe_refresh_schema_cache(db_key: str, validator: "SchemaValidator") -> None:
    """
    Refresh the validator's schema cache at most once per TTL *per source DB*.
    For ERP databases with many tables, use a longer TTL to avoid expensive refreshes.
    """
    now = time.time()
    with _SCHEMA_LOCK:
        last = _SCHEMA_LAST_REFRESH.get(db_key, 0.0)
        # Determine TTL based on database type
        ttl = _ERP_SCHEMA_TTL_SEC if db_key == "source_db_2" else _SCHEMA_TTL_SEC
        # if the validator is "cold", force refresh regardless of TTL
        if (now - last) < ttl:
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

from app.config import VECTOR_DB, DATABASE_CONFIG

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

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
                
                # For ERP databases, optimize the column query to avoid loading all columns for all tables
                # which is extremely expensive for databases with many tables
                if len(self._table_cache) > 500:  # ERP database optimization threshold
                    logger.info(f"Optimizing schema refresh for large database with {len(self._table_cache)} tables")
                    # For large databases, only cache columns for critical/often-used tables
                    critical_tables = [
                        'HR_OPERATING_UNITS', 'ORG_ORGANIZATION_DEFINITIONS', 
                        'MTL_ONHAND_QUANTITIES_DETAIL', 'MTL_SECONDARY_INVENTORIES'
                    ]
                    table_placeholders = ','.join([':' + str(i) for i in range(len(critical_tables))])
                    params = {str(i): table for i, table in enumerate(critical_tables)}
                    
                    cur.execute(f"""
                        SELECT table_name, column_name, data_type 
                        FROM user_tab_columns 
                        WHERE table_name IN ({table_placeholders})
                        ORDER BY table_name, column_id
                    """, params)
                else:
                    # Cache columns for all tables (original behavior for smaller databases)
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

# Timeout handler for database connections (cross-platform)
class DatabaseTimeoutError(Exception):
    pass

def initialize_connection(cfg: Dict[str, Any]) -> Tuple[cx_Oracle.Connection, SchemaValidator]:
    """Initialize a single database connection and validator"""
    dsn = cx_Oracle.makedsn(
        cfg["host"], 
        cfg["port"], 
        service_name=cfg["service_name"]
    )
    conn = None
    try:
        logger.debug(f"Attempting to connect to database at {cfg['host']}:{cfg['port']}/{cfg['service_name']}")
        # Add connection timeout parameters using correct cx_Oracle parameter names
        conn = cx_Oracle.connect(
            user=cfg["user"],
            password=cfg["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True,
            # Add timeout parameters
            expire_time=0,  # Disable connection expiration
        )
        logger.debug("Database connection established successfully")
        
        # Create validator
        validator = SchemaValidator(conn)
        validator.refresh_cache()
        
        return conn, validator
    except cx_Oracle.Error as e:
        logger.error(f"Failed to establish database connection: {e}")
        if conn:
            try:
                conn.close()
            except:
                pass
        raise

@contextmanager
def connect_to_source(db_key: str):
    """
    Context manager that connects to a source database using its ID
    Returns a connection and validator tuple
    Uses connection pooling for better performance.
    """
    cfg = SOURCE_DBS_MAP.get(db_key)
    if not cfg:
        raise ValueError(f"Unknown database: {db_key}")
    
    conn = None
    pool = None
    try:
        logger.debug(f"Attempting to connect to source database {db_key} at {cfg['host']}:{cfg['port']}/{cfg['service_name']}")
        
        # Use connection pool instead of creating new connections
        pool = _get_connection_pool(db_key)
        conn = pool.acquire()
        
        logger.debug(f"Acquired connection from pool for {db_key}")
        
        # Create validator for this connection
        validator = SchemaValidator(conn)
        _maybe_refresh_schema_cache(db_key, validator)
        
        yield conn, validator
    except cx_Oracle.Error as e:
        logger.error(f"Database error during operation with source {db_key}: {e}")
        if conn and pool:
            try:
                pool.release(conn)
            except:
                pass
        raise
    finally:
        if conn:
            try:
                pool = _get_connection_pool(db_key)
                pool.release(conn)
                logger.debug(f"Released connection back to pool for {db_key}")
            except Exception as close_error:
                logger.warning(f"Error releasing connection to pool for {db_key}: {close_error}")

@contextmanager
def connect_vector():
    """Connect to vector database with PDB support"""
    # Use connection pooling for vector database as well
    conn = None
    pool = None
    try:
        dsn = cx_Oracle.makedsn(
            VECTOR_DB["host"],
            VECTOR_DB["port"],
            service_name=VECTOR_DB["service_name"]
        )
        
        # Get timeout values from configuration
        from app.config import DATABASE_CONFIG
        connection_timeout_ms = DATABASE_CONFIG.get("connection_timeout_ms", 3000)
        
        # Create or get connection pool for vector database
        vector_db_key = f"vector_{VECTOR_DB['host']}_{VECTOR_DB['port']}_{VECTOR_DB['service_name']}"
        with _POOL_LOCK:
            if vector_db_key not in _CONNECTION_POOLS:
                pool = cx_Oracle.SessionPool(
                    user=VECTOR_DB["user"],
                    password=VECTOR_DB["password"],
                    dsn=dsn,
                    min=_POOL_MIN,
                    max=_POOL_MAX,
                    increment=_POOL_INCREMENT,
                    encoding="UTF-8",
                    nencoding="UTF-8",
                    threaded=True,
                    getmode=cx_Oracle.SPOOL_ATTRVAL_WAIT,
                    timeout=int(connection_timeout_ms / 1000),  # Convert to seconds
                    wait_timeout=int(connection_timeout_ms / 1000),  # Convert to seconds
                    max_lifetime_session=600,  # Increased to 10 minutes max lifetime
                    # Add performance optimization parameters
                    homogeneous=True,  # All connections use the same credentials
                    externalauth=False,  # Use standard authentication
                )
                _CONNECTION_POOLS[vector_db_key] = pool
                logger.debug(f"Created connection pool for vector database (min={_POOL_MIN}, max={_POOL_MAX}, timeout={connection_timeout_ms}ms)")
            
            pool = _CONNECTION_POOLS[vector_db_key]
        
        conn = pool.acquire()
        logger.debug("Acquired connection from pool for vector database")

        # Switch to PDB if specified
        if "pdb" in VECTOR_DB and VECTOR_DB["pdb"]:
            with conn.cursor() as cur:
                cur.execute(f"ALTER SESSION SET CONTAINER = {VECTOR_DB['pdb']}")

        yield conn
    except cx_Oracle.Error as e:
        logger.error(f"Vector DB connection error: {e}")
        if conn and pool:
            try:
                pool.release(conn)
            except:
                pass
        raise
    finally:
        if conn and pool:
            try:
                pool.release(conn)
                logger.debug("Released connection back to pool for vector database")
            except Exception as close_error:
                logger.warning(f"Error releasing connection to pool for vector database: {close_error}")

@contextmanager
def connect_feedback():
    """Connect to the Oracle DB that stores AI feedback/labels."""
    cfg = SOURCE_DBS_MAP.get(FEEDBACK_DB_ID)
    if not cfg:
        raise ValueError(f"Unknown FEEDBACK_DB_ID: {FEEDBACK_DB_ID}")
    
    conn = None
    pool = None
    try:
        logger.debug(f"Attempting to connect to feedback database at {cfg['host']}:{cfg['port']}/{cfg['service_name']}")
        
        # Use connection pool for feedback database
        pool = _get_connection_pool(FEEDBACK_DB_ID)
        conn = pool.acquire()
        
        logger.debug("Acquired connection from pool for feedback database")
        yield conn
    except cx_Oracle.Error as e:
        logger.error(f"Feedback DB connection error: {e}")
        if conn and pool:
            try:
                pool.release(conn)
            except:
                pass
        raise
    finally:
        if conn and pool:
            try:
                pool.release(conn)
                logger.debug("Released connection back to pool for feedback database")
            except Exception as close_error:
                logger.warning(f"Error releasing connection to pool for feedback database: {close_error}")

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

# Add a custom exception for query cancellation
class QueryCancellationError(Exception):
    """Exception raised when a query is cancelled."""
    pass

# Add a function to execute SQL with cancellation support
def execute_sql_with_cancellation(sql: str, connection, cancellation_token: Optional[Callable[[], bool]] = None) -> List[Dict[str, Any]]:
    """
    Execute SQL with support for cancellation.
    
    Args:
        sql: The SQL query to execute
        connection: The database connection
        cancellation_token: A function that returns True if the query should be cancelled
        
    Returns:
        List of rows as dictionaries
        
    Raises:
        QueryCancellationError: If the query is cancelled
    """
    # Check for cancellation before executing
    if cancellation_token and cancellation_token():
        raise QueryCancellationError("Query was cancelled before execution")
    
    cursor = connection.cursor()
    
    try:
        cursor.execute(sql)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        rows = [{cols[i]: to_jsonable(r[i]) for i in range(len(cols))} for r in cursor]
        
        # Check for cancellation after execution
        if cancellation_token and cancellation_token():
            raise QueryCancellationError("Query was cancelled during execution")
            
        return rows
    finally:
        try:
            cursor.close()
        except:
            pass

# Helper function to convert values to JSON-serializable format
def to_jsonable(v):
    """Convert a value to a JSON-serializable format."""
    from decimal import Decimal
    from datetime import datetime, date
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='ignore')
    return v
