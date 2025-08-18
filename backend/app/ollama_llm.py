import requests
import logging
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import (
    OLLAMA_SQL_URL,
    OLLAMA_SQL_MODEL,
    OLLAMA_SQL_TIMEOUT,
    OLLAMA_SUMMARY_URL,
    OLLAMA_SUMMARY_MODEL,
    OLLAMA_SUMMARY_TIMEOUT,
    OLLAMA_R1_URL,
    OLLAMA_R1_MODEL,
    OLLAMA_R1_TIMEOUT,
    OLLAMA_ANALYTICAL_URL,
    OLLAMA_ANALYTICAL_MODEL,
    OLLAMA_ANALYTICAL_TIMEOUT,
    # ↓ add these imports
    OLLAMA_SQL_TEMP,
    OLLAMA_SQL_TOP_P,
    OLLAMA_SQL_TOP_K,
    OLLAMA_SQL_REPEAT_PENALTY,
    OLLAMA_SQL_NUM_PREDICT,
    OLLAMA_SQL_NUM_CTX,
    OLLAMA_SQL_SEED,
)

logger = logging.getLogger(__name__)

OLLAMA_RETRY_CONFIG = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=2, max=10),
    "reraise": True
}

# ✅ Generic Ollama caller
def _ask_ollama_generic(
    url: str,
    model: str,
    timeout: int,
    prompt: str,
    options: Optional[Dict[str, Any]] = None,  # ← NEW
) -> str:
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt must be a non-empty string")

    try:
        truncated_prompt = prompt[:10000] if len(prompt) > 10000 else prompt

        payload = {
            "model": model,
            "prompt": truncated_prompt,
            "stream": False,
        }
        # Only include options if provided (keeps other callers unchanged)
        if options:
            payload["options"] = options

        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        response_json = response.json()

        if "response" not in response_json:
            raise ValueError("Invalid response format from Ollama API")

        result = response_json["response"].strip()

        # Clean up code blocks
        if result.startswith("```") and "```" in result[3:]:
            result = result.split("```", 1)[1].strip()

        if not result:
            raise ValueError("Empty response from Ollama")

        logger.info(f"[LLM] Response from {model}: {result[:200]}...")
        return result

    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama API request failed: {str(e)}", exc_info=True)
        raise
    except ValueError as e:
        logger.error(f"Ollama response validation failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Ollama query: {str(e)}", exc_info=True)
        raise

# ✅ Retry wrappers
@retry(**OLLAMA_RETRY_CONFIG)
def ask_sql_model(prompt: str) -> str:
    # Lower creativity + determinism for SQL only
    sql_options = {
        "temperature": OLLAMA_SQL_TEMP,
        "top_p": OLLAMA_SQL_TOP_P,
        "top_k": OLLAMA_SQL_TOP_K,
        "repeat_penalty": OLLAMA_SQL_REPEAT_PENALTY,
        "num_predict": OLLAMA_SQL_NUM_PREDICT,
        "num_ctx": OLLAMA_SQL_NUM_CTX,
        "seed": OLLAMA_SQL_SEED,
        # (Optional) Stops to reduce multi-statement outputs; keep commented unless needed:
        # "stop": ["```"]
    }
    return _ask_ollama_generic(OLLAMA_SQL_URL, OLLAMA_SQL_MODEL, OLLAMA_SQL_TIMEOUT, prompt, sql_options)

@retry(**OLLAMA_RETRY_CONFIG)
def ask_summary_model(prompt: str) -> str:
    return _ask_ollama_generic(OLLAMA_SUMMARY_URL, OLLAMA_SUMMARY_MODEL, OLLAMA_SUMMARY_TIMEOUT, prompt)

@retry(**OLLAMA_RETRY_CONFIG)
def ask_analytical_model(prompt: str) -> str:
    return _ask_ollama_generic(
        OLLAMA_ANALYTICAL_URL,
        OLLAMA_ANALYTICAL_MODEL,
        OLLAMA_ANALYTICAL_TIMEOUT,
        prompt
    )

def call_ollama(prompt: str, model: str) -> str:
    if model == OLLAMA_SQL_MODEL:
        return ask_sql_model(prompt)
    elif model == OLLAMA_SUMMARY_MODEL:
        return _ask_ollama_generic(OLLAMA_SUMMARY_URL, model, OLLAMA_SUMMARY_TIMEOUT, prompt)
    elif model == OLLAMA_ANALYTICAL_MODEL:
        return ask_analytical_model(prompt)
    elif model == OLLAMA_R1_MODEL:
        return ask_deepseek_r1(prompt)
    else:
        raise ValueError(f"Unsupported model: {model}")

def ask_deepseek_r1(prompt: str) -> str:
    try:
        response = requests.post(
            OLLAMA_R1_URL,
            json={"model": OLLAMA_R1_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_R1_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except Exception as e:
        logger.error(f"[R1] DeepSeek-R1 failed: {e}")
        return "⚠️ Failed to generate response with DeepSeek-R1."
