import json
import os
from dotenv import load_dotenv

load_dotenv()

# Load all source DBs
with open("config/sources.json") as f:
    sources_data = json.load(f)
    if isinstance(sources_data, dict):
        SOURCES = list(sources_data.values())
    else:
        SOURCES = sources_data

# Vector DB Configuration
VECTOR_DB = {
    "host": os.getenv("VECTOR_DB_HOST", "172.17.2.228"),
    "port": int(os.getenv("VECTOR_DB_PORT", 1521)),
    "service_name": os.getenv("VECTOR_DB_SERVICE", "AIPDB"),
    "pdb": os.getenv("VECTOR_DB_PDB", "AIPDB"),
    "user": os.getenv("VECTOR_DB_USER", "apps"),
    "password": os.getenv("VECTOR_DB_PASSWORD", "aPps#956")
}

# LLM for SQL generation (DeepSeek-Coder)
OLLAMA_SQL = {
    "url": os.getenv("OLLAMA_SQL_URL", "http://172.17.2.228/ollama/api/generate"),
    "model": os.getenv("OLLAMA_SQL_MODEL", "deepseek-coder-v2:16b"),
    "timeout": int(os.getenv("OLLAMA_SQL_TIMEOUT", 180))
}

# LLM for summaries (Mistral, legacy)
OLLAMA_SUMMARY = {
    "url": os.getenv("OLLAMA_SUMMARY_URL", "http://172.17.2.228/ollama/api/generate"),
    "model": os.getenv("OLLAMA_SUMMARY_MODEL", "mistral"),
    "timeout": int(os.getenv("OLLAMA_SUMMARY_TIMEOUT", 180))
}

# ✅ LLM for intelligent responses (DeepSeek-R1)
OLLAMA_R1 = {
    "url": os.getenv("OLLAMA_R1_URL", "http://172.17.2.228/ollama/api/generate"),
    "model": os.getenv("OLLAMA_R1_MODEL", "deepseek-r1:14b"),
    "timeout": int(os.getenv("OLLAMA_R1_TIMEOUT", 300))
}

# LLM for analytical summaries
OLLAMA_ANALYTICAL = {
    "url": os.getenv("OLLAMA_ANALYTICAL_URL", "http://172.17.2.228/ollama/api/generate"),
    "model": os.getenv("OLLAMA_ANALYTICAL_MODEL", "mistral"),
    "timeout": int(os.getenv("OLLAMA_ANALYTICAL_TIMEOUT", 240))
}

DYNAMIC_PROCESSING_CONFIG = {
    "entity_recognition": {
        "enabled": True,
        "confidence_threshold": 0.7,
        "max_entities_per_type": 5
    },
    "intent_classification": {
        "enabled": True,
        "fallback_intent": "general",
        "confidence_threshold": 0.5
    },
    "table_selection": {
        "smart_selection": True,
        "fallback_table": "T_PROD_DAILY",
        "preference_weights": {
            "date_context": 0.3,
            "entity_alignment": 0.4,
            "intent_match": 0.3
        }
    },
    "caching": {
        "enabled": True,
        "max_cache_size": 1000,
        "default_ttl": 300
    }
}

# Enhanced hybrid system thresholds
ENHANCED_THRESHOLDS = {
    "complexity_assessment": {
        "simple_threshold": 1,
        "medium_threshold": 3,
        "complex_threshold": 4
    },
    "confidence_calibration": {
        "base_local_confidence": 0.7,
        "base_skip_api": 0.85,
        "base_force_hybrid": 0.3,
        "adjustment_range": 0.2
    }
}

# Summarization Configuration
SUMMARIZATION_CONFIG = {
    "api_enabled": os.getenv("SUMMARIZATION_API_ENABLED", "true").lower() == "true",
    "api_threshold_rows": int(os.getenv("SUMMARIZATION_API_THRESHOLD_ROWS", "10")),
    "api_threshold_words": int(os.getenv("SUMMARIZATION_API_THRESHOLD_WORDS", "10")),
    "api_model_temperature": float(os.getenv("SUMMARIZATION_API_TEMPERATURE", "0.3")),
    "api_max_tokens": int(os.getenv("SUMMARIZATION_API_MAX_TOKENS", "500")),
    "fallback_to_local": os.getenv("SUMMARIZATION_FALLBACK_TO_LOCAL", "true").lower() == "true"
}

# Flattened variables for easier import
OLLAMA_SQL_URL = OLLAMA_SQL["url"]
OLLAMA_SQL_MODEL = OLLAMA_SQL["model"]
OLLAMA_SQL_TIMEOUT = OLLAMA_SQL["timeout"]

OLLAMA_SUMMARY_URL = OLLAMA_SUMMARY["url"]
OLLAMA_SUMMARY_MODEL = OLLAMA_SUMMARY["model"]
OLLAMA_SUMMARY_TIMEOUT = OLLAMA_SUMMARY["timeout"]

OLLAMA_R1_URL = OLLAMA_R1["url"]
OLLAMA_R1_MODEL = OLLAMA_R1["model"]
OLLAMA_R1_TIMEOUT = OLLAMA_R1["timeout"]

OLLAMA_ANALYTICAL_URL = OLLAMA_ANALYTICAL["url"]
OLLAMA_ANALYTICAL_MODEL = OLLAMA_ANALYTICAL["model"]
OLLAMA_ANALYTICAL_TIMEOUT = OLLAMA_ANALYTICAL["timeout"]

# ---- SQL model decoding options (all optional, with safe defaults)
OLLAMA_SQL_TEMP = float(os.getenv("OLLAMA_SQL_TEMP", "0.1"))
OLLAMA_SQL_TOP_P = float(os.getenv("OLLAMA_SQL_TOP_P", "0.9"))
OLLAMA_SQL_TOP_K = int(os.getenv("OLLAMA_SQL_TOP_K", "40"))
OLLAMA_SQL_REPEAT_PENALTY = float(os.getenv("OLLAMA_SQL_REPEAT_PENALTY", "1.1"))
OLLAMA_SQL_NUM_PREDICT = int(os.getenv("OLLAMA_SQL_NUM_PREDICT", "512"))
OLLAMA_SQL_NUM_CTX = int(os.getenv("OLLAMA_SQL_NUM_CTX", "4096"))
OLLAMA_SQL_SEED = int(os.getenv("OLLAMA_SQL_SEED", "7"))

# ...existing imports...
# app/config.py
SUMMARY_ENGINE = (os.getenv("SUMMARY_ENGINE") or "py").strip().lower()
SUMMARY_MAX_ROWS = int(os.getenv("SUMMARY_MAX_ROWS", 120))
SUMMARY_CHAR_BUDGET = int(os.getenv("SUMMARY_CHAR_BUDGET", 24000))

# ChromaDB Path
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "chroma_db"))

#Feedback system
FEEDBACK_DB_ID = os.getenv("FEEDBACK_DB_ID", "source_db_1")

#Feedback system
FEEDBACK_DB_ID = os.getenv("FEEDBACK_DB_ID", "source_db_1")

# ============================================================================
# HYBRID AI SYSTEM - OpenRouter API Configuration
# ============================================================================

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")

# Hybrid System Configuration
HYBRID_ENABLED = os.getenv("HYBRID_ENABLED", "true").lower() == "true"
HYBRID_MODE = os.getenv("HYBRID_MODE", "parallel")  # "parallel" or "fallback"

# API Models Configuration (Primary, Secondary, Fallback)
API_MODELS = {
    "production": {
        "primary": os.getenv("API_MODEL_PRODUCTION_PRIMARY", "deepseek/deepseek-chat"),
        "secondary": os.getenv("API_MODEL_PRODUCTION_SECONDARY", "meta-llama/llama-3.1-8b-instruct"),
        "fallback": os.getenv("API_MODEL_PRODUCTION_FALLBACK", "google/gemini-flash-1.5")
    },
    "hr": {
        "primary": os.getenv("API_MODEL_HR_PRIMARY", "meta-llama/llama-3.1-8b-instruct"),
        "secondary": os.getenv("API_MODEL_HR_SECONDARY", "deepseek/deepseek-chat"),
        "fallback": os.getenv("API_MODEL_HR_FALLBACK", "google/gemini-flash-1.5")
    },
    "tna": {
        "primary": os.getenv("API_MODEL_TNA_PRIMARY", "deepseek/deepseek-chat"),
        "secondary": os.getenv("API_MODEL_TNA_SECONDARY", "meta-llama/llama-3.1-8b-instruct"),
        "fallback": os.getenv("API_MODEL_TNA_FALLBACK", "google/gemini-flash-1.5")
    },
    "general": {
        "primary": os.getenv("API_MODEL_GENERAL_PRIMARY", "deepseek/deepseek-chat"),
        "secondary": os.getenv("API_MODEL_GENERAL_SECONDARY", "meta-llama/llama-3.1-8b-instruct"),
        "fallback": os.getenv("API_MODEL_GENERAL_FALLBACK", "google/gemini-flash-1.5")
    }
}

# API Request Configuration
API_REQUEST_TIMEOUT = int(os.getenv("API_REQUEST_TIMEOUT", "45"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))
API_RETRY_DELAY = float(os.getenv("API_RETRY_DELAY", "1.0"))

# Hybrid System Thresholds
LOCAL_CONFIDENCE_THRESHOLD = float(os.getenv("LOCAL_CONFIDENCE_THRESHOLD", "0.7"))
SKIP_API_THRESHOLD = float(os.getenv("SKIP_API_THRESHOLD", "0.85"))
FORCE_HYBRID_THRESHOLD = float(os.getenv("FORCE_HYBRID_THRESHOLD", "0.3"))

# Response Selection Weights
RESPONSE_SELECTION_WEIGHTS = {
    "technical_accuracy": float(os.getenv("WEIGHT_TECHNICAL_ACCURACY", "0.4")),
    "business_logic": float(os.getenv("WEIGHT_BUSINESS_LOGIC", "0.3")),
    "performance": float(os.getenv("WEIGHT_PERFORMANCE", "0.2")),
    "confidence": float(os.getenv("WEIGHT_CONFIDENCE", "0.1"))
}

# Training Data Collection
COLLECT_TRAINING_DATA = os.getenv("COLLECT_TRAINING_DATA", "true").lower() == "true"
TRAINING_DATA_DB_PATH = os.getenv("TRAINING_DATA_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "training_data.db"))

# Rate Limiting (Daily Limits)
DAILY_API_CALL_LIMIT = int(os.getenv("DAILY_API_CALL_LIMIT", "1000"))
EMERGENCY_LOCAL_ONLY = os.getenv("EMERGENCY_LOCAL_ONLY", "false").lower() == "true"

# Flattened API configuration for easier import
OPENROUTER_ENABLED = HYBRID_ENABLED and bool(OPENROUTER_API_KEY)
DEFAULT_API_MODEL = API_MODELS["general"]["primary"]