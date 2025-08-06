import requests
import logging
from typing import Optional
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
    OLLAMA_ANALYTICAL_TIMEOUT
)

logger = logging.getLogger(__name__)

OLLAMA_RETRY_CONFIG = {
    "stop": stop_after_attempt(3),
    "wait": wait_exponential(multiplier=1, min=2, max=10),
    "reraise": True
}

# ✅ Generic Ollama caller
def _ask_ollama_generic(url: str, model: str, timeout: int, prompt: str) -> str:
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt must be a non-empty string")

    try:
        truncated_prompt = prompt[:10000] if len(prompt) > 10000 else prompt

        response = requests.post(
            url,
            json={
                "model": model,
                "prompt": truncated_prompt,
                "stream": False
            },
            timeout=timeout
        )

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

        logger.info(f"[LLM] Response from {model}: {result[:200]}...")  # Truncate long responses
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
    return _ask_ollama_generic(OLLAMA_SQL_URL, OLLAMA_SQL_MODEL, OLLAMA_SQL_TIMEOUT, prompt)

@retry(**OLLAMA_RETRY_CONFIG)
def ask_summary_model(prompt: str) -> str:
    return _ask_ollama_generic(OLLAMA_SUMMARY_URL, OLLAMA_SUMMARY_MODEL, OLLAMA_SUMMARY_TIMEOUT, prompt)

# ✅ Analytical model wrapper
@retry(**OLLAMA_RETRY_CONFIG)
def ask_analytical_model(prompt: str) -> str:
    return _ask_ollama_generic(
        OLLAMA_ANALYTICAL_URL, 
        OLLAMA_ANALYTICAL_MODEL, 
        OLLAMA_ANALYTICAL_TIMEOUT, 
        prompt
    )

# ✅ Unified fallback caller for general use
def call_ollama(prompt: str, model: str) -> str:
    if model == OLLAMA_SQL_MODEL:
        return _ask_ollama_generic(OLLAMA_SQL_URL, model, OLLAMA_SQL_TIMEOUT, prompt)
    elif model == OLLAMA_SUMMARY_MODEL:
        return _ask_ollama_generic(OLLAMA_SUMMARY_URL, model, OLLAMA_SUMMARY_TIMEOUT, prompt)
    elif model == OLLAMA_ANALYTICAL_MODEL:
        return ask_analytical_model(prompt)
    elif model == OLLAMA_R1_MODEL:
        return ask_deepseek_r1(prompt)
    else:
        raise ValueError(f"Unsupported model: {model}")

# ✅ DeepSeek-R1 (optional usage only)
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