# backend/test_config.py
from app.config import (
    OPENROUTER_ENABLED, 
    OPENROUTER_API_KEY, 
    API_MODELS, 
    HYBRID_ENABLED,
    RESPONSE_SELECTION_WEIGHTS,
    API_REQUEST_TIMEOUT
)

print("🔧 Hybrid System Configuration Test")
print(f"✅ Hybrid Enabled: {HYBRID_ENABLED}")
print(f"✅ OpenRouter Enabled: {OPENROUTER_ENABLED}")
print(f"✅ API Key Present: {bool(OPENROUTER_API_KEY)}")
print(f"✅ API Key Length: {len(OPENROUTER_API_KEY)} chars")
print(f"✅ Production Model: {API_MODELS['production']['primary']}")
print(f"✅ HR Model: {API_MODELS['hr']['primary']}")
print(f"✅ TNA Model: {API_MODELS['tna']['primary']}")
print(f"✅ Request Timeout: {API_REQUEST_TIMEOUT}s")
print(f"✅ Selection Weights: {RESPONSE_SELECTION_WEIGHTS}")
print("🚀 Configuration loaded successfully!")