#!/usr/bin/env python3
"""
Test script to verify trend analysis functionality
"""

import sys
import os
import asyncio

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from app.rag_engine import answer
from app.query_engine import determine_display_mode

async def test_trend_analysis_queries():
    """Test trend analysis queries to ensure they return both summary and table views."""
    
    test_queries = [
        "Show the company-wise efficiency trend for last month",
        "Provide a trend analysis of production quantities over the past 6 months",
        "Analyze the efficiency trend for CAL company in 2025",
        "Show me the defect trend analysis by floor for this year",
        "What is the monthly production trend for Winner company?",
    ]
    
    print("🔍 Testing Trend Analysis Queries")
    print("=" * 50)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\nTest {i}: {query}")
        print("-" * 40)
        
        # Test display mode determination
        display_mode = determine_display_mode(query, [])
        print(f"Display mode: {display_mode}")
        
        # Test RAG engine response
        try:
            result = await answer(query, "source_db_1", "SOS")
            if result.get("status") == "success":
                print(f"✅ Status: Success")
                print(f"Display mode: {result.get('display_mode', 'N/A')}")
                has_summary = bool(result.get("summary"))
                has_table = bool(result.get("results", {}).get("columns"))
                print(f"Has summary: {has_summary}")
                print(f"Has table data: {has_table}")
                
                if display_mode == "both" or "trend" in query.lower():
                    if has_summary and has_table:
                        print("✅ Correctly returns both summary and table for trend analysis")
                    else:
                        print("❌ Should return both summary and table for trend analysis")
                else:
                    print("ℹ️  Display mode as expected")
            else:
                print(f"❌ Status: {result.get('status', 'Unknown')}")
                print(f"Message: {result.get('message', 'N/A')}")
        except Exception as e:
            print(f"❌ Error: {str(e)}")
    
    print("\n" + "=" * 50)
    print("Testing complete!")

if __name__ == "__main__":
    asyncio.run(test_trend_analysis_queries())