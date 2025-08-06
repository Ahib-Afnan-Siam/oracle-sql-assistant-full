import os
import requests
from dotenv import load_dotenv  # Added to load .env variables

# Load environment variables
load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", 30))

def call_llm(prompt: str) -> str:
    """
    Call Ollama LLM (Mistral) with the given prompt and return the response text.
    If the call fails, return a default fallback JSON string.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        return '{"intent": "general", "confidence": 0.0}'
