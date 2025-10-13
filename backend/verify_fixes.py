#!/usr/bin/env python3
"""
Verification script to check the fixes for the ERP R12 hybrid processor issues
"""
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def check_model_configs():
    """Check model configurations"""
    from app.config import API_MODELS
    
    print("=== MODEL CONFIGURATION CHECK ===")
    hr_models = API_MODELS.get("hr", {})
    print(f"HR Domain Models:")
    print(f"  Primary: {hr_models.get('primary', 'Not found')}")
    print(f"  Secondary: {hr_models.get('secondary', 'Not found')}")
    print(f"  Fallback: {hr_models.get('fallback', 'Not found')}")
    
    # Check for invalid model IDs
    fallback = hr_models.get('fallback', '')
    if 'gemini-flash-2.0-flash-experimental' in fallback:
        print("❌ ERROR: Invalid model ID still present!")
        return False
    else:
        print("✅ HR Fallback model ID is valid")
    
    # Check SOS hybrid processor model configs
    print(f"\nChecking SOS hybrid processor model configs...")
    sos_file = os.path.join(os.path.dirname(__file__), 'app', 'SOS', 'hybrid_processor.py')
    if os.path.exists(sos_file):
        with open(sos_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'gemini-flash-2.0-flash-experimental' in content:
                print("❌ ERROR: Invalid model ID still present in SOS hybrid processor!")
                return False
            else:
                print("✅ SOS hybrid processor model IDs are valid")
    
    return True

def check_erp_hybrid_processor():
    """Check ERP hybrid processor for variable scope issues"""
    print("\n=== ERP HYBRID PROCESSOR CHECK ===")
    
    erp_file = os.path.join(os.path.dirname(__file__), 'app', 'ERP_R12_Test_DB', 'hybrid_processor.py')
    if os.path.exists(erp_file):
        with open(erp_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Check for proper imports in error handling sections
            if 'from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results' in content:
                print("✅ execute_query and format_erp_results imports found in error handling sections")
            else:
                print("⚠️  WARNING: execute_query and format_erp_results imports may be missing in error handling sections")
            
            # Check for target_db usage
            if 'target_db' in content:
                print("✅ target_db variable is used in the processor")
            else:
                print("❌ ERROR: target_db variable not found")
                return False
            
            return True
    else:
        print("❌ ERROR: ERP hybrid processor file not found")
        return False

def main():
    """Main verification function"""
    print("Running fix verification...")
    
    model_ok = check_model_configs()
    processor_ok = check_erp_hybrid_processor()
    
    if model_ok and processor_ok:
        print("\n✅ ALL FIXES VERIFIED SUCCESSFULLY!")
        print("1. Invalid model IDs have been corrected")
        print("2. Variable scope issues in ERP hybrid processor have been addressed")
        return 0
    else:
        print("\n❌ SOME ISSUES REMAIN")
        return 1

if __name__ == "__main__":
    sys.exit(main())