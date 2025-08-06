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

# ChromaDB Path
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "chroma_db"))