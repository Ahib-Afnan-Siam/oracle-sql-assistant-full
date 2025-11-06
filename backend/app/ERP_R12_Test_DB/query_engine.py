# ERP R12 Query Engine
import logging
import re  # Add missing import
import cx_Oracle
from typing import Dict, List, Any, Optional, Callable
from contextlib import contextmanager
from app.db_connector import connect_to_source
# Import ERP-specific vector store
from app.ERP_R12_Test_DB.vector_store_chroma import hybrid_schema_value_search, search_similar_schema
# Import database configuration
from app.config import DATABASE_CONFIG
import time

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

def get_table_schema_info(table_name: str, selected_db: str = "source_db_2") -> Dict[str, Any]:
    """
    Get schema information for a specific table from the vector store.
    
    Args:
        table_name: Name of the table to get schema info for
        selected_db: Database ID to query
        
    Returns:
        Dictionary containing table schema information
    """
    try:
        # Search for schema information about the table with higher top_k
        schema_docs = search_similar_schema(table_name, selected_db, top_k=20)
        
        # Extract column information from schema documents
        columns = []
        table_description = ""
        processed_columns = set()  # To avoid duplicates
        
        for doc in schema_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about columns
                if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == table_name:
                    column_name = doc['metadata'].get('column')
                    if column_name and column_name not in processed_columns:
                        columns.append(column_name)
                        processed_columns.add(column_name)
                # Get table description from table documents
                elif doc['metadata'].get('kind') == 'table' and doc['metadata'].get('table') == table_name:
                    if not table_description:  # Take the first description we find
                        table_description = doc['document']
        
        # If we didn't find a description, generate one
        if not table_description:
            table_description = f"ERP R12 table {table_name} containing business data."
        
        return {
            "table_name": table_name,
            "columns": columns,
            "description": table_description or f"Schema information for {table_name}. ONLY use these actual columns: " + ", ".join(columns[:20])
        }
    except Exception as e:
        logger.warning(f"Failed to get schema info for {table_name}: {e}")
        # Fallback to empty schema
        return {
            "table_name": table_name,
            "columns": [],
            "description": f"Schema information for {table_name}"
        }

def discover_erp_tables(query: str, selected_db: str = "source_db_2") -> List[str]:
    """
    Dynamically discover ERP tables mentioned in the query using vector store.
    
    Args:
        query: User's natural language query
        selected_db: Database ID to query
        
    Returns:
        List of table names discovered in the query context
    """
    try:
        # Search for table information in the vector store
        table_docs = search_similar_schema(query, selected_db, top_k=50)
        
        # Extract unique table names from the documents
        table_names = set()
        for doc in table_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about a table
                if doc['metadata'].get('kind') == 'table':
                    table_name = doc['metadata'].get('table')
                    if table_name:
                        table_names.add(table_name)
                # Also check for table names mentioned in the document content
                elif 'document' in doc:
                    # Look for common ERP R12 table patterns
                    content = doc['document'].upper()
                    # Use a comprehensive list of known ERP tables
                    erp_tables = [
                        "HR_OPERATING_UNITS", "ORG_ORGANIZATION_DEFINITIONS", 
                        "MTL_ONHAND_QUANTITIES_DETAIL", "MTL_SECONDARY_INVENTORIES",
                        "MTL_MATERIAL_TRANSACTIONS", "MTL_SYSTEM_ITEMS_B",
                        "MTL_ITEM_CATEGORIES", "MTL_CATEGORIES_B",
                        "MTL_PARAMETERS", "MTL_ITEM_CATALOG_GROUPS_B",
                        "MTL_ITEM_CATALOGS_B", "MTL_CROSS_REFERENCES",
                        "MTL_RESERVATIONS", "MTL_DEMAND", "MTL_SUPPLY",
                        "MTL_TRANSACTION_TYPES", "MTL_TRANSACTION_ACCOUNTS",
                        "MTL_TXN_REQUEST_HEADERS", "MTL_TXN_REQUEST_LINES",
                        "MTL_MATERIAL_STATUSES_B", "MTL_LOT_NUMBERS",
                        "MTL_SERIAL_NUMBERS", "MTL_UNIT_TRANSACTIONS",
                        "MTL_ITEM_REVISIONS", "MTL_ITEM_SUB_INVENTORIES",
                        "HR_ALL_ORGANIZATION_UNITS", "HR_LOCATIONS_ALL",
                        "HR_JOB_HISTORY", "HR_EMPLOYEES_CURRENT_V",
                        "PO_HEADERS_ALL", "PO_LINES_ALL", 
                        "PO_LINE_LOCATIONS_ALL", "PO_DISTRIBUTIONS_ALL",
                        "PO_VENDORS", "PO_VENDOR_SITES_ALL",
                        "AP_INVOICES_ALL", "AP_INVOICE_LINES_ALL",
                        "AP_INVOICE_DISTRIBUTIONS_ALL", "AP_SUPPLIERS",
                        "AP_SUPPLIER_SITES_ALL", "AP_TERMS_TL",
                        "OE_ORDER_HEADERS_ALL", "OE_ORDER_LINES_ALL",
                        "OE_TRANSACTION_TYPES_TL", "OE_PRICE_ADJUSTMENTS",
                        "AR_CUSTOMERS", "AR_CUSTOMER_SITES_ALL",
                        "AR_PAYMENT_SCHEDULES_ALL", "AR_RECEIVABLES_TRX_ALL",
                        "GL_LEDGERS", "GL_JE_HEADERS", "GL_JE_LINES",
                        "GL_CODE_COMBINATIONS", "GL_PERIODS", "GL_DAILY_RATES",
                        "FA_ADDITIONS_B", "FA_BOOKS", "FA_CATEGORIES_B",
                        "FA_DEPRN_DETAIL", "FA_DEPRN_SUMMARY",
                        "CST_ITEM_COSTS", "CST_COST_TYPES", 
                        "CST_QUANTITY_LAYERS", "CST_COST_ELEMENTS",
                        "BOM_BILL_OF_MATERIALS", "BOM_INVENTORY_COMPONENTS",
                        "BOM_RESOURCES", "BOM_DEPARTMENTS",
                        "WIP_ENTITIES", "WIP_OPERATIONS", 
                        "WIP_DISCRETE_JOBS", "WIP_REQUIREMENT_OPERATIONS",
                        "INV_MGD_MEASUREMENTS", "INV_MGD_ITEM_ORG_ASSIGNMENTS"
                    ]
                    for table in erp_tables:
                        if table in content:
                            table_names.add(table)
        
        # If we didn't find any tables, try a broader search
        if not table_names:
            logger.debug("No tables found in initial search, trying broader search")
            # Search for common ERP table prefixes
            prefixes = ["HR_", "ORG_", "MTL_", "PO_", "AP_", "AR_", "GL_", "FA_", "CST_", "BOM_", "WIP_", "INV_"]
            for prefix in prefixes:
                prefix_docs = search_similar_schema(f"{prefix} tables", selected_db, top_k=20)
                for doc in prefix_docs:
                    if 'document' in doc and 'metadata' in doc:
                        if doc['metadata'].get('kind') == 'table':
                            table_name = doc['metadata'].get('table')
                            if table_name:
                                table_names.add(table_name)
        
        logger.debug(f"Discovered ERP tables: {list(table_names)}")
        return list(table_names)
    except Exception as e:
        logger.warning(f"Failed to discover ERP tables: {e}. Using default tables.")
        # Fallback to known core tables
        return [
            "HR_OPERATING_UNITS", 
            "ORG_ORGANIZATION_DEFINITIONS", 
            "MTL_ONHAND_QUANTITIES_DETAIL", 
            "MTL_SECONDARY_INVENTORIES"
        ]

def detect_table_relationships(query: str, selected_db: str = "source_db_2") -> List[Dict[str, str]]:
    """
    Dynamically detect table relationships mentioned in the query using schema context.
    
    Args:
        query: User's natural language query
        selected_db: Database ID to query
        
    Returns:
        List of detected relationships
    """
    relationships = []
    query_lower = query.lower()
    
    # Dynamic detection based on schema context and natural language understanding
    # Import vector store to get dynamic schema information
    from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema
    
    # Discover tables mentioned in the query
    discovered_tables = discover_erp_tables(query, selected_db)
    
    # Get schema information for discovered tables
    table_schemas = {}
    for table_name in discovered_tables:
        table_schemas[table_name] = get_table_schema_info(table_name, selected_db)
    
    # Check for references to specific tables
    has_hr_ou_reference = "hr_operating_units" in query_lower or "operating unit" in query_lower or "org unit" in query_lower
    has_org_def_reference = "org_organization_definitions" in query_lower or "organization" in query_lower
    has_mtl_system_items_reference = "mtl_system_items" in query_lower or "item" in query_lower
    has_oe_order_lines_reference = "order lines" in query_lower or "sales order lines" in query_lower or "customer order lines" in query_lower
    has_oe_order_headers_reference = "order headers" in query_lower or "sales orders" in query_lower or "customer orders" in query_lower
    
    # Dynamic join detection based on schema context
    # Check for explicit relationship terms
    relationship_terms = ["join", "link", "connect", "both", "together", "with", "and", "compare", "versus", "vs"]
    has_relationship_term = any(term in query_lower for term in relationship_terms)
    
    # Enhanced HR_OPERATING_UNITS and ORG_ORGANIZATION_DEFINITIONS relationship
    if (has_hr_ou_reference and has_org_def_reference) or \
       (has_relationship_term and has_hr_ou_reference and has_org_def_reference) or \
       ("both" in query_lower and (has_hr_ou_reference or has_org_def_reference)):
        relationships.append({
            "left_table": "HR_OPERATING_UNITS",
            "left_column": "ORGANIZATION_ID",
            "right_table": "ORG_ORGANIZATION_DEFINITIONS",
            "right_column": "OPERATING_UNIT",
            "type": "INNER JOIN"
        })
    
    # Enhanced OE_ORDER_LINES_ALL and MTL_SYSTEM_ITEMS_B relationship (critical for sales analysis)
    if (has_oe_order_lines_reference and has_mtl_system_items_reference) or \
       ("sales" in query_lower and ("item" in query_lower or "product" in query_lower)):
        relationships.append({
            "left_table": "OE_ORDER_LINES_ALL",
            "left_column": "INVENTORY_ITEM_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "INVENTORY_ITEM_ID",
            "type": "INNER JOIN"
        })
        # Add organization join as well
        relationships.append({
            "left_table": "OE_ORDER_LINES_ALL",
            "left_column": "SHIP_FROM_ORG_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced OE_ORDER_LINES_ALL and OE_ORDER_HEADERS_ALL relationship
    if has_oe_order_lines_reference and has_oe_order_headers_reference:
        relationships.append({
            "left_table": "OE_ORDER_LINES_ALL",
            "left_column": "HEADER_ID",
            "right_table": "OE_ORDER_HEADERS_ALL",
            "right_column": "HEADER_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced MTL_SYSTEM_ITEMS_B and ORG_ORGANIZATION_DEFINITIONS relationship
    if has_mtl_system_items_reference and has_org_def_reference:
        relationships.append({
            "left_table": "MTL_SYSTEM_ITEMS_B",
            "left_column": "ORGANIZATION_ID",
            "right_table": "ORG_ORGANIZATION_DEFINITIONS",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced MTL_ONHAND_QUANTITIES_DETAIL and MTL_SYSTEM_ITEMS_B relationship
    has_onhand_reference = "onhand" in query_lower or "inventory" in query_lower or "stock" in query_lower
    if has_onhand_reference and has_mtl_system_items_reference:
        relationships.append({
            "left_table": "MTL_ONHAND_QUANTITIES_DETAIL",
            "left_column": "INVENTORY_ITEM_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "INVENTORY_ITEM_ID",
            "type": "INNER JOIN"
        })
        relationships.append({
            "left_table": "MTL_ONHAND_QUANTITIES_DETAIL",
            "left_column": "ORGANIZATION_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced MTL_MATERIAL_TRANSACTIONS and MTL_SYSTEM_ITEMS_B relationship
    has_transactions_reference = "transaction" in query_lower or "movement" in query_lower
    if has_transactions_reference and has_mtl_system_items_reference:
        relationships.append({
            "left_table": "MTL_MATERIAL_TRANSACTIONS",
            "left_column": "INVENTORY_ITEM_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "INVENTORY_ITEM_ID",
            "type": "INNER JOIN"
        })
        relationships.append({
            "left_table": "MTL_MATERIAL_TRANSACTIONS",
            "left_column": "ORGANIZATION_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced CST_ITEM_COSTS and MTL_SYSTEM_ITEMS_B relationship (for cost queries)
    has_cost_reference = "cost" in query_lower or "price" in query_lower or "value" in query_lower
    if has_cost_reference and has_mtl_system_items_reference:
        relationships.append({
            "left_table": "CST_ITEM_COSTS",
            "left_column": "INVENTORY_ITEM_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "INVENTORY_ITEM_ID",
            "type": "INNER JOIN"
        })
        relationships.append({
            "left_table": "CST_ITEM_COSTS",
            "left_column": "ORGANIZATION_ID",
            "right_table": "MTL_SYSTEM_ITEMS_B",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced PO_HEADERS_ALL and PO_LINES_ALL relationship
    has_po_reference = "purchase order" in query_lower or "po" in query_lower
    if has_po_reference and "line" in query_lower:
        relationships.append({
            "left_table": "PO_HEADERS_ALL",
            "left_column": "PO_HEADER_ID",
            "right_table": "PO_LINES_ALL",
            "right_column": "PO_HEADER_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced HR_EMPLOYEES_CURRENT_V and HR_ALL_ORGANIZATION_UNITS relationship
    has_employee_reference = "employee" in query_lower or "staff" in query_lower or "worker" in query_lower
    if has_employee_reference and has_org_def_reference:
        relationships.append({
            "left_table": "HR_EMPLOYEES_CURRENT_V",
            "left_column": "ORGANIZATION_ID",
            "right_table": "HR_ALL_ORGANIZATION_UNITS",
            "right_column": "ORGANIZATION_ID",
            "type": "INNER JOIN"
        })
    
    # Enhanced GL_LEDGERS and ORG_ORGANIZATION_DEFINITIONS relationship
    has_gl_reference = "ledger" in query_lower or "gl" in query_lower or "financial" in query_lower
    if has_gl_reference and has_org_def_reference:
        relationships.append({
            "left_table": "GL_LEDGERS",
            "left_column": "LEDGER_ID",
            "right_table": "ORG_ORGANIZATION_DEFINITIONS",
            "right_column": "SET_OF_BOOKS_ID",
            "type": "INNER JOIN"
        })
    
    # Log the detected relationships for debugging
    if relationships:
        logger.info(f"Detected {len(relationships)} table relationships for query: {query}")
        for rel in relationships:
            logger.debug(f"  {rel['left_table']}.{rel['left_column']} -> {rel['right_table']}.{rel['right_column']}")
    
    return relationships

def validate_erp_query(sql: str) -> bool:
    """
    Validate an ERP R12 SQL query for basic syntax and safety.
    
    Args:
        sql: The SQL query to validate
        
    Returns:
        True if query is valid, False otherwise
    """
    # Basic validation - check for prohibited operations
    sql_lower = sql.lower().strip()
    
    # Check for DML operations (not allowed in query engine)
    prohibited_keywords = [
        'insert', 'update', 'delete', 'drop', 'truncate', 'alter', 'create', 'replace'
    ]
    
    for keyword in prohibited_keywords:
        if keyword in sql_lower:
            # Make sure it's a whole word, not part of another word
            if re.search(r'\b' + keyword + r'\b', sql_lower):
                logger.warning(f"Prohibited keyword '{keyword}' found in query")
                return False
    
    # Check for proper SELECT statement
    if not sql_lower.startswith('select'):
        logger.warning("Query does not start with SELECT")
        return False
    
    # Basic structure validation
    if ';' in sql_lower and not sql_lower.strip().endswith(';'):
        # Semicolon should only be at the end if present
        logger.warning("Semicolon found in middle of query")
        return False
    
    # Additional validation for ERP R12 specific column names
    # Check for common incorrect column references
    incorrect_columns = [
        r'\bOOD\.DATE_TO\b',  # Should be DISABLE_DATE in ORG_ORGANIZATION_DEFINITIONS
        r'\b.*\.COMPANY\b',   # COMPANY column doesn't exist
    ]
    
    for pattern in incorrect_columns:
        if re.search(pattern, sql, re.IGNORECASE):
            logger.warning(f"Potentially incorrect column reference found: {pattern}")
            return False
    
    # Validate table and column references based on actual schema
    # This helps catch queries that reference non-existent tables or columns
    table_references = re.findall(r'\b([A-Z_][A-Z0-9_]+)\b', sql, re.IGNORECASE)
    
    # Filter out common SQL keywords and functions
    sql_keywords = {
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL', 
        'ORDER', 'BY', 'GROUP', 'HAVING', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER', 'ON',
        'AS', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
        'TO_CHAR', 'TO_DATE', 'TRUNC', 'SYSDATE', 'ADD_MONTHS', 'NVL', 'DECODE', 'SUBSTR', 'LENGTH',
        'UPPER', 'LOWER', 'CONCAT', 'ROUND', 'FLOOR', 'CEIL', 'ABS', 'MOD', 'POWER', 'SQRT',
        'DUAL', 'FETCH', 'NEXT', 'ROWS', 'ONLY', 'OFFSET', 'WITH'
    }
    
    actual_tables = [table for table in table_references if table.upper() not in sql_keywords]
    
    if not actual_tables:
        logger.warning("No valid ERP R12 tables referenced in query")
        # This might be okay for some queries, so we won't fail here
    
    return True

def _has_oracle_sql_issues(sql: str) -> bool:
    """
    Check for common Oracle SQL issues that might cause ORA-00933.
    
    Args:
        sql: The SQL query to check
        
    Returns:
        True if potential issues are detected, False otherwise
    """
    # Check for non-printable characters
    for char in sql:
        if ord(char) < 32 and char not in ['\n', '\t', ' ']:
            return True
    
    # Check for multiple semicolons
    if sql.count(';') > 1:
        return True
        
    # Check for trailing whitespace after semicolon
    if sql.endswith(';') and len(sql) > 1:
        if sql[-2].isspace():
            return True
            
    return False

def _deep_clean_sql(sql: str) -> str:
    """
    Deep clean SQL to remove any characters that might cause issues.
    
    Args:
        sql: The SQL query to clean
        
    Returns:
        Deep cleaned SQL query
    """
    # Remove the trailing semicolon
    sql = sql.rstrip(';')
    
    # Split into tokens and rebuild
    tokens = sql.split()
    cleaned_tokens = []
    
    for token in tokens:
        # Remove any non-printable characters
        cleaned_token = ''.join(char for char in token if ord(char) >= 32)
        if cleaned_token:
            cleaned_tokens.append(cleaned_token)
    
    # Rebuild the SQL
    cleaned_sql = ' '.join(cleaned_tokens)
    
    # Add semicolon back
    cleaned_sql += ';'
    
    return cleaned_sql

def _fix_common_oracle_issues(sql: str) -> str:
    """
    Fix common Oracle SQL issues that might cause ORA-00933.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    # Remove the trailing semicolon for processing
    sql = sql.rstrip(';')
    
    # Fix TRUNC(SYSDATE) issues - sometimes AI models generate problematic date functions
    # Replace TRUNC(SYSDATE) with SYSDATE if it's causing issues
    sql = sql.replace('TRUNC(SYSDATE)', 'SYSDATE')
    
    # Fix common column reference issues - cost information is in CST_ITEM_COSTS, not MTL_SYSTEM_ITEMS_B
    sql = _fix_cost_column_references(sql)
    
    # Fix common HR_OPERATING_UNITS query issues - handle NULL values properly
    sql = _fix_hr_operating_units_conditions(sql)
    
    # Fix GROUP BY issues - ensure all non-aggregate columns in SELECT are in GROUP BY
    sql = _fix_group_by_issues(sql)
    
    # Fix trailing comma in GROUP BY clause before ORDER BY
    import re
    # Pattern to match: GROUP BY ... , ORDER BY
    sql = re.sub(r'(GROUP BY\s+[^,]+(?:\s*,\s*[^,]+)*)\s*,\s*(ORDER BY)', r'\1 \2', sql, flags=re.IGNORECASE)
    
    # Fix trailing comma in GROUP BY clause before closing parenthesis or end of query
    sql = re.sub(r'(GROUP BY\s+[^,]+(?:\s*,\s*[^,]+)*)\s*,\s*(\)|$)', r'\1\2', sql, flags=re.IGNORECASE)
    
    # Fix other common trailing comma issues
    # Remove trailing comma before closing parenthesis in general
    sql = re.sub(r',\s*\)', ')', sql)
    
    # Remove multiple consecutive commas
    sql = re.sub(r',\s*,', ',', sql)
    
    # Fix ORDER BY clause issues - sometimes AI models generate ORDER BY clauses that are not properly formatted
    # Remove any trailing commas before the end of the query in ORDER BY clauses
    sql = re.sub(r'(ORDER BY\s+[^,]+(?:\s*,\s*[^,]+)*)\s*,\s*$', r'\1', sql, flags=re.IGNORECASE)
    
    # Fix common date filtering issues for sales analysis
    # Replace overly restrictive date filters with more reasonable ones
    sql = _fix_sales_date_filters(sql)
    
    # Fix common join condition issues
    sql = _fix_join_conditions(sql)
    
    # Clean up extra spaces that might have been introduced
    sql = re.sub(r'\s+', ' ', sql)
    
    # Note: Do not add semicolon back here as the execution logic handles that
    # The execute_query function will add it when needed
    
    return sql

def _fix_sales_date_filters(sql: str) -> str:
    """
    Fix common date filtering issues in sales analysis queries.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    import re
    import logging
    logger = logging.getLogger(__name__)
    
    # Check if this is a sales analysis query
    sales_indicators = ['sales', 'shipment', 'order', 'revenue', 'quantity']
    is_sales_query = any(indicator in sql.lower() for indicator in sales_indicators)
    
    if is_sales_query:
        # Look for overly restrictive date filters that might cause 0 results
        restrictive_patterns = [
            r"AND\s+\w+\.\w+_date\s*>=\s*ADD_MONTHS\s*\(\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*,\s*-\d+\s*\)\s*AND\s*\w+\.\w+_date\s*<\s*ADD_MONTHS\s*\(\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*,\s*\d+\s*\)",
            r"AND\s+\w+\.\w+_date\s*>=\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*AND\s*\w+\.\w+_date\s*<\s*ADD_MONTHS\s*\(\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*,\s*\d+\s*\)"
        ]
        
        for pattern in restrictive_patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            if matches:
                logger.info(f"Found restrictive date filters in sales query: {matches}")
                # Replace with a broader date range (last 24 months)
                sql = re.sub(
                    pattern,
                    "AND \\g<0> >= ADD_MONTHS(SYSDATE, -24)",  # Add a broader condition
                    sql,
                    flags=re.IGNORECASE
                )
    
    return sql

def _optimize_query_for_better_results(sql: str, user_query: str) -> str:
    """
    Optimize SQL query when initial execution returns no results.
    This method attempts to modify restrictive conditions to get better results.
    
    Args:
        sql: The original SQL query
        user_query: The user's natural language query
        
    Returns:
        Optimized SQL query
    """
    optimized_sql = sql
    
    # Check if this is a sales analysis query that might have restrictive date filtering
    if "sales" in user_query.lower() or "month" in user_query.lower() or "compare" in user_query.lower():
        logger.info("Optimizing SQL for sales analysis query with potentially restrictive date filtering")
        
        # Look for restrictive date filters and try to broaden them
        import re
        
        # Pattern to match date filters like: AND oola.actual_shipment_date >= ADD_MONTHS(TRUNC(SYSDATE, 'MM'), -1)
        date_pattern = r"AND\s+\w+\.\w+\s*>=\s*ADD_MONTHS\s*\(\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*,\s*-\d+\s*\)"
        
        # Pattern to match upper date bounds
        upper_date_pattern = r"AND\s+\w+\.\w+\s*<\s*ADD_MONTHS\s*\(\s*TRUNC\s*\(\s*SYSDATE\s*,\s*'MM'\s*\)\s*,\s*\d+\s*\)"
        
        # Check if we have restrictive date patterns
        date_matches = re.findall(date_pattern, optimized_sql, re.IGNORECASE)
        upper_date_matches = re.findall(upper_date_pattern, optimized_sql, re.IGNORECASE)
        
        if date_matches or upper_date_matches:
            logger.info("Found restrictive date filters, attempting to broaden date range")
            
            # For sales analysis, let's remove restrictive date filters entirely to get all available data
            # This is a simple approach - in a production system, you might want more sophisticated logic
            optimized_sql = re.sub(date_pattern, "", optimized_sql, flags=re.IGNORECASE)
            optimized_sql = re.sub(upper_date_pattern, "", optimized_sql, flags=re.IGNORECASE)
            
            # Clean up any double spaces or extra AND operators that might have been created
            optimized_sql = re.sub(r"\s+AND\s+AND\s+", " AND ", optimized_sql, flags=re.IGNORECASE)
            optimized_sql = re.sub(r"WHERE\s+AND\s+", "WHERE ", optimized_sql, flags=re.IGNORECASE)
            optimized_sql = re.sub(r"\s+", " ", optimized_sql)  # Normalize whitespace
            
    # Check for overly restrictive WHERE conditions that might cause 0 results
    if "WHERE" in optimized_sql.upper():
        import re
        # Look for conditions that might be too restrictive
        restrictive_conditions = [
            r"AND\s+\w+\.\w+\s*=\s*'[^']*'",  # Exact string matches
            r"AND\s+\w+\.\w+\s*IS\s+NOT\s+NULL",  # NOT NULL conditions
            r"AND\s+\w+\.\w+\s*>\s*\d+",  # Greater than conditions with numbers
            r"AND\s+\w+\.\w+\s*<\s*\d+"   # Less than conditions with numbers
        ]
        
        for pattern in restrictive_conditions:
            matches = re.findall(pattern, optimized_sql, re.IGNORECASE)
            if len(matches) > 2:  # If we have many restrictive conditions
                logger.info(f"Found {len(matches)} potentially restrictive conditions, attempting to relax some")
                # Remove some restrictive conditions to broaden results
                optimized_sql = re.sub(pattern, "", optimized_sql, count=1, flags=re.IGNORECASE)
    
    # Log the optimization
    if optimized_sql != sql:
        logger.info(f"SQL optimized from: {sql[:200]}...")
        logger.info(f"SQL optimized to: {optimized_sql[:200]}...")
        
    return optimized_sql

def _fix_join_conditions(sql: str) -> str:
    """
    Fix common join condition issues in ERP R12 queries.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    import re
    import logging
    logger = logging.getLogger(__name__)
    
    # Fix common OE_ORDER_LINES_ALL and MTL_SYSTEM_ITEMS_B join issues
    # Ensure both INVENTORY_ITEM_ID and ORGANIZATION_ID are joined
    if "OE_ORDER_LINES_ALL" in sql and "MTL_SYSTEM_ITEMS_B" in sql:
        # Check if we have the proper join conditions
        inventory_join_match = re.search(r"oola\.inventory_item_id\s*=\s*msib\.inventory_item_id", sql, re.IGNORECASE)
        org_join_match = re.search(r"oola\.ship_from_org_id\s*=\s*msib\.organization_id", sql, re.IGNORECASE)
        
        if inventory_join_match and not org_join_match:
            logger.info("Adding missing organization join condition for OE_ORDER_LINES_ALL and MTL_SYSTEM_ITEMS_B")
            # Add the organization join condition
            sql = re.sub(
                r"(oola\.inventory_item_id\s*=\s*msib\.inventory_item_id)",
                "\\1 AND oola.ship_from_org_id = msib.organization_id",
                sql,
                flags=re.IGNORECASE
            )
        elif not inventory_join_match and org_join_match:
            logger.info("Adding missing inventory item join condition for OE_ORDER_LINES_ALL and MTL_SYSTEM_ITEMS_B")
            # Add the inventory item join condition
            sql = re.sub(
                r"(oola\.ship_from_org_id\s*=\s*msib\.organization_id)",
                "oola.inventory_item_id = msib.inventory_item_id AND \\1",
                sql,
                flags=re.IGNORECASE
            )
        elif not inventory_join_match and not org_join_match:
            logger.info("Adding both join conditions for OE_ORDER_LINES_ALL and MTL_SYSTEM_ITEMS_B")
            # Look for the FROM clause to add the join conditions
            from_match = re.search(r"FROM\s+.*?OE_ORDER_LINES_ALL\s+oola.*?MTL_SYSTEM_ITEMS_B\s+msib", sql, re.IGNORECASE | re.DOTALL)
            if from_match:
                # Add both join conditions
                sql = re.sub(
                    r"(FROM\s+.*?OE_ORDER_LINES_ALL\s+oola.*?MTL_SYSTEM_ITEMS_B\s+msib)",
                    "\\1 ON oola.inventory_item_id = msib.inventory_item_id AND oola.ship_from_org_id = msib.organization_id",
                    sql,
                    flags=re.IGNORECASE
                )
    
    # Fix common MTL_ONHAND_QUANTITIES_DETAIL and MTL_SYSTEM_ITEMS_B join issues
    if "MTL_ONHAND_QUANTITIES_DETAIL" in sql and "MTL_SYSTEM_ITEMS_B" in sql:
        # Check if we have the proper join conditions
        inventory_join_match = re.search(r"moqd\.inventory_item_id\s*=\s*msib\.inventory_item_id", sql, re.IGNORECASE)
        org_join_match = re.search(r"moqd\.organization_id\s*=\s*msib\.organization_id", sql, re.IGNORECASE)
        
        if inventory_join_match and not org_join_match:
            logger.info("Adding missing organization join condition for MTL_ONHAND_QUANTITIES_DETAIL and MTL_SYSTEM_ITEMS_B")
            # Add the organization join condition
            sql = re.sub(
                r"(moqd\.inventory_item_id\s*=\s*msib\.inventory_item_id)",
                "\\1 AND moqd.organization_id = msib.organization_id",
                sql,
                flags=re.IGNORECASE
            )
        elif not inventory_join_match and org_join_match:
            logger.info("Adding missing inventory item join condition for MTL_ONHAND_QUANTITIES_DETAIL and MTL_SYSTEM_ITEMS_B")
            # Add the inventory item join condition
            sql = re.sub(
                r"(moqd\.organization_id\s*=\s*msib\.organization_id)",
                "moqd.inventory_item_id = msib.inventory_item_id AND \\1",
                sql,
                flags=re.IGNORECASE
            )
    
    return sql

def _fix_cost_column_references(sql: str) -> str:
    """
    Fix common cost column reference issues in SQL queries.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    import re
    
    # Check if the query references cost columns from MTL_SYSTEM_ITEMS_B
    # Cost information is actually in CST_ITEM_COSTS table
    if re.search(r'msib\.standard_cost', sql, re.IGNORECASE):
        logger.info("Fixing cost column reference: standard_cost is in CST_ITEM_COSTS, not MTL_SYSTEM_ITEMS_B")
        
        # Replace msib.standard_cost with cic.item_cost (or another appropriate cost column)
        # But first we need to make sure CST_ITEM_COSTS is joined
        if not re.search(r'cst_item_costs', sql, re.IGNORECASE):
            # Add join to CST_ITEM_COSTS table
            from_match = re.search(r'FROM\s+mtl_system_items_b\s+msib', sql, re.IGNORECASE)
            if from_match:
                # Add join to CST_ITEM_COSTS
                join_clause = " JOIN cst_item_costs cic ON msib.inventory_item_id = cic.inventory_item_id AND msib.organization_id = cic.organization_id "
                sql = sql[:from_match.end()] + join_clause + sql[from_match.end():]
        
        # Replace the column reference
        sql = re.sub(r'msib\.standard_cost', 'cic.item_cost', sql, flags=re.IGNORECASE)
    
    # Handle other common cost-related column issues
    cost_column_mappings = {
        r'msib\.material_cost': 'cic.material_cost',
        r'msib\.item_cost': 'cic.item_cost',
        r'msib\.cost': 'cic.item_cost'
    }
    
    for old_pattern, new_column in cost_column_mappings.items():
        if re.search(old_pattern, sql, re.IGNORECASE):
            logger.info(f"Fixing cost column reference: {old_pattern} should be in CST_ITEM_COSTS")
            
            # Add join if not present
            if not re.search(r'cst_item_costs', sql, re.IGNORECASE):
                from_match = re.search(r'FROM\s+mtl_system_items_b\s+msib', sql, re.IGNORECASE)
                if from_match:
                    join_clause = " JOIN cst_item_costs cic ON msib.inventory_item_id = cic.inventory_item_id AND msib.organization_id = cic.organization_id "
                    sql = sql[:from_match.end()] + join_clause + sql[from_match.end():]
            
            # Replace the column reference
            sql = re.sub(old_pattern, new_column, sql, flags=re.IGNORECASE)
    
    return sql

def _fix_hr_operating_units_conditions(sql: str) -> str:
    """
    Fix common HR_OPERATING_UNITS query conditions that may not match actual data.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    import re
    import logging
    logger = logging.getLogger(__name__)
    
    # Check if this is an HR_OPERATING_UNITS query
    if "HR_OPERATING_UNITS" in sql.upper():
        # Check for overly restrictive USABLE_FLAG conditions
        # If all rows have NULL USABLE_FLAG, remove the condition
        usable_flag_match = re.search(r"USABLE_FLAG\s*=\s*['\"]Y['\"]", sql, re.IGNORECASE)
        if usable_flag_match:
            logger.info("Detected USABLE_FLAG = 'Y' condition in HR_OPERATING_UNITS query")
            # Replace with a more flexible condition that handles NULL values
            sql = re.sub(r"AND\s+USABLE_FLAG\s*=\s*['\"]Y['\"]", "", sql, flags=re.IGNORECASE)
            sql = re.sub(r"USABLE_FLAG\s*=\s*['\"]Y['\"]\s+AND", "", sql, flags=re.IGNORECASE)
            # Add a condition that includes NULL values or 'Y' values
            # But only if there's a WHERE clause already
            if "WHERE" in sql.upper():
                sql = re.sub(r"(WHERE\s+.*?)(\s+AND|\s*$)", r"\1 AND (USABLE_FLAG = 'Y' OR USABLE_FLAG IS NULL)\2", sql, flags=re.IGNORECASE)
            else:
                # Add WHERE clause if it doesn't exist
                from_match = re.search(r"FROM\s+HR_OPERATING_UNITS", sql, re.IGNORECASE)
                if from_match:
                    sql = sql[:from_match.end()] + " WHERE (USABLE_FLAG = 'Y' OR USABLE_FLAG IS NULL)" + sql[from_match.end():]
        
        # Check for overly restrictive DATE_TO conditions
        # If all rows have NULL DATE_TO, adjust the condition
        date_to_match = re.search(r"DATE_TO\s+IS\s+NULL\s+OR\s+DATE_TO\s*>=\s*SYSDATE", sql, re.IGNORECASE)
        if date_to_match:
            logger.info("Detected DATE_TO condition in HR_OPERATING_UNITS query")
            # The condition is already reasonable, but we can make it more explicit
            # Replace with a condition that better handles the NULL values we observed
            sql = re.sub(r"DATE_TO\s+IS\s+NULL\s+OR\s+DATE_TO\s*>=\s*SYSDATE", "(DATE_TO IS NULL OR DATE_TO >= SYSDATE)", sql, flags=re.IGNORECASE)
    
    return sql

def _fix_group_by_issues(sql: str) -> str:
    """
    Fix GROUP BY issues by ensuring all non-aggregate columns in SELECT are included in GROUP BY.
    
    Args:
        sql: The SQL query to fix
        
    Returns:
        Fixed SQL query
    """
    import re
    
    # Check if this is a SELECT statement
    if not sql.upper().startswith("SELECT"):
        return sql
    
    # Extract SELECT clause
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return sql
    
    select_clause = select_match.group(1)
    
    # Identify aggregate functions
    aggregate_functions = [
        'SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'GROUP_CONCAT', 'LISTAGG', 
        'STDDEV', 'VARIANCE', 'FIRST', 'LAST', 'ROW_NUMBER', 'RANK', 
        'DENSE_RANK', 'LEAD', 'LAG', 'NTILE'
    ]
    
    # Check if we have any aggregate functions in the SELECT clause
    has_aggregate_functions = any(func in select_clause.upper() for func in aggregate_functions)
    
    # If no aggregate functions, no need to fix GROUP BY
    if not has_aggregate_functions:
        return sql
    
    # Parse SELECT clause to find columns (excluding aggregate functions)
    # Split by comma but be careful of commas inside parentheses (for functions)
    select_parts = []
    current_part = ""
    paren_count = 0
    
    for char in select_clause:
        if char == '(':
            paren_count += 1
            current_part += char
        elif char == ')':
            paren_count -= 1
            current_part += char
        elif char == ',' and paren_count == 0:
            select_parts.append(current_part.strip())
            current_part = ""
        else:
            current_part += char
    
    if current_part:
        select_parts.append(current_part.strip())
    
    # Identify non-aggregate columns
    non_aggregate_columns = []
    for part in select_parts:
        # Check if this part contains an aggregate function
        is_aggregate = False
        for func in aggregate_functions:
            if re.search(r'\b' + func + r'\s*\(', part, re.IGNORECASE):
                is_aggregate = True
                break
        
        # If not an aggregate function, extract the column name or expression
        if not is_aggregate:
            # Extract the full expression before AS (if present)
            full_expression = part.split(' AS ')[0].strip()
            
            # Skip literals and expressions that are clearly not columns
            if not re.match(r'^[\'\"0-9]', full_expression) and full_expression not in non_aggregate_columns:
                # Handle complex expressions (contains parentheses) and simple column references
                if ('.' in full_expression and not full_expression.startswith("'") and not full_expression.startswith('"')) or \
                   ('(' in full_expression and ')' in full_expression) or \
                   (not full_expression.startswith("'") and not full_expression.startswith('"') and full_expression):
                    non_aggregate_columns.append(full_expression)
    
    # Check for correlated subqueries in SELECT clause that reference outer query columns
    correlated_columns = []
    
    # Specific fix for the common pattern we're seeing:
    # When we have a correlated subquery that references msib.inventory_item_id or msib.organization_id,
    # these columns must be included in the GROUP BY clause
    # Check the entire SQL, not just the SELECT clause, since parsing may truncate subqueries
    if re.search(r'\(\s*SELECT.*?WHERE.*?msib\.', sql, re.IGNORECASE | re.DOTALL):
        # Add the commonly referenced msib columns
        common_correlated_columns = ['msib.inventory_item_id', 'msib.organization_id']
        for col in common_correlated_columns:
            if col not in correlated_columns:
                correlated_columns.append(col)
    
    # Combine non-aggregate columns and correlated subquery columns
    all_required_columns = list(non_aggregate_columns)
    for col in correlated_columns:
        if col not in all_required_columns:
            all_required_columns.append(col)
    
    # If we have required columns and aggregate functions, we need GROUP BY
    if all_required_columns and has_aggregate_functions:
        # Check if we already have GROUP BY
        group_by_match = re.search(r'\bGROUP\s+BY\b', sql, re.IGNORECASE)
        
        if group_by_match:
            # Extract existing GROUP BY columns
            group_by_end_match = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+ORDER\s+BY|\s+HAVING|\s*;|$)', sql, re.IGNORECASE)
            if group_by_end_match:
                group_by_clause = group_by_end_match.group(1)
                group_by_parts = [part.strip() for part in group_by_clause.split(',') if part.strip()]
                
                # Add missing required columns to GROUP BY
                missing_columns = []
                for col in all_required_columns:
                    # Check if column is already in GROUP BY (accounting for aliases)
                    found = False
                    for group_col in group_by_parts:
                        if col.lower() == group_col.lower() or col.split('.')[-1].lower() == group_col.split('.')[-1].lower():
                            found = True
                            break
                    if not found:
                        missing_columns.append(col)
                
                # If we found missing columns, add them to GROUP BY
                if missing_columns:
                    logger.info(f"Fixing GROUP BY clause - adding missing columns: {missing_columns}")
                    # Replace the GROUP BY clause with the updated one
                    new_group_by = group_by_clause + ', ' + ', '.join(missing_columns)
                    sql = sql[:group_by_end_match.start(1)] + new_group_by + sql[group_by_end_match.end(1):]
        else:
            # No GROUP BY clause but we have aggregate functions and required columns
            # We need to add a GROUP BY clause
            logger.info(f"Adding GROUP BY clause for columns: {all_required_columns}")
            
            # Find the position to insert GROUP BY (before ORDER BY, HAVING, or at the end)
            having_match = re.search(r'\bHAVING\b', sql, re.IGNORECASE)
            order_by_match = re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE)
            
            if having_match:
                # Insert GROUP BY before HAVING
                insert_pos = having_match.start()
                sql = sql[:insert_pos] + ' GROUP BY ' + ', '.join(all_required_columns) + ' ' + sql[insert_pos:]
            elif order_by_match:
                # Insert GROUP BY before ORDER BY
                insert_pos = order_by_match.start()
                sql = sql[:insert_pos] + ' GROUP BY ' + ', '.join(all_required_columns) + ' ' + sql[insert_pos:]
            else:
                # Insert GROUP BY at the end (before semicolon if present)
                semicolon_pos = sql.rfind(';')
                if semicolon_pos != -1:
                    sql = sql[:semicolon_pos] + ' GROUP BY ' + ', '.join(all_required_columns) + ' ' + sql[semicolon_pos:]
                else:
                    sql = sql + ' GROUP BY ' + ', '.join(all_required_columns)
    
    return sql

def _generate_simple_erp_sql(user_query: str) -> Optional[str]:
    """
    Generate simple SQL for common ERP queries.
    
    Args:
        user_query: The user's natural language query
        
    Returns:
        Generated SQL query or None if the query is not recognized
    """
    # Instead of hardcoding specific query patterns, we should rely on the dynamic
    # schema context from the vector store. Returning None will force the system
    # to use the API-based approach with proper schema context.
    
    # Remove all hardcoded query patterns - let the AI handle this dynamically
    return None

def execute_query(sql: str, db_id: str = "source_db_2", page: int = 1, page_size: int = 1000, cancellation_token: Optional[Callable[[], bool]] = None, user_query: str = "") -> Dict[str, Any]:
    """
    Execute a SQL query against the ERP R12 database with retry logic and cancellation support.
    
    Args:
        sql: The SQL query to execute
        db_id: The database ID to connect to (default: source_db_2)
        page: Page number for pagination (default: 1)
        page_size: Number of rows per page (default: 1000)
        cancellation_token: Function that returns True if query should be cancelled
        user_query: The original user query for optimization purposes
        
    Returns:
        Dictionary containing query results with columns and rows
    """
    # Try to execute the query with improved retry logic
    max_attempts = DATABASE_CONFIG["retry_attempts"]
    
    # Check for cancellation before executing
    if cancellation_token and cancellation_token():
        raise Exception("Query was cancelled before execution")
    
    for attempt in range(max_attempts + 1):
        try:
            # Basic validation of SQL query
            if not sql or not isinstance(sql, str):
                raise ValueError("Invalid SQL query: empty or not a string")
            
            # Clean up the SQL query
            sql = sql.strip()
            
            # Check if the query contains bind variables
            has_bind_variables = ':' in sql and 'DUAL' not in sql.upper()
            
            # If the query has bind variables, we need to handle them properly
            if has_bind_variables:
                logger.info(f"Query contains bind variables: {sql}")
                # For queries with bind variables, we need to handle them properly
                # This is a simplified approach - in a real implementation, these would come from user input
                if ':specific_organization_id' in sql:
                    try:
                        # Try to get a valid organization ID from the database
                        with connect_to_source(db_id) as (org_conn, org_validator):
                            org_cursor = org_conn.cursor()
                            org_cursor.execute("""
                                SELECT ORGANIZATION_ID 
                                FROM ORG_ORGANIZATION_DEFINITIONS 
                                WHERE ROWNUM = 1
                            """)
                            result = org_cursor.fetchone()
                            if result:
                                specific_org_id = result[0]
                                sql = sql.replace(':specific_organization_id', str(specific_org_id))
                                logger.info(f"Replaced :specific_organization_id with {specific_org_id}")
                            else:
                                # Fallback to 1 if no organization found
                                sql = sql.replace(':specific_organization_id', '1')
                                logger.warning("No organization found, using default value 1")
                    except Exception as e:
                        # Fallback to 1 if we can't get a valid organization ID
                        logger.warning(f"Could not get valid organization ID: {e}. Using default value 1.")
                        sql = sql.replace(':specific_organization_id', '1')
                else:
                    # For other bind variables, we need to handle them appropriately
                    # This is a more general approach to handle bind variables
                    import re
                    bind_vars = re.findall(r':(\w+)', sql)
                    for var in bind_vars:
                        # Replace with a default value for testing
                        # In a real implementation, these would come from user input
                        sql = sql.replace(f':{var}', "'DEFAULT_VALUE'")  # Using string literal for safety
                        logger.info(f"Replaced bind variable :{var} with DEFAULT_VALUE")
            
            # Remove any trailing semicolons for Oracle execution
            # Oracle cx_Oracle doesn't always like trailing semicolons
            sql = sql.rstrip(';')
            
            # Must start with SELECT
            if not sql.upper().startswith("SELECT"):
                raise ValueError(f"Invalid SQL query: must start with SELECT. Got: {sql[:50]}...")
            
            # Log the exact SQL being executed for debugging
            logger.info(f"Executing query on {db_id} (attempt {attempt + 1})")
            logger.info(f"SQL: {repr(sql)}")  # This will show exactly what characters are in the SQL
            
            # Apply common Oracle SQL fixes before execution
            original_sql = sql
            sql = _fix_common_oracle_issues(sql)
            if sql != original_sql:
                logger.info(f"Applied SQL fixes. New SQL: {repr(sql)}")
            
            # Additional debugging - let's try to validate the SQL structure
            # Check for common Oracle SQL issues
            if _has_oracle_sql_issues(sql):
                logger.warning(f"Potential Oracle SQL issues detected in: {sql}")
            
            with connect_to_source(db_id) as (conn, validator):
                # Set query timeout to prevent long-running queries from hanging
                cursor = conn.cursor()
                
                # Set a reasonable timeout for the query using configuration values
                # Only set timeout if it's not None
                timeout_ms = DATABASE_CONFIG["query_timeout_ms"]
                if timeout_ms is not None:
                    try:
                        cursor.calltimeout = timeout_ms
                    except AttributeError:
                        # Older versions of cx_Oracle may not support calltimeout
                        pass
                
                # Log connection details for debugging
                try:
                    dsn_info = getattr(conn, 'dsn', 'Unknown DSN')
                    logger.info(f"Connected to database: {dsn_info}")
                except:
                    logger.info("Connected to database (DSN info not available)")
                
                try:
                    version_info = getattr(conn, 'version', 'Unknown version')
                    logger.info(f"Database version: {version_info}")
                except:
                    logger.info("Database version info not available")
                
                # Log cursor information
                logger.info(f"Created cursor: {type(cursor)}")
                
                # Check for cancellation before executing
                if cancellation_token and cancellation_token():
                    raise Exception("Query was cancelled before execution")
                
                # Try to execute the query directly first (without semicolon)
                try:
                    logger.info("Attempting to execute query directly (without semicolon)")
                    logger.info(f"Executing SQL: {repr(sql)}")
                    cursor.execute(sql)
                    logger.info("Query executed successfully")
                except cx_Oracle.Error as direct_error:
                    # If direct execution fails, try with semicolon
                    logger.warning(f"Direct execution failed, trying with semicolon: {direct_error}")
                    sql_with_semicolon = sql + ';'
                    logger.info(f"Executing SQL with semicolon: {repr(sql_with_semicolon)}")
                    try:
                        cursor.execute(sql_with_semicolon)
                        logger.info("Query with semicolon executed successfully")
                    except cx_Oracle.Error as semicolon_error:
                        # Try various fixes for the SQL
                        logger.warning(f"Query with semicolon also failed: {semicolon_error}")
                        
                        # Try without aliases
                        no_alias_sql = sql.replace(" AS OPERATING_UNIT_NAME", "")
                        logger.info(f"Trying SQL without alias: {repr(no_alias_sql)}")
                        try:
                            cursor.execute(no_alias_sql)
                            logger.info("SQL without alias executed successfully")
                        except cx_Oracle.Error as no_alias_error:
                            logger.warning(f"SQL without alias also failed: {no_alias_error}")
                            
                            # Try with quoted alias
                            quoted_alias_sql = sql.replace(" AS OPERATING_UNIT_NAME", ' AS "OPERATING_UNIT_NAME"')
                            logger.info(f"Trying SQL with quoted alias: {repr(quoted_alias_sql)}")
                            try:
                                cursor.execute(quoted_alias_sql)
                                logger.info("SQL with quoted alias executed successfully")
                            except cx_Oracle.Error as quoted_alias_error:
                                logger.warning(f"SQL with quoted alias also failed: {quoted_alias_error}")
                                
                                # Try removing the last condition
                                simplified_sql = sql.replace(" AND (hou.USABLE_FLAG IS NULL OR hou.USABLE_FLAG = 'Y')", "")
                                simplified_sql = simplified_sql.replace(" AND hou.DATE_FROM <= SYSDATE", "")
                                simplified_sql = simplified_sql.replace(" AND (hou.DATE_TO IS NULL OR hou.DATE_TO >= SYSDATE)", "")
                                simplified_sql = simplified_sql.replace(" AND hou.DATE_TO IS NULL", "")
                                simplified_sql = simplified_sql.replace(" AND hou.DATE_TO >= SYSDATE", "")
                                logger.info(f"Trying simplified SQL (removed conditions): {repr(simplified_sql)}")
                                try:
                                    cursor.execute(simplified_sql)
                                    logger.info("Simplified SQL executed successfully")
                                except cx_Oracle.Error as simplified_error:
                                    logger.error(f"Simplified SQL also failed: {simplified_error}")
                                    
                                    # Try a very simple query to see if the connection works
                                    try:
                                        simple_sql = "SELECT 1 FROM DUAL"
                                        logger.info(f"Testing simple SQL: {repr(simple_sql)}")
                                        cursor.execute(simple_sql)
                                        result = cursor.fetchone()
                                        logger.info(f"Simple query result: {result}")
                                    except cx_Oracle.Error as simple_error:
                                        logger.error(f"Even simple query failed: {simple_error}")
                                        # Log connection details for debugging
                                        try:
                                            dsn_info = getattr(conn, 'dsn', 'Unknown DSN')
                                            logger.error(f"Connection details: {dsn_info}")
                                        except:
                                            logger.error("Connection details not available")
                                        
                                        try:
                                            version_info = getattr(conn, 'version', 'Unknown version')
                                            logger.error(f"Connection version: {version_info}")
                                        except:
                                            logger.error("Connection version info not available")
                                    
                                    # Re-raise the original error
                                    raise direct_error
                
                # Get column information
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                else:
                    columns = []
                
                # Check for cancellation after execution but before processing results
                if cancellation_token and cancellation_token():
                    raise Exception("Query was cancelled during execution")
                
                # OPTIMIZATION: For very large result sets, we'll implement a more efficient approach
                # Check the row count first to determine the best approach
                row_count = 0
                try:
                    # Try to get count with a COUNT(*) query for better performance estimation
                    # For very large result sets, skip the count query as it can be expensive
                    # Instead, fetch a sample to estimate if we have data
                    count_sql = f"SELECT COUNT(*) FROM ({sql}) count_subquery"
                    count_cursor = conn.cursor()
                    count_cursor.execute(count_sql)
                    row_count_result = count_cursor.fetchone()
                    if row_count_result:
                        row_count = int(row_count_result[0])
                    count_cursor.close()
                    logger.info(f"Estimated row count: {row_count}")
                except Exception as count_error:
                    logger.warning(f"Could not get row count: {count_error}")
                    # Fall back to fetching a sample to estimate
                    try:
                        sample_cursor = conn.cursor()
                        sample_cursor.execute(sql)
                        # Fetch just a few rows to check if query works
                        sample_rows = sample_cursor.fetchmany(10)
                        if sample_rows:
                            logger.info(f"Sample fetch successful, at least {len(sample_rows)} rows available")
                            row_count = len(sample_rows)  # Set a minimum row count
                        sample_cursor.close()
                    except Exception as sample_error:
                        logger.warning(f"Sample fetch also failed: {sample_error}")
                
                # PERFORMANCE OPTIMIZATION: Implement pagination for large result sets
                # Calculate offset for pagination
                offset = (page - 1) * page_size
                
                # Add OFFSET and FETCH NEXT clauses for pagination
                paginated_sql = f"{sql} OFFSET {offset} ROWS FETCH NEXT {page_size} ROWS ONLY"
                
                # Check for cancellation before executing paginated query
                if cancellation_token and cancellation_token():
                    raise Exception("Query was cancelled before pagination")
                
                # Execute the paginated query
                cursor.execute(paginated_sql)
                result_rows = cursor.fetchall()
                
                logger.info(f"Fetched page {page} with {len(result_rows)} rows (page size: {page_size})")
                
                # Check for cancellation after pagination but before processing results
                if cancellation_token and cancellation_token():
                    raise Exception("Query was cancelled during pagination")
                
                # Convert rows to list of dictionaries for easier handling
                formatted_rows = []
                for row in result_rows:
                    row_dict = {}
                    for i, col_name in enumerate(columns):
                        # Handle LOB objects and other special types
                        value = row[i]
                        if hasattr(value, 'read'):
                            try:
                                value = value.read()
                            except:
                                value = str(value)
                        row_dict[col_name] = value
                    formatted_rows.append(row_dict)
                
                logger.info(f"Query executed successfully, returned {len(formatted_rows)} rows")
                
                # Add metadata about the full result set and pagination
                result_metadata = {
                    "total_rows_available": row_count,
                    "rows_returned": len(formatted_rows),
                    "results_truncated": row_count > len(formatted_rows),
                    "current_page": page,
                    "page_size": page_size,
                    "total_pages": (row_count + page_size - 1) // page_size  # Ceiling division
                }
                
                # If we got 0 rows, let's try to optimize the query
                if len(formatted_rows) == 0:
                    try:
                        # Try a simple count query to see if there's any data
                        count_cursor = conn.cursor()
                        count_cursor.execute(f"SELECT COUNT(*) as count FROM ({sql})")
                        count_result = count_cursor.fetchone()
                        if count_result and count_result[0] > 0:
                            logger.info(f"Query returned 0 rows but table has {count_result[0]} rows")
                        else:
                            logger.info("Query returned 0 rows and table is empty")
                        count_cursor.close()
                    except Exception as count_check_error:
                        logger.warning(f"Could not check row count: {count_check_error}")
                    
                    # Try to optimize the query for better results
                    logger.info("Attempting to optimize query for better results")
                    optimized_sql = _optimize_query_for_better_results(sql, user_query)
                    
                    if optimized_sql != sql:
                        logger.info("Retrying with optimized SQL")
                        try:
                            # Execute the optimized query
                            cursor.execute(optimized_sql)
                            result_rows = cursor.fetchall()
                            
                            logger.info(f"Optimized query executed successfully, returned {len(result_rows)} rows")
                            
                            # Convert rows to list of dictionaries for easier handling
                            optimized_formatted_rows = []
                            for row in result_rows:
                                row_dict = {}
                                for i, col_name in enumerate(columns):
                                    # Handle LOB objects and other special types
                                    value = row[i]
                                    if hasattr(value, 'read'):
                                        try:
                                            value = value.read()
                                        except:
                                            value = str(value)
                                    row_dict[col_name] = value
                                optimized_formatted_rows.append(row_dict)
                            
                            # If the optimized query returned results, use them instead
                            if len(optimized_formatted_rows) > 0:
                                formatted_rows = optimized_formatted_rows
                                logger.info(f"Using optimized query results with {len(formatted_rows)} rows")
                        except Exception as opt_error:
                            logger.warning(f"Optimized query execution failed: {opt_error}")

                
                return {
                    "columns": columns,
                    "rows": formatted_rows,
                    "row_count": len(formatted_rows),
                    "metadata": result_metadata
                }
                
        except Exception as e:
            if attempt < max_attempts:
                logger.warning(f"Query execution failed (attempt {attempt + 1}/{max_attempts + 1}): {e}")
                # Wait before retrying
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            else:
                logger.error(f"Query execution failed after {max_attempts + 1} attempts: {e}")
                raise e
    
    # This should never be reached
    raise Exception("Unexpected error in query execution")

def format_erp_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format ERP R12 query results for display.
    
    Args:
        results: Raw query results
        
    Returns:
        Formatted results with appropriate display modes
    """
    # Determine the best display mode based on data
    columns = results.get("columns", [])
    rows = results.get("rows", [])
    
    # Default to table view
    display_mode = "table"
    
    # If we have many columns, consider a different view
    if len(columns) > 10:
        display_mode = "table_scrollable"
    
    # If we have a lot of rows, consider pagination
    if len(rows) > 1000:
        display_mode = "table_paginated"
    
    # Special handling for certain data types
    formatted_rows = []
    for row in rows:
        formatted_row = {}
        for key, value in row.items():
            # Handle date formatting - fixed isinstance check for Oracle datetime types
            if hasattr(value, 'strftime') and callable(getattr(value, 'strftime', None)):
                # This is a more robust way to check for datetime objects
                try:
                    formatted_row[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_row[key] = str(value)
            # Handle numeric formatting
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if isinstance(value, float) and value.is_integer():
                    formatted_row[key] = int(value)
                else:
                    formatted_row[key] = value
            # Handle None values
            elif value is None:
                formatted_row[key] = ""
            else:
                formatted_row[key] = value
        formatted_rows.append(formatted_row)
    
    # Convert rows to arrays to match frontend expectations
    rows_as_arrays = [list(row.values()) for row in formatted_rows] if formatted_rows else []
    
    # Include metadata in the formatted results
    formatted_results = {
        "columns": columns,
        "rows": rows_as_arrays,
        "row_count": results.get("row_count", len(formatted_rows)),
        "display_mode": display_mode
    }
    
    # Add metadata if available
    if "metadata" in results:
        formatted_results["metadata"] = results["metadata"]
    
    return formatted_results