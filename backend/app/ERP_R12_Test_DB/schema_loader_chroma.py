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

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

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
# Enhanced column hints for ERP R12 tables
COLUMN_HINTS = {
    # HR_OPERATING_UNITS table columns
    "BUSINESS_GROUP_ID": "Unique identifier for the business group in ERP R12",
    "ORGANIZATION_ID": "Identifier linking to ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT",
    "NAME": "Name of the operating unit",
    "DATE_FROM": "Start date of the operating unit's validity period",
    "DATE_TO": "End date of the operating unit's validity period. NULL indicates currently active.",
    "SHORT_CODE": "Short code identifier for the operating unit",
    "SET_OF_BOOKS_ID": "Identifier for the set of books. Used in financial reporting.",
    "DEFAULT_LEGAL_CONTEXT_ID": "Default legal context identifier for regulatory compliance",
    "USABLE_FLAG": "Flag indicating if the operating unit is currently usable. Examine actual values in this column to determine appropriate filtering conditions.",
    
    # ORG_ORGANIZATION_DEFINITIONS table columns
    "USER_DEFINITION_ENABLE_DATE": "Date when user definition was enabled",
    "DISABLE_DATE": "Date when the organization was disabled (NULL means active)",
    "ORGANIZATION_CODE": "Code identifier for the organization",
    "ORGANIZATION_NAME": "Name of the organization",
    "CHART_OF_ACCOUNTS_ID": "Identifier for the chart of accounts",
    "INVENTORY_ENABLED_FLAG": "Flag indicating if inventory is enabled for the organization",
    "OPERATING_UNIT": "Identifier linking to HR_OPERATING_UNITS.ORGANIZATION_ID",
    "LEGAL_ENTITY": "Legal entity associated with the organization",
    
    # MTL_ONHAND_QUANTITIES_DETAIL table columns
    "INVENTORY_ITEM_ID": "Identifier for the inventory item",
    "DATE_RECEIVED": "Date when the inventory quantity was received",
    "PRIMARY_TRANSACTION_QUANTITY": "Primary transaction quantity of the item in stock",
    "SUBINVENTORY_CODE": "Subinventory code where the item is located",
    "REVISION": "Revision level of the item",
    "LOCATOR_ID": "Identifier for the physical locator within the subinventory",
    "LOT_NUMBER": "Lot number for lot-controlled items",
    "COST_GROUP_ID": "Identifier for the cost group associated with the item",
    "PROJECT_ID": "Project identifier for project-related inventory",
    "TASK_ID": "Task identifier for project-task-related inventory",
    "ONHAND_QUANTITIES_ID": "Primary key identifier for the onhand quantities record",
    "CONTAINERIZED_FLAG": "Flag indicating if the item is containerized",
    "IS_CONSIGNED": "Flag indicating if the inventory is consigned (owned by supplier)",
    "LPN_ID": "License plate number identifier for the item",
    "STATUS_ID": "Status identifier for the inventory item",
    "MCC_CODE": "Material control code for the item",
    "CREATE_TRANSACTION_ID": "Transaction ID when the record was created",
    "UPDATE_TRANSACTION_ID": "Transaction ID when the record was last updated",
    "ORIG_DATE_RECEIVED": "Original date when the inventory quantity was received",
    "OWNING_ORGANIZATION_ID": "Organization ID that owns the inventory",
    "PLANNING_ORGANIZATION_ID": "Organization ID responsible for planning this inventory",
    "TRANSACTION_UOM_CODE": "Unit of measure code for the transaction quantity",
    "TRANSACTION_QUANTITY": "Transaction quantity of the item",
    "SECONDARY_UOM_CODE": "Secondary unit of measure code",
    "SECONDARY_TRANSACTION_QUANTITY": "Secondary transaction quantity of the item",
    "OWNING_TP_TYPE": "Type of third party that owns the inventory",
    "PLANNING_TP_TYPE": "Type of third party responsible for planning",
    "ORGANIZATION_TYPE": "Type of organization managing the inventory",
    
    # MTL_SECONDARY_INVENTORIES table columns
    "SECONDARY_INVENTORY_NAME": "Name of the secondary inventory subinventory",
    "DESCRIPTION": "Description of the secondary inventory",
    "DISABLE_DATE": "Date when the secondary inventory was disabled (NULL means active)",
    "INVENTORY_ATP_CODE": "Inventory ATP (Available to Promise) code",
    "AVAILABILITY_TYPE": "Availability type for the secondary inventory",
    "RESERVABLE_TYPE": "Reservable type indicator for the secondary inventory",
    "LOCATOR_TYPE": "Locator type for the secondary inventory",
    "PICKING_ORDER": "Order in which items are picked from this subinventory",
    "MATERIAL_ACCOUNT": "Material account associated with the secondary inventory",
    "DEMAND_CLASS": "Demand class assigned to the secondary inventory",
    "SUBINVENTORY_USAGE": "Usage classification of the secondary inventory",
    "PICK_METHODOLOGY": "Picking methodology for the secondary inventory",
    "CARTONIZATION_FLAG": "Flag indicating if cartonization is enabled",
    "DROPPING_ORDER": "Order in which items are dropped in this subinventory",
    "SUBINVENTORY_TYPE": "Type classification of the secondary inventory",
    "PLANNING_LEVEL": "Planning level for the secondary inventory",
    "ENABLE_BULK_PICK": "Flag indicating if bulk picking is enabled",
    "ENABLE_LOCATOR_ALIAS": "Flag indicating if locator aliases are enabled",
    "ENFORCE_ALIAS_UNIQUENESS": "Flag indicating if alias uniqueness is enforced",
    "ENABLE_OPP_CYC_COUNT": "Flag indicating if opportunistic cycle counting is enabled",
    
    # General ERP identifiers
    "ID": "Generic identifier (could be record or entity ID)",
    "NAME": "Name of the entity or record",
    "DESCRIPTION": "Description of the entity or record",
    "ENABLED_FLAG": "Flag indicating if the entity is enabled",
    "CREATION_DATE": "Date when the record was created",
    "CREATED_BY": "User who created the record",
    "LAST_UPDATE_DATE": "Date when the record was last updated",
    "LAST_UPDATED_BY": "User who last updated the record"
}

COLUMN_SYNONYMS = {
    "BUSINESS_GROUP_ID": ["business group id", "bg id", "business group", "group id", "group"],
    "ORGANIZATION_ID": ["organization id", "org id", "organization", "org"],
    "NAME": ["name", "title", "label", "designation"],
    "DATE_FROM": ["date from", "start date", "begin date", "valid from", "validity start"],
    "DATE_TO": ["date to", "end date", "valid to", "validity end"],
    "SHORT_CODE": ["short code", "code", "short", "abbreviation"],
    "SET_OF_BOOKS_ID": ["set of books id", "books id", "set of books", "books"],
    "DEFAULT_LEGAL_CONTEXT_ID": ["default legal context id", "legal entity id", "le id", "default legal entity", "legal context id"],
    "USABLE_FLAG": ["usable flag", "is usable", "active flag", "enabled flag", "status", "currently usable", "usable", "currently active", "active operating unit", "working unit", "functional unit", "availability flag"],
    
    "USER_DEFINITION_ENABLE_DATE": ["user definition enable date", "definition enable date", "enable date"],
    "DISABLE_DATE": ["disable date", "disabled date"],
    "ORGANIZATION_CODE": ["organization code", "org code", "code"],
    "ORGANIZATION_NAME": ["organization name", "org name", "name"],
    "CHART_OF_ACCOUNTS_ID": ["chart of accounts id", "accounts id", "chart"],
    "INVENTORY_ENABLED_FLAG": ["inventory enabled flag", "inventory flag", "inventory"],
    "OPERATING_UNIT": ["operating unit", "unit"],
    "LEGAL_ENTITY": ["legal entity", "entity"],
    
    "INVENTORY_ITEM_ID": ["inventory item id", "item id", "inventory id", "item"],
    "DATE_RECEIVED": ["date received", "received date", "receipt date"],
    "PRIMARY_TRANSACTION_QUANTITY": ["primary transaction quantity", "primary qty", "transaction quantity"],
    "SUBINVENTORY_CODE": ["subinventory code", "subinv code", "subinventory", "subinv"],
    "REVISION": ["revision", "rev"],
    "LOCATOR_ID": ["locator id", "location id", "locator"],
    "LOT_NUMBER": ["lot number", "lot", "batch number", "batch"],
    "COST_GROUP_ID": ["cost group id", "cost group"],
    "PROJECT_ID": ["project id", "project"],
    "TASK_ID": ["task id", "task"],
    "ONHAND_QUANTITIES_ID": ["onhand quantities id", "onhand id"],
    "CONTAINERIZED_FLAG": ["containerized flag", "containerized"],
    "IS_CONSIGNED": ["is consigned", "consigned flag", "consigned"],
    "LPN_ID": ["lpn id", "license plate number id", "license plate"],
    "STATUS_ID": ["status id", "status"],
    "MCC_CODE": ["mcc code", "material control code"],
    "CREATE_TRANSACTION_ID": ["create transaction id", "creation transaction id"],
    "UPDATE_TRANSACTION_ID": ["update transaction id", "last update transaction id"],
    "ORIG_DATE_RECEIVED": ["orig date received", "original date received"],
    "OWNING_ORGANIZATION_ID": ["owning organization id", "owner org id"],
    "PLANNING_ORGANIZATION_ID": ["planning organization id", "planning org id"],
    "TRANSACTION_UOM_CODE": ["transaction uom code", "uom code", "unit of measure code"],
    "TRANSACTION_QUANTITY": ["transaction quantity", "trans qty"],
    "SECONDARY_UOM_CODE": ["secondary uom code", "secondary unit of measure code"],
    "SECONDARY_TRANSACTION_QUANTITY": ["secondary transaction quantity", "secondary qty"],
    "OWNING_TP_TYPE": ["owning tp type", "owner third party type"],
    "PLANNING_TP_TYPE": ["planning tp type", "planning third party type"],
    "ORGANIZATION_TYPE": ["organization type", "org type"],
    
    "SECONDARY_INVENTORY_NAME": ["secondary inventory name", "subinventory name", "secondary inv name"],
    "INVENTORY_ATP_CODE": ["inventory atp code", "atp code", "available to promise code"],
    "AVAILABILITY_TYPE": ["availability type", "availability"],
    "RESERVABLE_TYPE": ["reservable type", "reservable"],
    "LOCATOR_TYPE": ["locator type", "locator"],
    "PICKING_ORDER": ["picking order", "pick order"],
    "MATERIAL_ACCOUNT": ["material account", "mat account"],
    "DEMAND_CLASS": ["demand class", "demand"],
    "SUBINVENTORY_USAGE": ["subinventory usage", "subinv usage"],
    "PICK_METHODOLOGY": ["pick methodology", "picking method"],
    "CARTONIZATION_FLAG": ["cartonization flag", "cartonization"],
    "DROPPING_ORDER": ["dropping order", "drop order"],
    "SUBINVENTORY_TYPE": ["subinventory type", "subinv type"],
    "PLANNING_LEVEL": ["planning level", "plan level"],
    "ENABLE_BULK_PICK": ["enable bulk pick", "bulk pick"],
    "ENABLE_LOCATOR_ALIAS": ["enable locator alias", "locator alias"],
    "ENFORCE_ALIAS_UNIQUENESS": ["enforce alias uniqueness", "alias uniqueness"],
    "ENABLE_OPP_CYC_COUNT": ["enable opp cyc count", "opportunistic cycle count"]
}

def generate_table_description(table_name: str) -> str:
    """Generate descriptions for ERP R12 tables."""
    t = table_name.upper()
    if t == "HR_OPERATING_UNITS":
        return "ERP R12 table containing operating unit definitions with business group associations, validity dates, and organizational structure information. This table contains key business columns like NAME (operating unit names), DEFAULT_LEGAL_CONTEXT_ID (legal entity identifiers), SHORT_CODE (abbreviated identifiers), and USABLE_FLAG (operating unit status)."
    elif t == "ORG_ORGANIZATION_DEFINITIONS":
        return "ERP R12 table defining organizations with their codes, names, and relationships to operating units for inventory and financial management. This table contains key business columns like ORGANIZATION_NAME (organization names), ORGANIZATION_CODE (abbreviated identifiers), CHART_OF_ACCOUNTS_ID (accounting structure identifiers), and INVENTORY_ENABLED_FLAG (inventory status)."
    elif t == "MTL_ONHAND_QUANTITIES_DETAIL":
        return "ERP R12 table containing detailed on-hand inventory quantities with subinventory locations, lot information, and transaction details. This table tracks actual inventory levels and movements."
    elif t == "MTL_SECONDARY_INVENTORIES":
        return "ERP R12 table defining secondary inventories (subinventories) with their attributes, controls, and configurations for inventory management."
    else:
        return f"ERP R12 table '{table_name}' contains unspecified data."

# -------------------------
# Enhanced Critical Table Definitions for ERP R12
# -------------------------
CRITICAL_TABLE_ENHANCED_INFO = {
    "HR_OPERATING_UNITS": {
        "description": "ERP R12 table containing operating unit definitions with business group associations, validity dates, and organizational structure information. This is a core table for ERP organizational hierarchy. Key business columns include NAME (operating unit names), DEFAULT_LEGAL_CONTEXT_ID (legal entity identifiers for compliance), SHORT_CODE (abbreviated identifiers), SET_OF_BOOKS_ID (financial reporting identifiers), and USABLE_FLAG (operating unit status).",
        "business_context": "Used for organizational structure queries, business group analysis, operating unit management, and ERP hierarchy reporting.",
        "key_metrics": ["ORGANIZATION_ID", "BUSINESS_GROUP_ID", "NAME", "DEFAULT_LEGAL_CONTEXT_ID"],
        "common_queries": ["operating unit information", "business group structure", "organizational hierarchy", "ERP structure", "legal context mapping"]
    },
    "ORG_ORGANIZATION_DEFINITIONS": {
        "description": "ERP R12 table defining organizations with their codes, names, and relationships to operating units for inventory and financial management. This table connects to HR_OPERATING_UNITS through the OPERATING_UNIT column. Key business columns include ORGANIZATION_NAME (organization names), ORGANIZATION_CODE (abbreviated identifiers), CHART_OF_ACCOUNTS_ID (accounting structure identifiers), INVENTORY_ENABLED_FLAG (inventory status), and LEGAL_ENTITY (legal entity identifiers).",
        "business_context": "Used for organization definitions, inventory management, financial reporting, and organizational structure analysis.",
        "key_metrics": ["ORGANIZATION_ID", "OPERATING_UNIT", "ORGANIZATION_NAME", "ORGANIZATION_CODE", "CHART_OF_ACCOUNTS_ID"],
        "common_queries": ["organization definitions", "inventory organizations", "financial organizations", "ERP organizational links", "accounting structure mapping"]
    },
    "MTL_ONHAND_QUANTITIES_DETAIL": {
        "description": "ERP R12 table containing detailed on-hand inventory quantities with subinventory locations, lot information, and transaction details. This is a core table for inventory tracking and management. Key business columns include INVENTORY_ITEM_ID (item identifiers), SUBINVENTORY_CODE (storage locations), PRIMARY_TRANSACTION_QUANTITY (quantities on hand), LOT_NUMBER (lot tracking), PROJECT_ID (project-related inventory), and ORGANIZATION_ID (inventory organization).",
        "business_context": "Used for inventory tracking, stock level monitoring, lot tracking, subinventory analysis, and project-related inventory management.",
        "key_metrics": ["INVENTORY_ITEM_ID", "ORGANIZATION_ID", "SUBINVENTORY_CODE", "PRIMARY_TRANSACTION_QUANTITY", "LOT_NUMBER", "PROJECT_ID"],
        "common_queries": ["inventory quantities", "stock levels", "on-hand inventory", "lot tracking", "subinventory analysis", "project inventory"]
    },
    "MTL_SECONDARY_INVENTORIES": {
        "description": "ERP R12 table defining secondary inventories (subinventories) with their attributes, controls, and configurations for inventory management. This table manages subinventory characteristics like availability types, picking methodologies, and usage classifications. Key business columns include SECONDARY_INVENTORY_NAME (subinventory identifiers), DESCRIPTION (descriptions), INVENTORY_ATP_CODE (availability settings), RESERVABLE_TYPE (reservation controls), and SUBINVENTORY_USAGE (usage classification).",
        "business_context": "Used for subinventory configuration, inventory controls, picking methodologies, and warehouse organization structure.",
        "key_metrics": ["SECONDARY_INVENTORY_NAME", "ORGANIZATION_ID", "DESCRIPTION", "INVENTORY_ATP_CODE", "RESERVABLE_TYPE", "SUBINVENTORY_USAGE"],
        "common_queries": ["subinventory definitions", "inventory controls", "warehouse configuration", "picking methods", "subinventory setup"]
    }
}

CRITICAL_COLUMN_ENHANCED_HINTS = {
    # HR_OPERATING_UNITS Columns
    "BUSINESS_GROUP_ID": "Unique identifier for the business group in ERP R12. Links to business group definitions.",
    "ORGANIZATION_ID": "Primary key identifier for the operating unit. Links to ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT for organizational relationships.",
    "NAME": "Name of the operating unit in the ERP system. Used for identification and reporting.",
    "DATE_FROM": "Start date of the operating unit's validity period. Used for temporal analysis.",
    "DATE_TO": "End date of the operating unit's validity period. NULL indicates currently active.",
    "SHORT_CODE": "Short code identifier for the operating unit. Used to identify operating units by their code.",
    "SET_OF_BOOKS_ID": "Identifier for the set of books associated with the operating unit for financial reporting.",
    "DEFAULT_LEGAL_CONTEXT_ID": "Default legal context identifier for regulatory compliance.",
    "USABLE_FLAG": "Flag indicating if the operating unit is currently usable. Examine actual values in this column to determine appropriate filtering conditions.",
    
    # ORG_ORGANIZATION_DEFINITIONS Columns
    "USER_DEFINITION_ENABLE_DATE": "Date when user definition was enabled for the organization.",
    "DISABLE_DATE": "Date when the organization was disabled. NULL indicates currently active.",
    "ORGANIZATION_CODE": "Unique code identifier for the organization used in transactions.",
    "ORGANIZATION_NAME": "Full name of the organization for reporting and identification.",
    "CHART_OF_ACCOUNTS_ID": "Identifier for the chart of accounts structure used by the organization.",
    "INVENTORY_ENABLED_FLAG": "Flag indicating if inventory management is enabled for the organization.",
    "OPERATING_UNIT": "Foreign key linking to HR_OPERATING_UNITS.ORGANIZATION_ID to establish organizational relationships.",
    "LEGAL_ENTITY": "Legal entity associated with the organization for compliance and reporting.",
    
    # MTL_ONHAND_QUANTITIES_DETAIL Columns
    "INVENTORY_ITEM_ID": "Primary identifier for the inventory item. Links to items managed in inventory.",
    "ORGANIZATION_ID": "Identifier linking to ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID to establish organizational relationships.",
    "DATE_RECEIVED": "Date when the inventory quantity was received. Used for temporal analysis of inventory receipts.",
    "PRIMARY_TRANSACTION_QUANTITY": "Primary transaction quantity of the item in stock. Represents the actual quantity on hand in the primary unit of measure.",
    "SUBINVENTORY_CODE": "Subinventory code where the item is physically located.",
    "REVISION": "Revision level of the item. Used for revision-controlled items to track different versions.",
    "LOCATOR_ID": "Identifier for the physical locator within the subinventory.",
    "LOT_NUMBER": "Lot number for lot-controlled items. Used for traceability and expiration tracking of inventory.",
    "COST_GROUP_ID": "Identifier for the cost group associated with the item.",
    "PROJECT_ID": "Project identifier for project-related inventory.",
    "TASK_ID": "Task identifier for project-task-related inventory.",
    "ONHAND_QUANTITIES_ID": "Primary key identifier for the onhand quantities record.",
    "CONTAINERIZED_FLAG": "Flag indicating if the item is containerized.",
    "IS_CONSIGNED": "Flag indicating if the inventory is consigned (owned by supplier).",
    "LPN_ID": "License plate number identifier for the item.",
    "STATUS_ID": "Status identifier for the inventory item.",
    "MCC_CODE": "Material control code for the item.",
    "CREATE_TRANSACTION_ID": "Transaction ID when the record was created.",
    "UPDATE_TRANSACTION_ID": "Transaction ID when the record was last updated.",
    "ORIG_DATE_RECEIVED": "Original date when the inventory quantity was received.",
    "OWNING_ORGANIZATION_ID": "Organization ID that owns the inventory.",
    "PLANNING_ORGANIZATION_ID": "Organization ID responsible for planning this inventory.",
    "TRANSACTION_UOM_CODE": "Unit of measure code for the transaction quantity.",
    "TRANSACTION_QUANTITY": "Transaction quantity of the item.",
    "SECONDARY_UOM_CODE": "Secondary unit of measure code.",
    "SECONDARY_TRANSACTION_QUANTITY": "Secondary transaction quantity of the item.",
    "OWNING_TP_TYPE": "Type of third party that owns the inventory.",
    "PLANNING_TP_TYPE": "Type of third party responsible for planning.",
    "ORGANIZATION_TYPE": "Type of organization managing the inventory.",
    
    # MTL_SECONDARY_INVENTORIES Columns
    "SECONDARY_INVENTORY_NAME": "Name of the secondary inventory subinventory. Primary identifier for subinventories.",
    "ORGANIZATION_ID": "Identifier linking to ORG_ORGANIZATION_DEFINITIONS.ORGANIZATION_ID to establish organizational relationships.",
    "DESCRIPTION": "Description of the secondary inventory.",
    "DISABLE_DATE": "Date when the secondary inventory was disabled. NULL indicates currently active.",
    "INVENTORY_ATP_CODE": "Inventory ATP (Available to Promise) code. Controls availability calculations for demand fulfillment.",
    "AVAILABILITY_TYPE": "Availability type for the secondary inventory.",
    "RESERVABLE_TYPE": "Reservable type indicator for the secondary inventory.",
    "LOCATOR_TYPE": "Locator type for the secondary inventory.",
    "PICKING_ORDER": "Order in which items are picked from this subinventory.",
    "MATERIAL_ACCOUNT": "Material account associated with the secondary inventory.",
    "DEMAND_CLASS": "Demand class assigned to the secondary inventory.",
    "SUBINVENTORY_USAGE": "Usage classification of the secondary inventory.",
    "PICK_METHODOLOGY": "Picking methodology for the secondary inventory.",
    "CARTONIZATION_FLAG": "Flag indicating if cartonization is enabled.",
    "DROPPING_ORDER": "Order in which items are dropped in this subinventory.",
    "SUBINVENTORY_TYPE": "Type classification of the secondary inventory.",
    "PLANNING_LEVEL": "Planning level for the secondary inventory.",
    "ENABLE_BULK_PICK": "Flag indicating if bulk picking is enabled.",
    "ENABLE_LOCATOR_ALIAS": "Flag indicating if locator aliases are enabled.",
    "ENFORCE_ALIAS_UNIQUENESS": "Flag indicating if alias uniqueness is enforced.",
    "ENABLE_OPP_CYC_COUNT": "Flag indicating if opportunistic cycle counting is enabled."
}

def generate_enhanced_table_description(table_name: str) -> str:
    """Generate enhanced descriptions for critical ERP R12 tables with business context."""
    table_upper = table_name.upper()
    if table_upper in CRITICAL_TABLE_ENHANCED_INFO:
        info = CRITICAL_TABLE_ENHANCED_INFO[table_upper]
        description = info["description"]
        business_context = info["business_context"]
        key_metrics = ", ".join(info["key_metrics"])
        common_queries = ", ".join(info["common_queries"])
        return f"{description} {business_context} Key metrics: {key_metrics}. Common use cases: {common_queries}."

    # Fallback to original lightweight heuristics
    return generate_table_description(table_name)

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
    r"(?:^|_)(ID|CODE|NO|NUM|NUMBER|BARCODE|CHALLAN|ORDER|SO|PO|INVOICE|JOB|LOT|REF|TRACK|DOC|VOUCHER|FLAG|STATUS|ENABLED)(?:$|_)",
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
    for source in SOURCES:
        # Only process source_db_2 (ERP R12)
        if source["id"] != "source_db_2":
            continue
            
        source_id = source["id"]
        collection_name = f"{COLLECTION_PREFIX}_{source_id}"

        logger.info(f"\n🔄 Loading schema for ERP R12 DB: {source_id}")
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
                cursor.execute("SELECT table_name FROM user_tables")
                tables = [row[0] for row in cursor.fetchall()] or []

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
                            f"ERP R12 Table '{table}' from {source_id.upper()} database. {table_desc} "
                            f"Business use cases: {', '.join(info['common_queries'])}. "
                            f"This table is frequently used for queries about: "
                            f"ERP organizational structure, operating units, business groups."
                        )
                        enhanced_meta = {
                            "source_table": table,
                            "source_id": source_id,
                            "kind": "table",
                            "is_critical": True,
                            "business_priority": "high",
                        }
                    else:
                        content = f"ERP R12 Table '{table}' from {source_id.upper()} database. Description: {table_desc}"
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
                            alias_docs.append(f"Alias token for ERP R12 table '{table}': {a}")
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
                            ("organizational structure", "operating unit business group hierarchy organization"),
                            ("ERP configuration", "setup definition configuration parameters"),
                            ("financial management", "set of books legal entity chart of accounts"),
                            ("inventory management", "inventory enabled organization code"),
                        ]
                        for context_type, keywords in context_mappings:
                            if any(
                                kw in (info["business_context"] or "").lower()
                                or kw in " ".join(info.get("common_queries", [])).lower()
                                for kw in keywords.split()
                            ):
                                business_doc = (
                                    f"ERP R12 business context: {context_type} using table '{table}'. "
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
                        col_doc = (
                            f"ERP R12 Column '{col_name}' in table '{table}' from {source_id.upper()} database. "
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
                                alias_docs_c.append(f"Alias token for ERP R12 column '{col_name}' of '{table}': {a}")
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
                    for col_name, col_type in cols:
                        dtype = str(col_type or "").upper()

                        # ---- TEXT SAMPLES (ID-like columns only) ----
                        if INCLUDE_VALUE_SAMPLES and any(t in dtype for t in TEXT_TYPES) and IDLIKE_RX.search(col_name):
                            samples = _sample_text_values(cursor, table, col_name)
                            if samples:
                                v_docs, v_ids, v_metas = [], [], []
                                for val, cnt in samples:
                                    pv = (val or "")[:256]
                                    v_docs.append(f"ERP R12 VALUE '{pv}' appears in {source_id}.{table}.{col_name} (frequency ~{cnt}).")
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
                                doc = f"ERP R12 RANGE for {source_id}.{table}.{col_name}: min {mn}, avg {avg}, max {mx}."
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

                logger.info(
                    f"✅ {source_id}: {total_tables} table docs, {total_columns} column docs"
                    + (f", {alias_table_docs} table-alias docs" if INCLUDE_ALIASES else "")
                    + (f", {alias_column_docs} column-alias docs" if INCLUDE_ALIASES else "")
                    + (f", {value_docs} value docs" if INCLUDE_VALUE_SAMPLES else "")
                    + (f", {range_docs} range docs" if INCLUDE_NUMERIC_RANGES else "")
                    + (f", enhanced business context for {business_context_count} critical tables" if business_context_count > 0 else "")
                    + " indexed."
                )


        except Exception as e:
            logger.error(f"❌ Failed to load {source_id}: {e}", exc_info=True)

if __name__ == "__main__":
    load_schema_to_chroma()