#app/ollama_llm.py
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
    # SQL tunables
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

# ---------------------------
# Generic Ollama caller
# ---------------------------
def _ask_ollama_generic(
    url: str,
    model: str,
    timeout: int,
    prompt: str,
    options: Optional[Dict[str, Any]] = None,
    format_mode: Optional[str] = None,  # ← set to "json" for strict JSON responses
) -> str:
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt must be a non-empty string")

    truncated = prompt[:10000] if len(prompt) > 10000 else prompt

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": truncated,
        "stream": False,
    }
    if options:
        payload["options"] = options
    if format_mode:
        payload["format"] = format_mode  # Ollama supports strict JSON via this field

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if "response" not in data:
            raise ValueError("Invalid response format from Ollama API")

        out = (data["response"] or "").strip()

        # In case some models still wrap JSON in fences
        if out.startswith("```") and "```" in out[3:]:
            out = out.split("```", 1)[1].strip()

        if not out:
            raise ValueError("Empty response from Ollama")

        logger.debug("[LLM] Response from %s: %s", model, (out or "")[:300].replace("\n", " "))
        return out
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama API request failed: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in Ollama query: {e}", exc_info=True)
        raise

# ---------------------------
# Retry wrappers
# ---------------------------
@retry(**OLLAMA_RETRY_CONFIG)
def ask_sql_model(prompt: str) -> str:
    sql_options = {
        "temperature": OLLAMA_SQL_TEMP,
        "top_p": OLLAMA_SQL_TOP_P,
        "top_k": OLLAMA_SQL_TOP_K,
        "repeat_penalty": OLLAMA_SQL_REPEAT_PENALTY,
        "num_predict": OLLAMA_SQL_NUM_PREDICT,
        "num_ctx": OLLAMA_SQL_NUM_CTX,
        "seed": OLLAMA_SQL_SEED,
    }
    return _ask_ollama_generic(OLLAMA_SQL_URL, OLLAMA_SQL_MODEL, OLLAMA_SQL_TIMEOUT, prompt, sql_options)

# NEW: strict-JSON wrapper for the planner
@retry(**OLLAMA_RETRY_CONFIG)
def ask_sql_planner(prompt: str) -> str:
    sql_options = {
        "temperature": OLLAMA_SQL_TEMP,
        "top_p": OLLAMA_SQL_TOP_P,
        "top_k": OLLAMA_SQL_TOP_K,
        "repeat_penalty": OLLAMA_SQL_REPEAT_PENALTY,
        "num_predict": OLLAMA_SQL_NUM_PREDICT,
        "num_ctx": OLLAMA_SQL_NUM_CTX,
        "seed": OLLAMA_SQL_SEED,
    }
    resp_text = _ask_ollama_generic(
        OLLAMA_SQL_URL,
        OLLAMA_SQL_MODEL,
        OLLAMA_SQL_TIMEOUT,
        prompt,
        options=sql_options,
        format_mode="json",   # ← forces valid JSON tokens from Ollama
    )
    # Quiet, but still available when DEBUG is enabled
    logger.debug("[LLM] Planner raw: %s", (resp_text or "")[:300].replace("\n", " "))
    return resp_text

@retry(**OLLAMA_RETRY_CONFIG)
def ask_summary_model(prompt: str) -> str:
    return _ask_ollama_generic(OLLAMA_SUMMARY_URL, OLLAMA_SUMMARY_MODEL, OLLAMA_SUMMARY_TIMEOUT, prompt)

@retry(**OLLAMA_RETRY_CONFIG)
def ask_analytical_model(prompt: str) -> str:
    return _ask_ollama_generic(OLLAMA_ANALYTICAL_URL, OLLAMA_ANALYTICAL_MODEL, OLLAMA_ANALYTICAL_TIMEOUT, prompt)

def call_ollama(prompt: str, model: str) -> str:
    if model == OLLAMA_SQL_MODEL:
        return ask_sql_model(prompt)
    if model == OLLAMA_SUMMARY_MODEL:
        return _ask_ollama_generic(OLLAMA_SUMMARY_URL, model, OLLAMA_SUMMARY_TIMEOUT, prompt)
    if model == OLLAMA_ANALYTICAL_MODEL:
        return ask_analytical_model(prompt)
    if model == OLLAMA_R1_MODEL:
        return ask_deepseek_r1(prompt)
    raise ValueError(f"Unsupported model: {model}")

def ask_deepseek_r1(prompt: str) -> str:
    try:
        resp = requests.post(
            OLLAMA_R1_URL,
            json={"model": OLLAMA_R1_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_R1_TIMEOUT,
        )
        resp.raise_for_status()
        return (resp.json().get("response") or "").strip()
    except Exception as e:
        logger.error(f"[R1] DeepSeek-R1 failed: {e}")
        return "⚠️ Failed to generate response with DeepSeek-R1."
