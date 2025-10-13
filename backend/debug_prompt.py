#!/usr/bin/env python3
"""
Debug script to check the prompt being sent to the AI model
"""
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

def debug_prompt():
    """Debug the prompt generation"""
    from app.ERP_R12_Test_DB.hybrid_processor import erp_hybrid_processor
    
    user_query = "List the organization names and their short codes from HR_OPERATING_UNITS"
    
    print("=== DEBUGGING PROMPT GENERATION ===")
    print(f"User Query: {user_query}")
    
    # Get ERP schema info
    erp_tables = erp_hybrid_processor._get_erp_schema_info()
    
    print("\nERP Schema Info:")
    for table_name, table_info in erp_tables.items():
        print(f"  {table_name}:")
        print(f"    Description: {table_info['description']}")
        print(f"    Columns: {', '.join(table_info['columns'][:10])}{'...' if len(table_info['columns']) > 10 else ''}")
    
    # Create the prompt
    prompt = f"""Oracle ERP R12 SQL Generation Request:

User Query: {user_query}

Schema Information (ONLY use these tables and columns - DO NOT assume any other columns exist):
"""
    for table_name, table_info in erp_tables.items():
        prompt += f"\n{table_name}: {table_info['description']}\nActual Columns: {', '.join(table_info['columns'][:20])}"  # Show more columns for accuracy
    
    prompt += """

Key Relationship:
HR_OPERATING_UNITS.ORGANIZATION_ID = ORG_ORGANIZATION_DEFINITIONS.OPERATING_UNIT

CRITICAL COLUMN NOTES:
- HR_OPERATING_UNITS has DATE_FROM and DATE_TO columns for validity periods
- ORG_ORGANIZATION_DEFINITIONS has DISABLE_DATE column for deactivation date (NOT DATE_TO)
- NEVER reference DATE_TO in ORG_ORGANIZATION_DEFINITIONS queries
- ONLY use the columns listed above - DO NOT assume any other columns exist
- For flag-based queries (like USABLE_FLAG), EXAMINE THE ACTUAL VALUES IN THE COLUMN rather than assuming specific values like 'Y' or 'N'. Use appropriate conditions based on actual data values.
- When checking for "usable" or "active" status, look for columns that indicate status and use appropriate conditions based on actual data values rather than assuming specific flag values
- For date-based queries, consider NULL values as indicating "currently active" or "no end date"
- In HR_OPERATING_UNITS, if USABLE_FLAG is NULL or not populated, use DATE_FROM and DATE_TO columns to determine if an operating unit is currently active:
  * DATE_FROM <= SYSDATE (the operating unit has started)
  * DATE_TO IS NULL OR DATE_TO >= SYSDATE (the operating unit has not ended)

Instructions:
1. Generate valid Oracle SQL only
2. Use proper table aliases (hou for HR_OPERATING_UNITS, ood for ORG_ORGANIZATION_DEFINITIONS)
3. ONLY include JOINs when specifically requested or when data from both tables is needed
4. For simple queries about a single table, use only that table without JOINs
5. Return only SQL syntax, no markdown or explanations
6. DO NOT assume any column names not explicitly listed above
7. DO NOT hallucinate column names
8. Ensure the query is complete with proper SELECT, FROM, and any necessary WHERE clauses
9. End the query with a semicolon
10. For queries about "list of operating units" or similar, use only HR_OPERATING_UNITS table
11. Only JOIN with ORG_ORGANIZATION_DEFINITIONS when organization names or related data is specifically requested
12. For flag-based queries, use appropriate conditions based on actual data values rather than assuming specific flag values
13. For date-based queries, consider NULL values appropriately
14. For "currently usable" or "active" operating units, if USABLE_FLAG is NULL or not populated, use DATE_FROM and DATE_TO columns instead

SQL Query:"""
    
    print("\n=== GENERATED PROMPT ===")
    print(prompt)

if __name__ == "__main__":
    debug_prompt()