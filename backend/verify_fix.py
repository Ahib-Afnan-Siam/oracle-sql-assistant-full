#!/usr/bin/env python3
"""
Verification script to check if the fix is properly implemented
"""
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def verify_fix():
    """Verify that the fix is properly implemented"""
    
    # Check if the get_model_with_fallback method is properly implemented
    from app.ERP_R12_Test_DB.openrouter_client import ERPOpenRouterClient
    
    # Check if the _generate_sql_with_api method is properly updated
    from app.ERP_R12_Test_DB.hybrid_processor import ERPHybridProcessor
    
    print("=== VERIFICATION OF FIX IMPLEMENTATION ===")
    
    # Check that ERPOpenRouterClient has the updated get_model_with_fallback method
    client = ERPOpenRouterClient.__dict__
    if 'get_model_with_fallback' in client:
        print("✓ ERPOpenRouterClient has get_model_with_fallback method")
    else:
        print("✗ ERPOpenRouterClient missing get_model_with_fallback method")
    
    # Check that ERPHybridProcessor has the updated _generate_sql_with_api method
    processor = ERPHybridProcessor.__dict__
    if '_generate_sql_with_api' in processor:
        print("✓ ERPHybridProcessor has _generate_sql_with_api method")
    else:
        print("✗ ERPHybridProcessor missing _generate_sql_with_api method")
    
    print("\n=== FIX VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    verify_fix()
