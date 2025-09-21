#!/usr/bin/env python3
"""
Verification script for trend analysis functionality
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.query_engine import determine_display_mode

def test_display_mode():
    """Test that trend analysis queries return 'both' display mode."""
    
    test_queries = [
        "Show the company-wise efficiency trend for last month",
        "Provide a trend analysis of production quantities over the past 6 months",
        "Analyze the efficiency trend for CAL company in 2025",
        "Show me the defect trend analysis by floor for this year",
        "What is the monthly production trend for Winner company?",
        "Show floor-wise production summary",  # This should be 'both' as per original code
        "List all employees",  # This should be 'table'
        "Give me a summary of production data"  # This should be 'summary'
    ]
    
    print("🔍 Verifying Display Mode Determination")
    print("=" * 50)
    
    for query in test_queries:
        # Test with empty rows list (similar to how it would be called)
        display_mode = determine_display_mode(query, [])
        print(f"Query: {query}")
        print(f"Display mode: {display_mode}")
        print("-" * 30)
    
    print("Verification complete!")

if __name__ == "__main__":
    test_display_mode()