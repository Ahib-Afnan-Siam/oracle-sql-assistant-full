import logging
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
- Use only the listed columns/tables.
- Prefer ANSI JOINs and use aliases when needed.
    """
    logger.info(f"[Prompt] Final Prompt Sent to DeepSeek:\n{prompt.strip()}")
    return prompt.strip()

def process_query(user_query: str) -> str:
    prompt = build_prompt(user_query)
    response = ask_sql_model(prompt)

    # Remove markdown block markers and backticks if present
    if response.strip().startswith("```"):
        response = response.strip().strip("`").replace("sql", "").strip()

    # Remove any lingering markdown
    response = response.strip().strip("`")

    logger.info(f"[LLM] Clean SQL:\n{response}")
    return response


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
