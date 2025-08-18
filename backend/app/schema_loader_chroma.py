# app/schema_loader_chroma.py
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

from chromadb.telemetry.posthog import Posthog
def _no_capture(*args, **kwargs):
    return None
Posthog.capture = _no_capture

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION_PREFIX = "schema_docs"

# --------- Ingest switches / limits via env ---------
INCLUDE_VALUE_SAMPLES = os.getenv("INCLUDE_VALUE_SAMPLES", "false").lower() == "true"
INCLUDE_NUMERIC_RANGES = os.getenv("INCLUDE_NUMERIC_RANGES", "false").lower() == "true"
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

def create_table_descriptions(tables):
    return {table: generate_table_description(table) for table in tables}

def _safe_id_fragment(s: str) -> str:
    s = (s or "")[:128]
    return re.sub(r"[\s\r\n\t]+", "_", s)

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

def load_schema_to_chroma():
    for source in SOURCES:
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

        try:
            with connect_to_source(source_id) as (conn, _):
                cursor = conn.cursor()
                cursor.execute("SELECT table_name FROM user_tables")
                tables = [row[0] for row in cursor.fetchall()] or []

                if SCHEMA_MAX_TABLES > 0:
                    tables = tables[:SCHEMA_MAX_TABLES]

                table_descriptions = create_table_descriptions(tables)

                # ---------- TABLE DOCS (batched) ----------
                table_docs, table_ids, table_metas = [], [], []
                for table in tables:
                    table_desc = table_descriptions.get(table.upper(), "No description available for this table")
                    content = f"Table '{table}' from {source_id.upper()} database. Description: {table_desc}"
                    doc_id = f"{source_id}.{table}"
                    table_docs.append(content)
                    table_ids.append(doc_id)
                    table_metas.append({"source_table": table, "source_id": source_id, "kind": "table"})
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
                        desc = COLUMN_HINTS.get(col_name.upper(), "No description available")
                        col_doc = (
                            f"Column '{col_name}' in table '{table}' from {source_id.upper()} database. "
                            f"Type: {col_type}. Purpose: {desc}"
                        )
                        col_id = f"{source_id}.{table}.{col_name}"
                        col_docs.append(col_doc)
                        col_ids.append(col_id)
                        col_metas.append({
                            "source_table": table,
                            "source_id": source_id,
                            "column": col_name,
                            "type": col_type,
                            "kind": "column"
                        })

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

                    # Optional value/range docs (kept tiny)
                    for col_name, col_type in cols:
                        dtype = str(col_type or "").upper()
                        # text samples
                        if INCLUDE_VALUE_SAMPLES and any(t in dtype for t in TEXT_TYPES):
                            samples = _sample_text_values(cursor, table, col_name)
                            if samples:
                                v_docs, v_ids, v_metas = [], [], []
                                for val, cnt in samples:
                                    pv = val[:256]
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

                        # numeric range (min/avg/max only)
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
                logger.info(
                    f"✅ {source_id}: {total_tables} table docs, {total_columns} column docs"
                    + (f", {value_docs} value docs" if INCLUDE_VALUE_SAMPLES else "")
                    + (f", {range_docs} range docs" if INCLUDE_NUMERIC_RANGES else "")
                    + " indexed."
                )

        except Exception as e:
            logger.error(f"❌ Failed to load {source_id}: {e}", exc_info=True)

if __name__ == "__main__":
    load_schema_to_chroma()
