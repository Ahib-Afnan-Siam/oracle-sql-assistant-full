#!/usr/bin/env python3
"""
Test script to verify the fix for content moderation issues
"""
import sys
import os
import asyncio

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

async def test_content_moderation_fix():
    """Test the content moderation fix"""
    from app.ERP_R12_Test_DB.hybrid_processor import erp_hybrid_processor
    from app.ERP_R12_Test_DB.openrouter_client import get_erp_openrouter_client
    
    user_query = "give all details of organization id 123"
    
    print("=== TESTING CONTENT MODERATION FIX ===")
    print(f"User Query: {user_query}")
    
    # Test the hybrid processor
    print("\nTesting hybrid processor...")
    result = await erp_hybrid_processor.process_query(
        user_query=user_query,
        selected_db="source_db_2",
        mode="ERP"
    )
    
    print(f"Processing result: {result}")
    
    # Test the OpenRouter client directly
    print("\nTesting OpenRouter client...")
    client = get_erp_openrouter_client()
    
    # Get schema context
    schema_context_texts, _ = erp_hybrid_processor._get_erp_schema_context(user_query, "source_db_2")
    schema_info = ''
    erp_tables = erp_hybrid_processor._get_erp_schema_info()
    for table_name, table_info in erp_tables.items():
        schema_info += f"{table_name}: {table_info['description']} | Columns: {', '.join(table_info['columns'][:15])}\n"
    
    print(f"Schema info: {schema_info[:200]}...")
    
    # Test the fallback mechanism
    response = await client.get_model_with_fallback("hr", user_query, schema_info)
    print(f"API response: success={response.success}, content={response.content[:100]}..., error={response.error}")
    print(f"Response metadata: {response.metadata}")

if __name__ == "__main__":
    asyncio.run(test_content_moderation_fix())