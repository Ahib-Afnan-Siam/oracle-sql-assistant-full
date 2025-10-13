#!/usr/bin/env python3
"""
Debug script to check the actual configuration values
"""
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def debug_config():
    """Debug the configuration"""
    from app.config import API_MODELS
    
    print("=== DEBUGGING CONFIGURATION ===")
    print("API_MODELS content:")
    for domain, models in API_MODELS.items():
        print(f"  {domain}:")
        for priority, model in models.items():
            print(f"    {priority}: {model}")
    
    print("\n=== HR DOMAIN SPECIFICALLY ===")
    hr_models = API_MODELS.get("hr", {})
    print(f"HR Models: {hr_models}")
    
    # Check where the values come from
    import os
    hr_fallback_env = os.getenv("API_MODEL_HR_FALLBACK")
    print(f"API_MODEL_HR_FALLBACK environment variable: {hr_fallback_env}")
    
    # Check the default value
    default_fallback = "google/gemini-flash-1.5:free"
    print(f"Default fallback value: {default_fallback}")

if __name__ == "__main__":
    debug_config()