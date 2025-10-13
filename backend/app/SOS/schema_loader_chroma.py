import logging
import os
from tqdm import tqdm
import chromadb
from chromadb.config import Settings
import re

from app.db_connector import connect_to_source
from app.embeddings import get_embedding, encode_texts_batch
from app.config import SOURCES

import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# ---- Telemetry handling with version compatibility ----
try:
    from chromadb.telemetry.posthog import Posthog
    # For older versions of ChromaDB
    def safe_capture(self, *args, **kwargs):
        return None
    Posthog.capture = safe_capture
except ImportError:
    # For newer versions of ChromaDB where this import doesn't exist
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION_PREFIX = "schema_docs"

# --------- Ingest switches / limits via env ---------
INCLUDE_VALUE_SAMPLES = os.getenv("INCLUDE_VALUE_SAMPLES", "false").lower() == "true"
INCLUDE_NUMERIC_RANGES = os.getenv("INCLUDE_NUMERIC_RANGES", "false").lower() == "true"
INCLUDE_ALIASES = os.getenv("INCLUDE_ALIASES", "true").lower() == "true"

SCHEMA_MAX_TABLES = int(os.getenv("SCHEMA_MAX_TABLES", "0"))  # 0 = no cap
SCHEMA_MAX_COLS_PER_TABLE = int(os.getenv("SCHEMA_MAX_COLS_PER_TABLE", "0"))  # 0 = no cap
EMB_BATCH_SIZE = int(os.getenv("EMB_BATCH_SIZE", "64"))
CHROMA_ADD_BATCH_SIZE = int(os.getenv("CHROMA_ADD_BATCH_SIZE", "512"))

# Value sampling caps
MAX_DISTINCT_SAMPLES = int(os.getenv("MAX_DISTINCT_SAMPLES", "8"))
TEXT_TYPES = {"CHAR", "NCHAR", "NVARCHAR2", "VARCHAR2", "CLOB"}
NUM_TYPES  = {"NUMBER", "FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE"}

def get_chroma_client(source_id: str):
    # Mirror vector_store_chroma telemetry setting & persistence
    return chromadb.PersistentClient(
        path=f"chroma_storage/{source_id}",
        settings=Settings(anonymized_telemetry=False)
    )

# ---------------- COLUMN_HINTS ----------------
# (Kept as lightweight hints; the system stays dynamic and doesn’t rely on them.)
COLUMN_HINTS = {
    "DEPTNO": "Department number",
    "DNAME": "Department name",
    "LOC": "Location of department",
    "EMPNO": "Employee ID",
    "ENAME": "Employee name",
    "JOB": "Job title",
    "MGR": "Manager ID",
    "HIREDATE": "Date of hire",
    "SAL": "Salary",
    "COMM": "Commission",
    "ID": "Generic identifier (could be task or record)",
    "TASK_NAME": "Full name of the task",
    "TASK_SHORT_NAME": "Abbreviated task name",
    "TASK_TYPE": "Task category/type",
    "STATUS_ACTIVE": "Active status flag",
    "TASK_GROUP": "Task grouping or category",
    "TASK_OWNER": "Responsible person or role",
    "A_DATE": "Activity or record date",
    "LOCATION_NAME": "Location description",
    "BU_NAME": "Business unit name",
    "SECTION_NAME": "Section within the business",
    "LINE_NAME": "Production line or zone",
    "SUBUNIT_NAME": "Sub-unit or team name",
    "TOTAL_PRESENTS": "Total number of presents",
    "OT_HOUR": "Overtime hours",
    "OT_AMOUNT": "Overtime payment amount",
    "BUYER_NAME": "Buyer name",
    "STYLE": "Garment style",
    "POQTY": "Purchase order quantity",
    "SOUTPUT": "Sewing output",
    "SHIPQTY": "Shipment quantity",
    "DEFECT_QTY": "Defect quantity",
    "PRODUCTION_QTY": "Produced quantity",
    "FLOOR_EF": "Floor efficiency",
    "CM": "Cost of manufacturing",
    "SMV": "Standard minute value",
    "FULL_NAME": "Full name",
    "EMAIL_ADDRESS": "Email address",
    "IS_ACTIVE": "Active flag",
    "PIN": "User PIN",
    "LAST_LOGIN": "Last login time"
}

def generate_table_description(table_name: str) -> str:
    t = table_name.lower()
    if "emp" in t or "employee" in t:
        return "Table containing employee data such as personal details, salaries, and job roles."
    elif "dept" in t or "department" in t:
        return "Table containing department details including department name and location."
    elif "task" in t or "tna" in t:
        return "Table containing task details related to Time and Action management."
    elif "order" in t:
        return "Table containing order details including order information, quantities, and statuses."
    elif "transaction" in t:
        return "Table storing transaction details related to various processes."
    elif "details" in t:
        return "Table containing detailed information related to specific records."
    elif "mst" in t:
        return "Master table containing key reference data for a specific entity."
    elif "inventory" in t or "inv" in t:
        return "Table containing inventory-related data, including stock and transactions."
    elif "comment" in t:
        return "Table containing comments or notes related to specific records or transactions."
    elif "consume" in t:
        return "Table storing data about consumption of resources, such as materials or goods."
    elif "charge" in t:
        return "Table containing information about charges, fees, or costs associated with records."
    elif "contract" in t:
        return "Table storing contract details including contract amendments and related information."
    elif "tc" in t:
        return "Table containing transaction or receipt details related to specific processes."
    else:
        return f"Table '{table_name}' contains unspecified data."

# -------------------------
# Enhanced Critical Table Definitions
# -------------------------
# Enhanced Critical Table Definitions with your full schema
CRITICAL_TABLE_ENHANCED_INFO = {
    "T_PROD": {
        "description": "Production data table containing daily floor-wise production metrics, defect quantities, efficiency rates, and quality analysis. This is the primary table for production analysis and floor performance tracking.",
        "business_context": "Used for production summaries, floor efficiency analysis, defect tracking, DHU calculations, and quality control reporting.",
        "key_metrics": ["PRODUCTION_QTY", "DEFECT_QTY", "DHU", "FLOOR_EF"],
        "common_queries": ["floor-wise production", "defect analysis", "efficiency tracking", "daily production summary"]
    },
    "T_PROD_DAILY": {
        "description": "Daily production data with detailed time tracking including AC production hours and working hours. Enhanced version of T_PROD with additional time-based metrics for comprehensive production analysis.",
        "business_context": "Used for detailed daily production analysis, time efficiency calculations, hourly productivity tracking, and operational hour reporting.",
        "key_metrics": ["PRODUCTION_QTY", "DEFECT_QTY", "DHU", "FLOOR_EF", "AC_PRODUCTION_HOUR", "AC_WORKING_HOUR"],
        "common_queries": ["daily production analysis", "hourly efficiency", "time-based productivity", "working hour analysis"]
    },
    "T_TNA_STATUS": {
        "description": "Time and Action (TNA) status tracking table containing task management, buyer information, style details, and shipment schedules. Critical for order fulfillment and timeline management.",
        "business_context": "Used for task tracking, buyer order management, style reference lookups, shipment planning, and TNA timeline analysis.",
        "key_metrics": ["TASK_NUMBER", "PO_NUMBER_ID"],
        "common_queries": ["task status", "buyer orders", "style information", "shipment tracking", "TNA analysis"]
    },
    "T_USERS": {
        "description": "User management table containing employee personal details, contact information, access control, and login tracking.",
        "business_context": "Used for HR queries, employee lookups, contact information, user authentication, and staff management.",
        "key_metrics": ["USER_ID", "FULL_NAME", "EMAIL_ADDRESS"],
        "common_queries": ["employee information", "staff lookup", "contact details", "user management"]
    },
    "EMP": {
        "description": "Employee data table containing personal details, job roles, salary information, and organizational hierarchy.",
        "business_context": "Used for HR analysis, salary queries, organizational structure, employee management, and payroll reporting.",
        "key_metrics": ["EMPNO", "ENAME", "SAL", "JOB"],
        "common_queries": ["employee details", "salary information", "job roles", "manager hierarchy"]
    },
    "DEPT": {
        "description": "Department master table containing department information, names, and locations within the organization.",
        "business_context": "Used for organizational structure queries, department-wise analysis, and location-based reporting.",
        "key_metrics": ["DEPTNO", "DNAME", "LOC"],
        "common_queries": ["department information", "organizational structure", "department locations"]
    },
    "T_ORDC": {
        "description": "Order details and production tracking table containing buyer information, style details, quantities, and production metrics.",
        "business_context": "Used for order management, production planning, buyer analysis, and shipment tracking.",
        "key_metrics": ["POQTY", "CUTQTY", "SOUTPUT", "SHIPQTY"],
        "common_queries": ["order details", "production tracking", "buyer orders", "shipment status"]
    },
    "COMPANIES": {
        "description": "Company master table containing company information, addresses, and contact details.",
        "business_context": "Used for company management, contact information, and business relationship tracking.",
        "key_metrics": ["COMPANY_ID", "COMPANY_NAME"],
        "common_queries": ["company information", "business contacts", "company details"]
    },
    "CONTAINER_MASTER": {
        "description": "Container specifications table containing container types, dimensions, and capacity information.",
        "business_context": "Used for shipping calculations, container planning, and logistics management.",
        "key_metrics": ["CONTAINER_ID", "MAX_CBM", "MAX_WEIGHT_KG"],
        "common_queries": ["container specifications", "shipping capacity", "logistics planning"]
    },
    "ITEM_MASTER": {
        "description": "Item master table containing product specifications, dimensions, and physical properties.",
        "business_context": "Used for product management, inventory planning, and shipping calculations.",
        "key_metrics": ["ITEM_ID", "CBM", "LENGTH_CM", "WIDTH_CM", "HEIGHT_CM"],
        "common_queries": ["item specifications", "product details", "inventory management"]
    },
    "V_TNA_STATUS": {
        "description": "TNA status view providing comprehensive task tracking with enhanced reporting capabilities.",
        "business_context": "Used for TNA reporting, task analysis, buyer tracking, and timeline management.",
        "key_metrics": ["JOB_NO", "PO_NUMBER", "BUYER_NAME"],
        "common_queries": ["TNA reports", "task analysis", "buyer tracking", "timeline reports"]
    }
}

CRITICAL_COLUMN_ENHANCED_HINTS = {
    # Production Tables
    "PROD_DATE": "Production date - key for daily/periodic production analysis",
    "FLOOR_NAME": "Production floor identifier - essential for floor-wise analysis and comparisons. Use patterns like 'Sewing CAL%', 'Winner%', 'BIP%' for company filtering",
    "PM_OR_APM_NAME": "Production Manager or Assistant Production Manager name",
    "FLOOR_EF": "Floor efficiency percentage - key performance indicator",
    "DHU": "Defects per Hundred Units - critical quality metric",
    "DEFECT_QTY": "Total defect quantity - primary quality measurement",
    "PRODUCTION_QTY": "Total production quantity - primary output measurement",
    "DEFECT_PERS": "Defect percentage relative to production",
    "UNCUT_THREAD": "Specific defect type: uncut threads",
    "DIRTY_STAIN": "Specific defect type: dirty stains or spots",
    "BROKEN_STITCH": "Specific defect type: broken stitching",
    "SKIP_STITCH": "Specific defect type: skipped stitches",
    "OPEN_SEAM": "Specific defect type: open seams",
    "AC_PRODUCTION_HOUR": "Actual production hours worked",
    "AC_WORKING_HOUR": "Actual total working hours",

    # TNA Status Table
    "JOB_NO": "Job number - unique identifier for production jobs",
    "PO_NUMBER_ID": "Purchase order number ID - links to buyer orders",
    "TASK_NUMBER": "Task sequence number in TNA timeline",
    "TASK_FINISH_DATE": "Planned task completion date",
    "ACTUAL_FINISH_DATE": "Actual task completion date - for timeline analysis",
    "TASK_SHORT_NAME": "Abbreviated task name for quick reference",
    "PO_NUMBER": "Purchase order number - buyer reference",
    "PO_RECEIVED_DATE": "Date when purchase order was received",
    "PUB_SHIPMENT_DATE": "Published/planned shipment date",
    "SHIPMENT_DATE": "Actual shipment date",
    "STYLE_REF_NO": "Style reference number - unique garment style identifier",
    "STYLE_DESCRIPTION": "Detailed description of the garment style",
    "BUYER_NAME": "Customer/buyer name - for buyer-wise analysis",
    "TEAM_MEMBER_NAME": "Team member responsible for the task",
    "TEAM_LEADER_NAME": "Team leader overseeing the task",

    # Employee Tables (EMP and T_USERS)
    "EMPNO": "Employee number - unique employee identifier",
    "ENAME": "Employee name",
    "JOB": "Job title or role",
    "MGR": "Manager employee number",
    "HIREDATE": "Employee hire date",
    "SAL": "Employee salary",
    "COMM": "Commission amount",
    "DEPTNO": "Department number",
    "USER_ID": "User identifier in system",
    "USERNAME": "System username",
    "FULL_NAME": "Employee full name",
    "PHONE_NUMBER": "Contact phone number",
    "EMAIL_ADDRESS": "Employee email address",
    "IS_ACTIVE": "User active status flag",
    "LAST_LOGIN": "Last login timestamp",

    # Department Table
    "DNAME": "Department name",
    "LOC": "Department location",

    # Order and Production Tables
    "BUYER_NAME": "Customer/buyer company name",
    "STYLEPO": "Style purchase order reference",
    "STYLE": "Garment style code",
    "JOB": "Job reference number",
    "ITEM_NAME": "Product item name",
    "FACTORY": "Manufacturing factory",
    "POQTY": "Purchase order quantity",
    "CUTQTY": "Cutting quantity completed",
    "SINPUT": "Sewing input quantity",
    "SOUTPUT": "Sewing output quantity",
    "SHIPQTY": "Shipped quantity",
    "LEFTQTY": "Remaining quantity",
    "FOBP": "FOB price",
    "SMV": "Standard minute value",
    "CM": "Cost of manufacturing",
    "CEFFI": "Cutting efficiency",
    "AEFFI": "Actual efficiency",
    "CMER": "CM earned",
    "ACM": "Actual CM",
    "EXMAT": "Excess material",
    "SHIPDATE": "Shipment date",

    # Company Tables
    "COMPANY_ID": "Company unique identifier",
    "COMPANY_NAME": "Company name",
    "COMPANY_ADDRESS": "Company address",
    "COMPANY_CNCL": "Company cancellation status",

    # Container and Item Tables
    "CONTAINER_ID": "Container unique identifier",
    "CONTAINER_TYPE": "Container type specification",
    "INNER_LENGTH_CM": "Container inner length in centimeters",
    "INNER_WIDTH_CM": "Container inner width in centimeters",
    "INNER_HEIGHT_CM": "Container inner height in centimeters",
    "MAX_CBM": "Maximum cubic meters capacity",
    "MAX_WEIGHT_KG": "Maximum weight capacity in kilograms",
    "ITEM_ID": "Item unique identifier",
    "ITEM_CODE": "Item code reference",
    "DESCRIPTION": "Item description",
    "LENGTH_CM": "Item length in centimeters",
    "WIDTH_CM": "Item width in centimeters",
    "HEIGHT_CM": "Item height in centimeters",
    "CBM": "Cubic meters volume",

    # Task and Library Tables
    "ID": "Generic identifier (context-dependent)",
    "TASK_NAME": "Full task name",
    "TASK_SHORT_NAME": "Abbreviated task name",
    "TASK_TYPE": "Task category or type",
    "STATUS_ACTIVE": "Active status indicator",
    "TASK_GROUP": "Task grouping category",
    "TASK_OWNER": "Task owner or responsible party",

    # Date and Time Fields
    "A_DATE": "Activity or record date",
    "LAST_UPDATE": "Last update timestamp",
    "ADDED_DATE": "Record creation date",
    "UPDATE_DATE": "Record modification date",

    # Location and Organizational Fields
    "LOCATION_NAME": "Location description",
    "BU_NAME": "Business unit name",
    "SECTION_NAME": "Section within business unit",
    "LINE_NAME": "Production line or zone name",
    "SUBUNIT_NAME": "Sub-unit or team name",

    # Overtime and Time Tracking
    "TOTAL_PRESENTS": "Total attendance count",
    "OT_HOUR": "Overtime hours worked",
    "OT_AMOUNT": "Overtime payment amount",
    "OT_EMPLOYEE_COUNT": "Number of employees with overtime",
    "OT_HOUR_COUNT": "Total overtime hours",

    # Training and Reporting Views
    "SQL_SAMPLE_ID": "SQL sample identifier",
    "TURN_ID": "Conversation turn identifier",
    "USER_QUESTION": "User query text",
    "SOURCE_DB_ID": "Source database identifier",
    "MODEL_NAME": "AI model name used",
    "PROMPT_TEXT": "System prompt used",
    "SQL_TEXT": "Generated SQL query",
    "SQL_TEXT_FINAL": "Final SQL after processing",
    "NORMALIZED_SQL": "Normalized SQL query",
    "VALIDATION_OK": "SQL validation status",
    "EXECUTION_OK": "SQL execution status",
    "ERROR_CODE": "Error code if any",
    "ROW_COUNT": "Result row count",
    "RESULT_TABLE_JSON": "Result data in JSON format",
    "LABEL": "Training label or category",
    "IMPROVEMENT_COMMENT": "Improvement suggestions",
    "SUMMARY_SAMPLE_ID": "Summary sample identifier",
    "DATA_SNAPSHOT": "Data snapshot for training",
    "SQL_USED": "SQL query used for results",
    "SUMMARY_TEXT": "Generated summary text"
}

def generate_enhanced_table_description(table_name: str) -> str:
    """Generate enhanced descriptions for critical tables with business context."""
    table_upper = table_name.upper()
    if table_upper in CRITICAL_TABLE_ENHANCED_INFO:
        info = CRITICAL_TABLE_ENHANCED_INFO[table_upper]
        description = info["description"]
        business_context = info["business_context"]
        key_metrics = ", ".join(info["key_metrics"])
        common_queries = ", ".join(info["common_queries"])
        return f"{description} {business_context} Key metrics: {key_metrics}. Common use cases: {common_queries}."

    # Fallback to original lightweight heuristics
    t = table_name.lower()
    if "emp" in t or "employee" in t:
        return "Table containing employee data such as personal details, salaries, and job roles."
    elif "dept" in t or "department" in t:
        return "Table containing department details including department name and location."
    elif "task" in t or "tna" in t:
        return "Table containing task details related to Time and Action management."
    elif "order" in t:
        return "Table containing order details including order information, quantities, and statuses."
    elif "transaction" in t:
        return "Table storing transaction details related to various processes."
    elif "details" in t:
        return "Table containing detailed information related to specific records."
    elif "mst" in t:
        return "Master table containing key reference data for a specific entity."
    elif "inventory" in t or "inv" in t:
        return "Table containing inventory-related data, including stock and transactions."
    elif "comment" in t:
        return "Table containing comments or notes related to specific records or transactions."
    elif "consume" in t:
        return "Table storing data about consumption of resources, such as materials or goods."
    elif "charge" in t:
        return "Table containing information about charges, fees, or costs associated with records."
    elif "contract" in t:
        return "Table storing contract details including contract amendments and related information."
    elif "tc" in t:
        return "Table containing transaction or receipt details related to specific processes."
    else:
        return f"Table '{table_name}' contains unspecified data."

def create_table_descriptions(tables):
    return {table: generate_enhanced_table_description(table) for table in tables}

def get_enhanced_column_hint(column_name: str, table_name: str = None) -> str:
    """Get enhanced column hints with table context awareness."""
    col_upper = (column_name or "").upper()
    if col_upper in CRITICAL_COLUMN_ENHANCED_HINTS:
        return CRITICAL_COLUMN_ENHANCED_HINTS[col_upper]
    return COLUMN_HINTS.get(col_upper, "No description available")

def _safe_id_fragment(s: str) -> str:
    s = (s or "")[:128]
    return re.sub(r"[\s\r\n\t]+", "_", s)

def _aliases(s: str) -> list[str]:
    """
    Generate generic alias tokens for robust matching:
    - Upper-case original
    - Compact: remove spaces, hyphens, underscores
    """
    u = (s or "").upper()
    compact = re.sub(r'[\s\-_]+', '', u)
    # Use a set to dedupe; return as list
    out = list({u, compact})
    return out

def _sample_text_values(cursor, table: str, column: str):
    if not INCLUDE_VALUE_SAMPLES:
        return []
    sql = f"""
        SELECT {column} AS val, COUNT(*) AS c
        FROM {table}
        WHERE {column} IS NOT NULL
        GROUP BY {column}
        ORDER BY COUNT(*) DESC
        FETCH FIRST {MAX_DISTINCT_SAMPLES} ROWS ONLY
    """
    try:
        cursor.execute(sql)
        out = []
        for r in cursor:
            v = r[0]
            if hasattr(v, "read"):
                v = v.read()
            if isinstance(v, bytes):
                try:
                    v = v.decode("utf-8", errors="ignore")
                except Exception:
                    v = str(v)
            out.append((str(v), int(r[1])))
        return out
    except Exception as e:
        logger.debug(f"[ValueSample] Skip {table}.{column}: {e}")
        return []

# Optional value/range docs (kept tiny)
# Only sample values for ID-like columns to avoid index bloat
IDLIKE_RX = re.compile(
    r"(?:^|_)(ID|CODE|NO|NUM|NUMBER|BARCODE|CHALLAN|ORDER|SO|PO|INVOICE|JOB|LOT|REF|TRACK|DOC|VOUCHER)(?:$|_)",
    re.IGNORECASE
)

def _sample_numeric_range(cursor, table: str, column: str):
    if not INCLUDE_NUMERIC_RANGES:
        return None
    # Skip MEDIAN to avoid sort cost
    sql = f"SELECT MIN({column}), AVG({column}), MAX({column}) FROM {table}"
    try:
        cursor.execute(sql)
        r = cursor.fetchone()
        return r if r and r[0] is not None and r[2] is not None else None
    except Exception as e:
        logger.debug(f"[ValueRange] Skip {table}.{column}: {e}")
        return None

# --------- Exclude patterns (LIKE-style) ---------
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

def load_schema_to_chroma():
    # Only process source_db_1 (SOS) - ERP data loading is handled by ERP_R12_Test_DB/schema_loader_chroma.py
    sos_sources = [source for source in SOURCES if source["id"] == "source_db_1"]
    
    for source in sos_sources:
        source_id = source["id"]
        collection_name = f"{COLLECTION_PREFIX}_{source_id}"

        logger.info(f"\n🔄 Loading schema for DB: {source_id}")
        chroma_client = get_chroma_client(source_id)

        # Clean old collection
        try:
            existing = [c.name for c in chroma_client.list_collections()]
            if collection_name in existing:
                chroma_client.delete_collection(name=collection_name)
        except Exception as e:
            logger.warning(f"Could not clean old collection '{collection_name}': {e}")

        collection = chroma_client.get_or_create_collection(name=collection_name)

        total_tables = 0
        total_columns = 0
        value_docs = 0
        range_docs = 0
        alias_table_docs = 0
        alias_column_docs = 0

        try:
            with connect_to_source(source_id) as (conn, _):
                cursor = conn.cursor()
                
                # Load user tables (existing functionality)
                cursor.execute("SELECT table_name FROM user_tables")
                user_tables = [row[0] for row in cursor.fetchall()] or []
                
                # Dynamically discover system views that are relevant for database administration
                # This approach is dynamic and doesn't hardcode specific system views
                cursor.execute("""
                    SELECT view_name 
                    FROM user_views 
                    WHERE view_name IN (
                        SELECT table_name 
                        FROM user_tab_columns 
                        WHERE table_name LIKE 'USER_%' OR table_name LIKE 'ALL_%' OR table_name LIKE 'DBA_%'
                        GROUP BY table_name
                    )
                    ORDER BY view_name
                """)
                system_views = [row[0] for row in cursor.fetchall()] or []
                
                # Combine user tables and system views
                tables = user_tables + system_views

                # NEW: filter out excluded tables
                before = len(tables)
                tables = [t for t in tables if not _is_excluded_table(t)]
                after = len(tables)
                if before != after:
                    logger.info(f"[Index] Skipped {before - after} tables by EXCLUDE_TABLE_PATTERNS={EXCLUDE_TABLE_PATTERNS}")

                if SCHEMA_MAX_TABLES > 0:
                    tables = tables[:SCHEMA_MAX_TABLES]

                table_descriptions = create_table_descriptions(tables)

                # ---------- TABLE DOCS (batched) ----------
                table_docs, table_ids, table_metas = [], [], []
                for table in tables:
                    table_desc = table_descriptions.get(table.upper(), "No description available for this table")

                    if table.upper() in CRITICAL_TABLE_ENHANCED_INFO:
                        info = CRITICAL_TABLE_ENHANCED_INFO[table.upper()]
                        content = (
                            f"Table '{table}' from {source_id.upper()} database. {table_desc} "
                            f"Business use cases: {', '.join(info['common_queries'])}. "
                            f"This table is frequently used for queries about: "
                            f"production analysis, floor performance, defect tracking, efficiency metrics."
                        )
                        enhanced_meta = {
                            "source_table": table,
                            "source_id": source_id,
                            "kind": "table",
                            "is_critical": True,
                            "business_priority": "high",
                        }
                    else:
                        # Enhanced description for system views
                        if table.upper().startswith(('USER_', 'ALL_', 'DBA_')):
                            content = f"System view '{table}' from {source_id.upper()} database. This is an Oracle system view containing database metadata and administrative information."
                            enhanced_meta = {
                                "source_table": table, 
                                "source_id": source_id, 
                                "kind": "system_view",
                                "is_system_view": True
                            }
                        else:
                            content = f"Table '{table}' from {source_id.upper()} database. Description: {table_desc}"
                            enhanced_meta = {"source_table": table, "source_id": source_id, "kind": "table"}

                    doc_id = f"{source_id}.{table}"
                    table_docs.append(content)
                    table_ids.append(doc_id)
                    table_metas.append(enhanced_meta)

                table_embs = encode_texts_batch(table_docs, batch_size=EMB_BATCH_SIZE)

                # Add tables in large batches
                for i in range(0, len(table_docs), CHROMA_ADD_BATCH_SIZE):
                    collection.add(
                        documents=table_docs[i:i+CHROMA_ADD_BATCH_SIZE],
                        embeddings=table_embs[i:i+CHROMA_ADD_BATCH_SIZE],
                        ids=table_ids[i:i+CHROMA_ADD_BATCH_SIZE],
                        metadatas=table_metas[i:i+CHROMA_ADD_BATCH_SIZE],
                    )
                    total_tables += len(table_ids[i:i+CHROMA_ADD_BATCH_SIZE])

                # ---------- TABLE ALIAS DOCS (optional; batched) ----------
                if INCLUDE_ALIASES and tables:
                    alias_docs, alias_ids, alias_meta = [], [], []
                    for table in tables:
                        for a in _aliases(table):
                            alias_docs.append(f"Alias token for table '{table}': {a}")
                            alias_ids.append(f"{source_id}.{table}::ALIAS::{a}")
                            alias_meta.append({"source_table": table, "source_id": source_id, "kind": "alias"})
                    if alias_docs:
                        alias_embs = encode_texts_batch(alias_docs, batch_size=EMB_BATCH_SIZE)
                        for i in range(0, len(alias_docs), CHROMA_ADD_BATCH_SIZE):
                            collection.add(
                                documents=alias_docs[i:i+CHROMA_ADD_BATCH_SIZE],
                                embeddings=alias_embs[i:i+CHROMA_ADD_BATCH_SIZE],
                                ids=alias_ids[i:i+CHROMA_ADD_BATCH_SIZE],
                                metadatas=alias_meta[i:i+CHROMA_ADD_BATCH_SIZE],
                            )
                            alias_table_docs += len(alias_ids[i:i+CHROMA_ADD_BATCH_SIZE])

                # ---------- ENHANCED BUSINESS CONTEXT DOCS (for critical tables) ----------
                business_docs, business_ids, business_metas = [], [], []

                for table in tables:
                    if table.upper() in CRITICAL_TABLE_ENHANCED_INFO:
                        info = CRITICAL_TABLE_ENHANCED_INFO[table.upper()]
                        context_mappings = [
                            ("production queries", "production quantity defect floor efficiency manufacturing output"),
                            ("defect analysis", "quality control defects DHU broken stitch skip stitch open seam"),
                            ("floor performance", "floor wise analysis efficiency comparison production rates"),
                            ("daily tracking", "daily production tracking date wise analysis trends"),
                            ("task management", "TNA timeline task status buyer orders shipment dates"),
                            ("style information", "garment style description buyer requirements specifications"),
                        ]
                        for context_type, keywords in context_mappings:
                            if any(
                                kw in (info["business_context"] or "").lower()
                                or kw in " ".join(info.get("common_queries", [])).lower()
                                for kw in keywords.split()
                            ):
                                business_doc = (
                                    f"Business context: {context_type} using table '{table}'. "
                                    f"Keywords: {keywords}. Table contains: {info['description'][:200]}..."
                                )
                                business_id = f"{source_id}.{table}::CONTEXT::{context_type.replace(' ', '_')}"
                                business_meta = {
                                    "source_table": table,
                                    "source_id": source_id,
                                    "kind": "business_context",
                                    "context_type": context_type,
                                    "is_critical": True,
                                }
                                business_docs.append(business_doc)
                                business_ids.append(business_id)
                                business_metas.append(business_meta)

                if business_docs:
                    business_embs = encode_texts_batch(business_docs, batch_size=EMB_BATCH_SIZE)
                    for i in range(0, len(business_docs), CHROMA_ADD_BATCH_SIZE):
                        collection.add(
                            documents=business_docs[i:i+CHROMA_ADD_BATCH_SIZE],
                            embeddings=business_embs[i:i+CHROMA_ADD_BATCH_SIZE],
                            ids=business_ids[i:i+CHROMA_ADD_BATCH_SIZE],
                            metadatas=business_metas[i:i+CHROMA_ADD_BATCH_SIZE],
                        )
                    logger.info(f"[{source_id}] Added {len(business_docs)} business context documents")

                # ---------- COLUMNS + OPTIONAL VALUE/RANGE (stream batched) ----------
                for table in tqdm(tables, desc=f"{source_id} Tables"):
                    # Handle both tables and views with the same column loading logic
                    cursor.execute("""
                        SELECT column_name, data_type
                        FROM user_tab_columns
                        WHERE table_name = :table_name
                        ORDER BY column_id
                    """, [table])
                    cols = cursor.fetchall() or []

                    if SCHEMA_MAX_COLS_PER_TABLE > 0:
                        cols = cols[:SCHEMA_MAX_COLS_PER_TABLE]

                    # build column docs first
                    col_docs, col_ids, col_metas = [], [], []
                    for col_name, col_type in cols:
                        # Use enhanced column hints with table context
                        desc = get_enhanced_column_hint(col_name, table)
                        
                        # Enhanced description for system view columns
                        if table.upper().startswith(('USER_', 'ALL_', 'DBA_')):
                            col_doc = (
                                f"Column '{col_name}' in system view '{table}' from {source_id.upper()} database. "
                                f"Type: {col_type}. Purpose: {desc} This is a system view column containing database metadata."
                            )
                        else:
                            col_doc = (
                                f"Column '{col_name}' in table '{table}' from {source_id.upper()} database. "
                                f"Type: {col_type}. Purpose: {desc}"
                            )

                        enhanced_meta = {
                            "source_table": table,
                            "source_id": source_id,
                            "column": col_name,
                            "type": col_type,
                            "kind": "column",
                        }

                        # Add critical flags / key metric markers
                        if table.upper() in CRITICAL_TABLE_ENHANCED_INFO:
                            enhanced_meta["is_critical"] = True
                            info = CRITICAL_TABLE_ENHANCED_INFO[table.upper()]
                            if col_name.upper() in (info.get("key_metrics") or []):
                                enhanced_meta["is_key_metric"] = True
                                col_doc += f" This is a key business metric for {table}."

                        # Mark system view columns
                        if table.upper().startswith(('USER_', 'ALL_', 'DBA_')):
                            enhanced_meta["is_system_view_column"] = True

                        col_id = f"{source_id}.{table}.{col_name}"
                        col_docs.append(col_doc)
                        col_ids.append(col_id)
                        col_metas.append(enhanced_meta)

                    # embed columns in batch
                    if col_docs:
                        col_embs = encode_texts_batch(col_docs, batch_size=EMB_BATCH_SIZE)
                        # push to collection in chunks
                        for i in range(0, len(col_docs), CHROMA_ADD_BATCH_SIZE):
                            collection.add(
                                documents=col_docs[i:i+CHROMA_ADD_BATCH_SIZE],
                                embeddings=col_embs[i:i+CHROMA_ADD_BATCH_SIZE],
                                ids=col_ids[i:i+CHROMA_ADD_BATCH_SIZE],
                                metadatas=col_metas[i:i+CHROMA_ADD_BATCH_SIZE]
                            )
                            total_columns += len(col_ids[i:i+CHROMA_ADD_BATCH_SIZE])

                    # ---------- COLUMN ALIAS DOCS (optional; batched) ----------
                    if INCLUDE_ALIASES and cols:
                        alias_docs_c, alias_ids_c, alias_meta_c = [], [], []
                        for col_name, _col_type in cols:
                            for a in _aliases(col_name):
                                alias_docs_c.append(f"Alias token for column '{col_name}' of '{table}': {a}")
                                alias_ids_c.append(f"{source_id}.{table}.{col_name}::ALIAS::{a}")
                                alias_meta_c.append({"source_table": table, "column": col_name, "source_id": source_id, "kind": "alias"})
                        if alias_docs_c:
                            alias_embs_c = encode_texts_batch(alias_docs_c, batch_size=EMB_BATCH_SIZE)
                            for i in range(0, len(alias_docs_c), CHROMA_ADD_BATCH_SIZE):
                                collection.add(
                                    documents=alias_docs_c[i:i+CHROMA_ADD_BATCH_SIZE],
                                    embeddings=alias_embs_c[i:i+CHROMA_ADD_BATCH_SIZE],
                                    ids=alias_ids_c[i:i+CHROMA_ADD_BATCH_SIZE],
                                    metadatas=alias_meta_c[i:i+CHROMA_ADD_BATCH_SIZE],
                                )
                                alias_column_docs += len(alias_ids_c[i:i+CHROMA_ADD_BATCH_SIZE])

                    # ---------- VALUE SAMPLES / NUMERIC RANGES ----------
                    # Skip value samples and ranges for system views as they're metadata tables
                    if not table.upper().startswith(('USER_', 'ALL_', 'DBA_')):
                        for col_name, col_type in cols:
                            dtype = str(col_type or "").upper()

                            # ---- TEXT SAMPLES (ID-like columns only) ----
                            if INCLUDE_VALUE_SAMPLES and any(t in dtype for t in TEXT_TYPES) and IDLIKE_RX.search(col_name):
                                samples = _sample_text_values(cursor, table, col_name)
                                if samples:
                                    v_docs, v_ids, v_metas = [], [], []
                                    for val, cnt in samples:
                                        pv = (val or "")[:256]
                                        v_docs.append(f"VALUE '{pv}' appears in {source_id}.{table}.{col_name} (frequency ~{cnt}).")
                                        v_ids.append(f"{source_id}.{table}.{col_name}::VAL::{_safe_id_fragment(pv)}")
                                        v_metas.append({
                                            "source_table": table, "source_id": source_id,
                                            "column": col_name, "kind": "column_value",
                                            "value": pv, "freq": cnt
                                        })
                                    v_embs = encode_texts_batch(v_docs, batch_size=EMB_BATCH_SIZE)
                                    for i in range(0, len(v_docs), CHROMA_ADD_BATCH_SIZE):
                                        collection.add(
                                            documents=v_docs[i:i+CHROMA_ADD_BATCH_SIZE],
                                            embeddings=v_embs[i:i+CHROMA_ADD_BATCH_SIZE],
                                            ids=v_ids[i:i+CHROMA_ADD_BATCH_SIZE],
                                            metadatas=v_metas[i:i+CHROMA_ADD_BATCH_SIZE]
                                        )
                                        value_docs += len(v_ids[i:i+CHROMA_ADD_BATCH_SIZE])

                            # ---- NUMERIC RANGE (optional) ----
                            if INCLUDE_NUMERIC_RANGES and any(t in dtype for t in NUM_TYPES):
                                rng = _sample_numeric_range(cursor, table, col_name)
                                if rng:
                                    mn, avg, mx = rng
                                    doc = f"RANGE for {source_id}.{table}.{col_name}: min {mn}, avg {avg}, max {mx}."
                                    rid = f"{source_id}.{table}.{col_name}::RANGE"
                                    emb = get_embedding(doc)
                                    collection.add(
                                        documents=[doc], embeddings=[emb], ids=[rid],
                                        metadatas=[{
                                            "source_table": table, "source_id": source_id,
                                            "column": col_name, "kind": "column_range",
                                            "min": mn, "avg": avg, "max": mx
                                        }]
                                    )
                                    range_docs += 1

                # ✅ No explicit persist() needed with PersistentClient
                business_context_count = len([t for t in tables if t.upper() in CRITICAL_TABLE_ENHANCED_INFO])
                system_view_count = len([t for t in tables if t.upper().startswith(('USER_', 'ALL_', 'DBA_'))])

                logger.info(
                    f"✅ {source_id}: {total_tables} table docs, {total_columns} column docs"
                    + (f", {alias_table_docs} table-alias docs" if INCLUDE_ALIASES else "")
                    + (f", {alias_column_docs} column-alias docs" if INCLUDE_ALIASES else "")
                    + (f", {value_docs} value docs" if INCLUDE_VALUE_SAMPLES else "")
                    + (f", {range_docs} range docs" if INCLUDE_NUMERIC_RANGES else "")
                    + (f", enhanced business context for {business_context_count} critical tables" if business_context_count > 0 else "")
                    + (f", {system_view_count} system views" if system_view_count > 0 else "")
                    + " indexed."
                )


        except Exception as e:
            logger.error(f"❌ Failed to load {source_id}: {e}", exc_info=True)

if __name__ == "__main__":
    load_schema_to_chroma()
