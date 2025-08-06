import logging
import re
from typing import List, Generator, Dict, Any, Optional
from tabulate import tabulate
from datetime import datetime
import json
from itertools import islice

from app.vector_store_chroma import search_vector_store_detailed
from app.ollama_llm import call_ollama, ask_summary_model
from app.db_connector import connect_to_source
from app.config import SOURCES, OLLAMA_SQL_MODEL
from app.summarizer import stream_summary

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_sql_prompt(schema_chunks: list, user_query: str) -> str:
    context = "\n\n".join(schema_chunks)
    prompt = f"""
You are an expert Oracle SQL assistant.
Generate a single valid SELECT SQL statement based on the given schema and user query.
Do not include explanations.

IMPORTANT RULES:
1. NEVER use bind variables (like :var)
2. If specific values are needed but not provided in the query, omit that condition
3. Only use values explicitly mentioned in the user query

COLUMN MEANINGS:
- EMPNO: Employee ID
- ENAME: Employee Name
- JOB: Job Title
- MGR: Manager ID (refers to manager's EMPNO)
- HIREDATE: Hire Date
- SAL: Monthly Salary (in dollars)
- COMM: Sales Commission (in dollars)
- DEPTNO: Department Number (not a bonus)

SCHEMA:
{context}

USER QUESTION:
{user_query}

SQL:
"""
    return prompt.strip()

def is_valid_sql(sql: str) -> bool:
    # Check for bind variables
    if re.search(r':\w+', sql, re.IGNORECASE):
        logger.warning("SQL contains bind variables, which is invalid.")
        return False
    
    # Check basic SQL structure
    if not sql.strip().lower().startswith("select"):
        return False
    if ";" in sql or sql.count("select") > 1:
        return False

    try:
        with connect_to_source(SOURCES[0]) as conn:
            cursor = conn.cursor()
            cursor.execute("EXPLAIN PLAN FOR " + sql)
            return True
    except Exception as e:
        logger.warning(f"[Validation Fail] SQL is invalid: {e}")
        return False

def retry_with_stricter_prompt(user_query: str, schema_chunks: list) -> str:
    context = "\n\n".join(schema_chunks)
    strict_prompt = f"""
You are an Oracle SQL expert.

STRICT MODE:
1. Generate only ONE valid Oracle SELECT SQL statement
2. No explanations or comments
3. NEVER use bind variables (like :var)
4. If specific values are needed but not provided, omit the condition

COLUMN MEANINGS:
- DEPTNO: Department Number (not a bonus)
- COMM: Sales Commission
- MGR: Manager ID

CONTEXT:
{context}

USER QUESTION:
{user_query}

SQL:
"""
    return call_ollama(strict_prompt.strip(), model=OLLAMA_SQL_MODEL)

def handle_bind_variables(sql: str, user_query: str) -> str:
    """Remove conditions with bind variables or replace with reasonable values"""
    # If bind variables exist, remove the condition
    if re.search(r':\w+', sql, re.IGNORECASE):
        logger.warning(f"Removing condition with bind variables for query: {user_query}")
        
        # Remove WHERE clause containing bind variable
        sql = re.sub(r'WHERE\s+.*?=.*?:\w+.*?(?=;|$)', '', sql, flags=re.IGNORECASE)
        
        # Remove AND/OR clauses with bind variables
        sql = re.sub(r'(AND|OR)\s+.*?=.*?:\w+', '', sql, flags=re.IGNORECASE)
        
        # Clean up dangling WHERE/AND/OR
        sql = re.sub(r'\s+WHERE\s*$', '', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\s+(AND|OR)\s*$', '', sql, flags=re.IGNORECASE)
        
        logger.info(f"Modified SQL after bind variable removal: {sql}")
    
    return sql

def run_sql(sql: str) -> list:
    source_db = SOURCES[0]
    with connect_to_source(source_db) as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]

def determine_display_mode(user_query: str, rows: list) -> str:
    """
    Intelligently determine the display mode based on user query and result characteristics.
    Returns: 'summary', 'table', or 'both'
    """
    user_query = user_query.lower()
    
    # Dynamic intent detection using NLP patterns
    summary_intent_phrases = [
        "summarize", "report", "insight", "analyze", "explain", "describe",
        "overview", "conclude", "key findings", "what does this mean",
        "interpret", "breakdown", "highlight", "key points", "brief",
        "insights", "analysis", "summary", "report", "findings", "conclusion"
    ]
    
    table_intent_phrases = [
        "list", "show", "display", "grid", "tabular", "view", "see",
        "present", "as a table", "in a table", "in tabular form", "table",
        "rows", "columns", "data", "entries", "records", "details"
    ]
    
    both_intent_phrases = [
        "both", "and", "with", "including", "along with", "plus", "also",
        "detailed report", "complete view", "full picture", "alongside",
        "together with", "comprehensive", "with analysis", "with summary"
    ]
    
    # Detect intent using phrase matching
    has_summary = any(phrase in user_query for phrase in summary_intent_phrases)
    has_table = any(phrase in user_query for phrase in table_intent_phrases)
    has_both = any(phrase in user_query for phrase in both_intent_phrases)
    
    # Check for implicit analytical requests
    analytical_indicators = {
        "compare", "trend", "performance", "growth", "change", "difference",
        "correlation", "relationship", "pattern", "distribution", "breakdown",
        "insight", "analyze", "evaluate", "assessment", "examine", "study",
        "review", "diagnose", "interpret", "understand", "observe"
    }
    
    # Count analytical terms in query
    analytical_term_count = sum(1 for term in analytical_indicators if term in user_query)
    
    # Explicit requests take highest priority
    if has_both or (has_summary and has_table):
        return "both"
    if has_summary:
        return "summary"
    if has_table:
        return "table"
    
    # Default behavior based on query and results
    if not rows:
        return "summary"
    
    # For analytical queries, show both
    if analytical_term_count >= 1:  # At least 1 analytical term
        return "both"
    
    # For count queries, show summary
    if "count" in user_query or "how many" in user_query or "number of" in user_query:
        return "summary"
    
    # For small result sets, show both
    if len(rows) <= 5:
        return "both"
    
    # For large result sets, show table
    if len(rows) > 50:
        return "table"
    
    # Default to table for most queries
    return "table"

def validate_query_match(user_query: str, summary: str) -> bool:
    """
    Ensure the summary actually addresses the user's query
    """
    # Skip validation for analytical queries
    if "swing" in user_query.lower() or "summary" in user_query.lower():
        logger.info(f"Skipping validation for analytical query: {user_query}")
        return True
    
    user_query = user_query.lower()
    summary = summary.lower()
    
    # Filter out stopwords and short terms
    stopwords = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with"}
    key_terms = [term for term in user_query.split() 
                 if len(term) > 3 and term not in stopwords]
    
    # If no meaningful terms, consider it valid
    if not key_terms:
        return True
    
    # Count matching terms
    matching_terms = sum(1 for term in key_terms if term in summary)
    
    # At least 50% of key terms should appear
    if matching_terms / len(key_terms) < 0.5:
        logger.warning(f"Summary doesn't match query. Query: {user_query}, Summary: {summary[:100]}...")
        return False
    return True

def summarize_results(rows: list, user_query: str) -> str:
    if not rows:
        return "No results found."

    keys = list(rows[0].keys())
    # Include headers in preview
    header = " | ".join(keys)
    data_rows = "\n".join([" | ".join([str(row.get(k, '')) for k in keys]) for row in rows[:5]])
    preview = f"{header}\n{data_rows}"

    prompt = f"""
You are a data analyst. Explain these results in relation to the user's query.

USER QUERY: {user_query}

COLUMN MEANINGS:
- DEPTNO: Department Number (not bonus)
- COMM: Sales Commission
- MGR: Manager ID
- SAL: Monthly Salary

DATA (first row is header):
{preview}

Guidelines:
1. NEVER invent numbers not in data
2. NEVER confuse DEPTNO with bonuses
3. Explain manager relationships using IDs
4. Use exact column names from header
5. ALWAYS address the user's EXACT query

Only return a clean, concise answer for the user.
"""
    return ask_summary_model(prompt.strip())

def render_table_markdown(rows: list) -> str:
    if not rows:
        return ""
    headers = rows[0].keys()
    data = [list(r.values()) for r in rows]
    return "```\n" + tabulate(data, headers, tablefmt="grid") + "\n```"

def process_question(user_query: str) -> dict:
    logger.info(f"[User Query] {user_query}")

    results = search_vector_store_detailed(user_query, top_k=5)
    schema_chunks = [r["document"] for r in results] if results else []
    if not schema_chunks:
        return {"error": "No schema context found."}

    prompt = generate_sql_prompt(schema_chunks, user_query)
    logger.debug(f"[SQL Prompt]\n{prompt}")

    sql = call_ollama(prompt, model=OLLAMA_SQL_MODEL)
    sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
    
    # Handle bind variables before validation
    sql = handle_bind_variables(sql, user_query)
    logger.info(f"[Generated SQL] {sql}")

    if not is_valid_sql(sql):
        logger.warning("[Retry] Initial SQL failed. Retrying with stricter prompt.")
        sql = retry_with_stricter_prompt(user_query, schema_chunks)
        sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
        
        # Handle bind variables again in retry
        sql = handle_bind_variables(sql, user_query)
        logger.info(f"[Retry SQL] {sql}")
        
        if not is_valid_sql(sql):
            return {"error": "Retry also failed. Invalid SQL.", "sql": sql}

    try:
        rows = run_sql(sql)
    except Exception as e:
        logger.error(f"[Oracle Error] {e}")
        return {"error": f"Oracle query failed: {str(e)}", "sql": sql}

    display_mode = determine_display_mode(user_query, rows)
    summary = ""
    
    if display_mode in ["summary", "both"]:
        summary = summarize_results(rows, user_query) if rows else "No results found."
        # Validate summary matches query
        if not validate_query_match(user_query, summary):
            return {
                "error": "Summary doesn't match query. Please try rephrasing.",
                "sql": sql,
                "results": {
                    "columns": list(rows[0].keys()) if rows else [],
                    "rows": [list(r.values()) for r in rows] if rows else [],
                    "row_count": len(rows)
                }
            }
    
    if display_mode == "table":
        summary = render_table_markdown(rows)
    elif display_mode == "both":
        summary += "\n\nHere is the table:\n" + render_table_markdown(rows)

    logger.info(f"[Display Mode] {display_mode}")
    return {
        "status": "success",
        "summary": summary,
        "sql": sql,
        "display_mode": display_mode,
        "results": {
            "columns": list(rows[0].keys()) if rows else [],
            "rows": [list(r.values()) for r in rows] if rows else [],
            "row_count": len(rows)
        },
        "schema_context": schema_chunks,
        "phases": [
            "Generating SQL...",
            "SQL generated!",
            "Parsing table...",
            "Table parsed!",
            "Summarizing..."
        ]
    }

def safe_json(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def run_sql_streaming(sql: str, chunk_size: int = 20) -> Generator[Dict[str, Any], None, None]:
    source_db = SOURCES[0]
    try:
        with connect_to_source(source_db) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)

            if not cursor.description:
                yield {"columns": ["Result"], "rows": [["Query executed successfully"]]}
                return

            columns = [desc[0] for desc in cursor.description]
            yield {"columns": columns}

            while True:
                rows = cursor.fetchmany(chunk_size)
                if not rows:
                    break

                serialized_rows = [
                    [safe_json(item) for item in row]
                    for row in rows
                ]

                yield {"rows": serialized_rows}

    except Exception as e:
        logger.error(f"SQL execution error: {e}")
        yield {"error": f"Database error: {str(e)}"}

def format_preview_for_summary(rows: list, limit: int = 10) -> str:
    if not rows:
        return ""
    # Handle both dict and list formats
    if isinstance(rows[0], dict):
        keys = list(rows[0].keys())
        header = " | ".join(keys)
        data_rows = [header]
        for row in islice(rows, limit):
            data_rows.append(" | ".join([str(row.get(k, '')) for k in keys]))
        return "\n".join(data_rows)
    else:
        # Handle list of lists format
        if not rows or not rows[0]:
            return ""
        header = " | ".join([str(item) for item in rows[0]])
        data_rows = [header]
        for row in islice(rows[1:], limit):
            data_rows.append(" | ".join([str(item) for item in row]))
        return "\n".join(data_rows)

def process_question_streaming(user_query: str) -> Generator[Dict[str, Any], None, None]:
    yield {"phase": "Generating SQL..."}

    results = search_vector_store_detailed(user_query, top_k=5)
    schema_chunks = [r["document"] for r in results] if results else []
    if not schema_chunks:
        yield {"error": "No schema context found."}
        return

    prompt = generate_sql_prompt(schema_chunks, user_query)
    sql = call_ollama(prompt, model=OLLAMA_SQL_MODEL)
    sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
    
    # Handle bind variables before validation
    sql = handle_bind_variables(sql, user_query)
    logger.info(f"[Generated SQL] {sql}")

    yield {"phase": "SQL generated!", "sql": sql}

    if not is_valid_sql(sql):
        yield {"phase": "Retrying SQL with stricter prompt..."}
        sql = retry_with_stricter_prompt(user_query, schema_chunks)
        sql = sql.strip().removeprefix("sql").strip("`").strip().rstrip(";")
        
        # Handle bind variables again in retry
        sql = handle_bind_variables(sql, user_query)
        logger.info(f"[Retry SQL] {sql}")
        
        yield {"phase": "Retry SQL generated", "sql": sql}
        
        if not is_valid_sql(sql):
            yield {"error": "Retry also failed. Invalid SQL.", "sql": sql}
            return

    all_rows = []
    columns = []
    try:
        for chunk in run_sql_streaming(sql):
            if "columns" in chunk:
                columns = chunk["columns"]
                yield {"columns": columns}
            elif "rows" in chunk:
                all_rows.extend(chunk["rows"])
                yield {"rows": chunk["rows"]}
            elif "error" in chunk:
                yield {"error": chunk["error"]}
                return
    except Exception as e:
        logger.error(f"[Oracle Error] {e}")
        yield {"error": f"Oracle query failed: {str(e)}", "sql": sql}
        return

    yield {"phase": "Table parsed!"}

    # Determine display mode
    display_mode = determine_display_mode(user_query, all_rows)
    preview = format_preview_for_summary(all_rows, limit=10)
    
    # Send display mode BEFORE summary
    yield {"display_mode": display_mode}
    
    # Only generate summary if needed
    if display_mode in ["summary", "both"]:
        try:
            full_summary = []
            for event in stream_summary(user_query, preview):
                event_data = json.loads(event)
                
                # Collect summary chunks
                if "summary" in event_data:
                    full_summary.append(event_data["summary"])
                
                yield event_data
            
            # Validate summary matches query (skip for analytical queries)
            combined_summary = "\n".join(full_summary)
            if not validate_query_match(user_query, combined_summary):
                yield {"error": "Summary doesn't match query. Please try rephrasing."}
            
        except Exception as e:
            logger.error(f"Summary streaming error: {e}")
            yield {"error": f"Summary failed: {str(e)}"}
    
    # Send final completion signal
    yield {"phase": "Done"}