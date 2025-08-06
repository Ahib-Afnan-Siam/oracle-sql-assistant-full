import re
import json
import logging
from typing import List
from app.llm_client import call_llm
from app.vector_store import search_vector_store_detailed
from app.ollama_llm import ask_sql_model  # Added for DeepSeek-Coder refinement

logger = logging.getLogger(__name__)

# -------------------
# Expanded Rule-Based Keywords
# -------------------

SALES_KEYWORDS = [
    "sales", "revenue", "order", "orders", "buyer", "buyers",
    "style", "styles", "ship", "shipment", "poqty", "shipqty", "poqty",
    "profit", "fobp", "smv", "cmer", "acm", "quantity", "qty",
    "top", "best-selling", "factory", "cutqty", "sinput", "soutput", "leftqty"
]

POLICY_KEYWORDS = [
    "policy", "leave", "vacation", "holiday", "hr", "benefit",
    "guideline", "document", "attendance", "company policy"
]

EMP_DEPT_KEYWORDS = [
    "employee", "employees", "emp", "ename", "salary", "sal",
    "dept", "department", "deptno", "manager", "hiredate",
    "commission", "comm", "loc", "full_name", "user", "users"
]

PRODUCTION_KEYWORDS = [
    "production", "prod", "floor", "floors", "dhu", "defect",
    "open seam", "skip stitch", "output", "input",
    "ac working hour", "ac production hour", "units", "efficiency"
]

OVERTIME_KEYWORDS = [
    "overtime", "ot", "ot hour", "ot amount", "daily ot",
    "presents", "section", "line", "bu_name", "shift"
]

# -----------------------
# Rule-based Classifier
# -----------------------

def detect_intent(query: str) -> dict:
    """Detect intent using keywords, fallback to LLM if needed."""
    query_lower = query.lower()

    # Check each category
    if any(kw in query_lower for kw in POLICY_KEYWORDS):
        return {"intent": "policy_doc", "confidence": 0.9}

    if any(kw in query_lower for kw in SALES_KEYWORDS):
        return {"intent": "sales_data", "confidence": 0.9}

    if any(kw in query_lower for kw in PRODUCTION_KEYWORDS):
        return {"intent": "production_data", "confidence": 0.9}

    if any(kw in query_lower for kw in EMP_DEPT_KEYWORDS):
        return {"intent": "employee_data", "confidence": 0.9}

    if any(kw in query_lower for kw in OVERTIME_KEYWORDS):
        return {"intent": "overtime_data", "confidence": 0.9}

    # Fallback to LLM-based classification
    prompt = f"""
    Classify the following user query into one of these categories:
    - sales_data (sales, revenue, product performance, orders)
    - policy_doc (HR policies, company guidelines, leave)
    - employee_data (employee, department, job info)
    - production_data (production, defects, floor efficiency)
    - overtime_data (overtime, OT hours, OT amount)
    - general (anything else)

    Query: "{query}"

    Answer in JSON format with fields: intent, confidence (0-1).
    """
    try:
        llm_response = call_llm(prompt)
        return json.loads(llm_response)
    except Exception:
        return {"intent": "general", "confidence": 0.5}


# -----------------------
# Table Mapping
# -----------------------
TABLE_MAP = {
    "sales_data": ["T_ORDC", "T_TNA_STATUS", "V_TNA_STATUS", "T_COMP", "T_TRST", "T_NPTD", "T_NPTM"],
    "employee_data": ["EMP", "DEPT", "T_USERS", "T_DEPT", "T_UCOM", "T_ULIN", "T_UNLC"],
    "production_data": ["T_PROD", "T_PROD_DAILY", "XX_DAILY_PROD_STATUS", "XX_DAILY_PROD_STATUS_DAILY", "T_PFLN", "T_SOSM", "T_SSIS", "T_SSTP"],
    "overtime_data": ["T_DAILY_OT", "T_DAILY_OT_Z", "SOS_TEMP_TABLE", "V_OT_RPT"],
    "policy_doc": []
}


# -----------------------
# Semantic Fallback
# -----------------------
def find_relevant_tables(user_query: str, top_k=3) -> List[str]:
    """
    Use ChromaDB semantic search to find the most relevant tables for a user query.
    """
    results = search_vector_store_detailed(user_query, top_k=top_k)
    tables = {r["metadata"].get("table") for r in results if "table" in r["metadata"]}
    return list(tables)


# -----------------------
# DeepSeek-Coder Refinement
# -----------------------
def refine_table_selection(user_query: str, candidate_tables: list) -> list:
    """
    Use DeepSeek-Coder to refine table selection among candidate tables.
    """
    if not candidate_tables:
        return []

    prompt = f"""
    You are a SQL expert.
    User query: "{user_query}"

    Candidate tables:
    {', '.join(candidate_tables)}

    Select the most relevant tables (1 to 3) that are required to answer the query.
    Answer ONLY with a JSON list of table names. Example: ["T_ORDC", "T_PROD_DAILY"]
    """

    try:
        response = ask_sql_model(prompt).strip()
        logger.info(f"[RefineTables] Raw LLM response: {response}")
        import json
        selected_tables = json.loads(response)
        selected_tables = [t for t in selected_tables if t in candidate_tables]
        return selected_tables
    except Exception as e:
        logger.warning(f"[RefineTables] LLM refinement failed: {e}")
        return candidate_tables  # fallback


# -----------------------
# Intent + Table Logic
# -----------------------
def get_tables_for_intent(intent: str, user_query: str = None):
    """
    Get tables for detected intent. Fallback to semantic search + LLM refinement if no table found.
    """
    tables = TABLE_MAP.get(intent, [])
    if not tables and user_query:
        logger.warning("[Intent] No tables from keywords. Falling back to ChromaDB semantic intent detection.")
        tables = find_relevant_tables(user_query)
        logger.info(f"[Intent] Semantic fallback tables before refinement: {tables}")

        if len(tables) > 1:
            tables = refine_table_selection(user_query, tables)
            logger.info(f"[Intent] Tables after LLM refinement: {tables}")

    return tables


# -----------------------
# Test
# -----------------------
if __name__ == "__main__":
    test_queries = [
        "Show me the sales summary for Product X in the last quarter.",
        "What is the HR leave policy?",
        "List all employees in department 10.",
        "How many units were produced on Sewing Floor-5 yesterday?",
        "What is the OT amount for section A?",
        "Get job details for employee KING",
        "Tell me something random."
    ]
    for q in test_queries:
        intent_result = detect_intent(q)
        print(f"Query: {q} -> {intent_result}, Tables: {get_tables_for_intent(intent_result['intent'], q)}")
