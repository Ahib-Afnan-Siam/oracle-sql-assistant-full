import logging
from tqdm import tqdm
from app.db_connector import connect_to_source
from app.embeddings import get_embedding
from app.config import SOURCES
import chromadb
from chromadb.config import Settings

COLLECTION_NAME = "schema_docs"


def get_chroma_client():
    return chromadb.PersistentClient(
        path="chroma_db",
        settings=Settings(anonymized_telemetry=False)
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Semantic descriptions
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
    "LOCATIONID": "Location ID",
    "BUID": "Business unit ID",
    "SECTIONID": "Section ID",
    "SUID": "Subunit ID",
    "LINEID": "Line ID",

    "COMP_ID": "Company ID",
    "COMP_NAME": "Company name",
    "COMP_ADDR": "Company address",
    "COMP_CNCL": "Cancel flag for company",

    "DEPT_NAME": "Name of department",
    "DEPT_CTPR": "Department contact person",
    "DEPT_MOBI": "Department mobile",
    "DEPT_EMAL": "Department email",
    "DEPT_CNCL": "Cancel status of department",

    "LIMP_ID": "Link map ID",
    "LIMP_FLIN": "From line",
    "LIMP_TLIN": "To line",
    "LIMP_CNCL": "Cancel flag",

    "LNSM_ID": "Line shift mapping ID",
    "LNSM_DATE": "Mapping date",
    "LNSM_PFLN": "Production floor line",
    "LNSM_STAT": "Status code",
    "LNSM_RMAK": "Remarks",

    "LOCT_ID": "Location ID",
    "LOCT_NAME": "Location name",
    "LOCT_ADDR": "Location address",
    "LOCT_STA": "Location status",

    "NPTD_DATE": "Non-productive time date",
    "NPTD_NPTT": "NPT type",
    "NPTD_NPTM": "NPT reason or name",
    "NPTD_STME": "Start time",
    "NPTD_ETME": "End time",
    "NPTD_UNIT": "Unit",
    "NPTD_LINE": "Line name",
    "NPTD_BUYR": "Buyer",
    "NPTD_STYL": "Style",
    "NPTD_CLST": "Cluster",

    "NPTM_NAMR": "NPT master name",
    "NPTM_DEPT": "Department",
    "NPTM_CNCL": "Cancel flag",
    "NPTM_SVRT": "Severity or version",

    "BUYER_NAME": "Buyer name",
    "STYLEPO": "Style PO",
    "STYLE": "Garment style",
    "ITEM_NAME": "Item name",
    "FACTORY": "Factory name",
    "POQTY": "Purchase order quantity",
    "CUTQTY": "Cut quantity",
    "SINPUT": "Sewing input",
    "SOUTPUT": "Sewing output",
    "SHIPQTY": "Shipment quantity",
    "LEFTQTY": "Leftover quantity",
    "FOBP": "FOB price",
    "SMV": "Standard minute value",
    "CM": "Cost of manufacturing",
    "CEFFI": "Cutting efficiency",
    "AEFFI": "Actual efficiency",
    "CMER": "Cost per merchandiser",
    "ACM": "Average CM",
    "EXMAT": "Extra material",
    "SHIPDATE": "Shipment date",

    "PFLN_ID": "Production floor line ID",
    "PFLN_UNLC": "Unit location",
    "PFLN_NAME": "Line name",
    "PFLN_CNNM": "Contact name",
    "PFLN_CNEM": "Contact email",
    "PFLN_CNMB": "Contact mobile",
    "PFLN_CNID": "Contact ID",
    "PFLN_TYPE": "Line type",
    "PFLN_COMP": "Company",

    "PROD_DATE": "Production date",
    "FLOOR_NAME": "Factory floor name",
    "PM_OR_APM_NAME": "PM or APM in charge",
    "FLOOR_EF": "Floor efficiency",
    "DHU": "Defects per hundred units",
    "DEFECT_QTY": "Defect quantity",
    "PRODUCTION_QTY": "Produced quantity",
    "DEFECT_PERS": "Defect percentage",
    "UNCUT_THREAD": "Uncut thread count",
    "DIRTY_STAIN": "Dirty or stained items",
    "BROKEN_STITCH": "Broken stitches",
    "SKIP_STITCH": "Skipped stitches",
    "OPEN_SEAM": "Open seams",
    "LAST_UPDATE": "Last update timestamp",
    "AC_PRODUCTION_HOUR": "Actual production hours",
    "AC_WORKING_HOUR": "Actual working hours",

    "PROT_ID": "Protocol ID",
    "PROT_DESC": "Protocol description",

    "SMSG": "Message",
    "SMSG_TIME": "Timestamp",
    "SMSG_DATE": "Message date",
    "SMSG_USER": "Message user",
    "SMSG_STAT": "Message status",
    "SMSG_NOTE": "Message notes",
    "SMSG_CLSU": "Closed by user",
    "SMSG_CLSC": "Close comment",
    "SMSG_CLSD": "Close date",
    "SMSG_COMP": "Company involved",

    "SSIS_ID": "Session issue ID",
    "SSIS_ISSM": "Issue name",
    "SSIS_CNCL": "Cancellation flag",

    "USER_ID": "User ID",
    "USERNAME": "Username",
    "FULL_NAME": "Full name",
    "PHONE_NUMBER": "Phone number",
    "EMAIL_ADDRESS": "Email address",
    "IMAGE": "User image",
    "IS_ACTIVE": "Active flag",
    "PIN": "User PIN",
    "FILENAME": "Uploaded file name",
    "LAST_UPDATED": "Last updated timestamp",
    "ADDED_DATE": "Added to system",
    "UPDATE_DATE": "Updated on",
    "MIME_TYPE": "MIME type",
    "LAST_LOGIN": "Last login time",
}


# Synonyms to improve match
COLUMN_SYNONYMS = {
    "DEPTNO": ["department number", "dept no", "dept id"],
    "DNAME": ["department name", "dept name"],
    "LOC": ["location of department", "location"],

    "EMPNO": ["employee id", "emp id", "employee number"],
    "ENAME": ["employee name", "name", "emp name"],
    "JOB": ["job title", "designation", "role", "position"],
    "MGR": ["manager id", "supervisor id"],
    "HIREDATE": ["hire date", "joining date", "date of hire"],
    "SAL": ["salary", "pay", "monthly salary"],
    "COMM": ["commission", "bonus"],

    "ID": ["record id", "task id", "generic id"],
    "TASK_NAME": ["task name", "full task name"],
    "TASK_SHORT_NAME": ["task short name", "task code"],
    "TASK_TYPE": ["task type", "task category"],
    "STATUS_ACTIVE": ["status", "active flag", "is active"],
    "TASK_GROUP": ["task group", "group name"],
    "TASK_OWNER": ["task owner", "responsible person"],

    "A_DATE": ["activity date", "date"],
    "LOCATION_NAME": ["location name", "location"],
    "BU_NAME": ["business unit name", "unit name"],
    "SECTION_NAME": ["section name", "section"],
    "LINE_NAME": ["line name", "production line"],
    "SUBUNIT_NAME": ["subunit name", "team name"],
    "TOTAL_PRESENTS": ["total presents", "present count", "attendance count"],
    "OT_HOUR": ["overtime hours", "ot"],
    "OT_AMOUNT": ["ot amount", "overtime pay"],

    "COMP_ID": ["company id"],
    "COMP_NAME": ["company name"],
    "COMP_ADDR": ["company address"],
    "COMP_CNCL": ["cancel flag"],

    "DEPT_NAME": ["department name", "dept name"],
    "DEPT_CTPR": ["contact person"],
    "DEPT_MOBI": ["mobile", "phone"],
    "DEPT_EMAL": ["email", "department email"],
    "DEPT_CNCL": ["department cancel"],

    "LOCT_NAME": ["location name"],
    "LOCT_ADDR": ["location address"],
    "LOCT_STA": ["location status"],

    "BUYER_NAME": ["buyer", "buyer name"],
    "STYLEPO": ["style po", "style purchase order"],
    "STYLE": ["style", "garment style"],
    "ITEM_NAME": ["item name", "product name"],
    "FACTORY": ["factory", "factory name"],
    "POQTY": ["po quantity", "purchase quantity"],
    "SHIPQTY": ["shipment quantity", "shipped"],
    "SHIPDATE": ["shipment date", "delivery date"],

    "PROD_DATE": ["production date", "prod date"],
    "FLOOR_NAME": ["floor name", "factory floor"],
    "PM_OR_APM_NAME": ["pm name", "apm name"],
    "FLOOR_EF": ["efficiency", "floor efficiency"],
    "DHU": ["defects per hundred", "dhu"],
    "DEFECT_QTY": ["defect quantity", "defects"],
    "PRODUCTION_QTY": ["produced quantity", "output quantity"],
    "DEFECT_PERS": ["defect percentage", "defect rate"],
    "UNCUT_THREAD": ["uncut threads"],
    "DIRTY_STAIN": ["dirty items", "stains"],
    "BROKEN_STITCH": ["broken stitch", "stitch issues"],
    "SKIP_STITCH": ["skip stitch", "stitch error"],
    "OPEN_SEAM": ["open seam", "open stitching"],

    "FULL_NAME": ["full name", "name"],
    "USERNAME": ["username", "user name"],
    "EMAIL_ADDRESS": ["email", "email address"],
    "PHONE_NUMBER": ["phone", "phone number"],
    "USER_ID": ["user id", "uid"],
    "IS_ACTIVE": ["active", "status"],
    "PIN": ["pin", "user pin"]
}


def enrich_column(col_name: str, col_type: str) -> str:
    desc = COLUMN_HINTS.get(col_name.upper(), "No description available")
    synonyms = COLUMN_SYNONYMS.get(col_name.upper(), [])
    line = f"- {col_name} ({col_type}): {desc}"
    if synonyms:
        line += f" [Synonyms: {', '.join(synonyms)}]"
    return line

def load_schema_to_chroma():
    source_db = SOURCES[0]

    with connect_to_source(source_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM user_tables")
        tables = [row[0] for row in cursor.fetchall()]

        chroma_client = get_chroma_client()
        if COLLECTION_NAME in [c.name for c in chroma_client.list_collections()]:
            chroma_client.delete_collection(name=COLLECTION_NAME)
        collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)

        total_loaded = 0
        for table in tqdm(tables, desc="Batches"):
            cursor.execute(f"""
                SELECT column_name, data_type
                FROM user_tab_columns
                WHERE table_name = :table_name
                ORDER BY column_id
            """, [table])
            columns = cursor.fetchall()
            if not columns:
                continue

            # Build enriched schema chunk
            chunk_lines = [f"TABLE: {table}"]
            chunk_lines.append(f"This table stores data related to {table.lower().replace('_', ' ')}.")
            chunk_lines.append("COLUMNS:")
            column_names = []

            for col_name, col_type in columns:
                chunk_lines.append(enrich_column(col_name, col_type))
                column_names.append(col_name)

            chunk_lines.append(f"KEYWORDS: {table.upper()}, {', '.join(column_names)}")
            chunk_text = "\n".join(chunk_lines)
            embedding = get_embedding(chunk_text)
            doc_id = f"{table}_schema"

            collection.add(
                documents=[chunk_text],
                embeddings=[embedding],
                ids=[doc_id],
                metadatas=[{"source_table": table}]
            )

            logger.info(f"[✓] Loaded: {table} → {len(columns)} columns")
            total_loaded += 1

    logger.info(f"\n✅ Total Tables Loaded into ChromaDB: {total_loaded}")

if __name__ == "__main__":
    load_schema_to_chroma()
