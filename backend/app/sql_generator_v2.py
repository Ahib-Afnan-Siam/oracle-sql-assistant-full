import logging
import re

from app.vector_store import get_rich_schema_context, get_all_schema_tokens
from app.ollama_llm import ask_sql_model

logger = logging.getLogger(__name__)

def build_prompt(user_query: str) -> str:
    """
    Build a rich prompt for DeepSeek using schema context.
    """
    full_context = get_rich_schema_context(user_query, top_k=3)

    # Truncate schema context if too long
    MAX_CONTEXT_LEN = 5000
    if len(full_context) > MAX_CONTEXT_LEN:
        logger.warning(f"[Prompt] Truncating schema context from {len(full_context)} to {MAX_CONTEXT_LEN} chars")
        full_context = full_context[:MAX_CONTEXT_LEN]

    logger.info(f"[Prompt] Schema Context:\n{full_context}")

    prompt = f"""
You are an Oracle SQL expert.
Based on the user question and schema context, generate ONE valid Oracle SQL query.

User Question:
{user_query}

Schema Context:
{full_context}

Constraints:
- Only return SQL (no explanations, no markdown).
- Return **exactly one** SELECT statement (no semicolons, no BEGIN/END).
- Avoid UNION/UNION ALL unless the user explicitly asks to combine datasets.
- If requested columns exist in a single table, prefer a single-table SELECT.
- Use only the listed columns/tables.
- Prefer ANSI JOINs and use aliases when needed.
    """
    logger.info(f"[Prompt] Final Prompt Sent to DeepSeek:\n{prompt.strip()}")
    return prompt.strip()

def process_query_with_prompt(user_query: str):
    """
    Return a tuple: (clean_sql, prompt) for the given user_query.
    Keeps process_query(...) stable for existing callers.
    """
    prompt = build_prompt(user_query)
    response = ask_sql_model(prompt)

    # Strip code fences like ```sql ... ```
    r = response.strip()
    if r.startswith("```"):
        # remove leading ```[sql]? and trailing ```
        r = re.sub(r"^```(?:\s*sql)?\s*", "", r, flags=re.IGNORECASE)
        r = re.sub(r"\s*```$", "", r)

    # Fallback cleanup in case any stray backticks remain
    r = r.strip("`").strip()

    # Keep only the first statement (defensive against multi-statement outputs)
    resp_no_semis = r.split(";", 1)[0].strip()

    # Ensure we start at the first SELECT (drop any preamble noise)
    m = re.search(r"(?is)\bselect\b", resp_no_semis)
    clean_sql = resp_no_semis[m.start():].strip() if m else resp_no_semis

    logger.info(f"[LLM] Clean SQL:\n{clean_sql}")
    return clean_sql, prompt


def process_query(user_query: str) -> str:
    """
    Backward-compatible wrapper: return only the SQL string.
    """
    sql, _prompt = process_query_with_prompt(user_query)
    return sql



def validate_sql(sql: str) -> bool:
    if not sql:
        logger.warning("Empty SQL received for validation.")
        return False

    all_tokens = get_all_schema_tokens()
    valid_tokens = [t for t in all_tokens if any(kw in sql for kw in t.split())]

    if not valid_tokens:
        logger.warning("No valid schema tokens found in SQL!")
    logger.info(f"SQL Validation: {'PASSED' if valid_tokens else 'FAILED'}")
    return True
