# ERP R12 RAG Engine
import logging
import re
from typing import Dict, List, Optional, Tuple, Any, Callable

# Import ERP-specific modules
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema
from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

def _discover_erp_tables() -> List[str]:
    """
    Dynamically discover all ERP tables from the vector store.
    
    Returns:
        List of table names discovered in the vector store
    """
    try:
        # Search for table information in the vector store
        table_docs = search_similar_schema("ERP R12 tables", "source_db_2", top_k=100)
        
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
                    # Use a more comprehensive list of known ERP tables
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
                prefix_docs = search_similar_schema(f"{prefix} tables", "source_db_2", top_k=20)
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

def _get_erp_schema_info() -> Dict[str, Any]:
    """
    Dynamically retrieve ERP schema information from the vector store.
    
    Returns:
        Dictionary containing table and column information
    """
    try:
        # Dynamically discover ERP tables instead of hardcoding them
        table_names = _discover_erp_tables()
        
        erp_tables = {}
        
        # Process each discovered table
        for table_name in table_names:
            # Search for schema information about this table
            table_docs = search_similar_schema(table_name, "source_db_2", top_k=50)
            
            # Extract column information from schema documents
            columns = []
            table_description = ""
            processed_columns = set()  # To avoid duplicates
            
            for doc in table_docs:
                if 'document' in doc and 'metadata' in doc:
                    # Check if this document is about columns
                    if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == table_name:
                        column_name = doc['metadata'].get('column')
                        if column_name and column_name not in processed_columns:
                            columns.append(column_name)
                            processed_columns.add(column_name)
                    # Get table description
                    elif doc['metadata'].get('kind') == 'table' and doc['metadata'].get('table') == table_name:
                        if 'document' in doc and not table_description:
                            table_description = doc['document']
            
            # If we didn't find a description in the documents, generate one
            if not table_description:
                table_description = f"ERP R12 table {table_name} containing business data."
            
            # Limit columns to top 50 most relevant ones to avoid overwhelming the API
            if len(columns) > 50:
                columns = columns[:50]
                logger.debug(f"Truncated columns for {table_name} to top 50")
            
            erp_tables[table_name] = {
                "columns": columns,
                "description": table_description
            }
        
        logger.debug(f"Retrieved dynamic schema info for {len(erp_tables)} tables")
        return erp_tables
    except Exception as e:
        logger.warning(f"Failed to retrieve dynamic schema info: {e}. Using empty schema.")
        # Fallback to empty schema
        return {}

def _is_erp_query_dynamic(user_query: str) -> bool:
    """
    Dynamically determine if a query should be routed to ERP R12 based on schema information.
    
    Args:
        user_query: The user's natural language query
        
    Returns:
        True if the query should be routed to ERP R12, False otherwise
    """
    query_lower = user_query.lower()
    
    # Get dynamic schema information
    erp_tables = _get_erp_schema_info()
    
    # Check for table names
    for table_name in erp_tables.keys():
        if table_name.lower() in query_lower:
            return True
    
    # Check for column names
    all_columns = []
    for table_info in erp_tables.values():
        all_columns.extend(table_info.get("columns", []))
    
    # Check for common column patterns
    for column in all_columns:
        if column.lower() in query_lower:
            return True
    
    # Use intelligent pattern matching for ERP-specific business terms
    # Look for common ERP business concepts
    erp_business_terms = [
        "operating unit", "organization", "inventory", "subinventory",
        "onhand", "quantity", "item", "product", "material", "stock",
        "purchase order", "po number", "supplier", "vendor", "invoice",
        "customer", "sales order", "order number", "shipment", "delivery",
        "employee", "job", "department", "location", "asset", "cost",
        "ledger", "account", "transaction", "balance", "payment",
        "budget", "forecast", "demand", "supply", "planning",
        "manufacturing", "bom", "bill of material", "work order",
        "project", "task", "resource", "capacity", "schedule",
        "quality", "inspection", "lot", "serial", "batch",
        "requisition", "rfq", "quote", "contract", "agreement"
    ]
    
    # Check if this looks like an ERP business query
    erp_matches = sum(1 for term in erp_business_terms if term in query_lower)
    if erp_matches >= 2:  # If at least 2 ERP business terms are found
        return True
        
    # Look for common database query patterns
    common_patterns = [
        "list", "show", "find", "get", "select", "retrieve", 
        "count", "total", "sum", "average", "avg", "min", "max",
        "where", "filter", "search", "lookup", "query"
    ]
    
    # Check if this looks like a database query
    pattern_matches = sum(1 for pattern in common_patterns if pattern in query_lower)
    if pattern_matches >= 2:  # If at least 2 common query patterns are found
        # Check if it mentions database-related concepts
        db_terms = ["table", "column", "record", "data", "information", "entry"]
        db_matches = sum(1 for term in db_terms if term in query_lower)
        if db_matches >= 1:
            return True
        
    return False

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

async def answer(user_query: str, selected_db: str = "source_db_2", mode: str = "ERP", session_id: Optional[str] = None, client_ip: Optional[str] = None, user_agent: Optional[str] = None, page: int = 1, page_size: int = 1000, chat_id: Optional[int] = None, cancellation_token: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """
    Main entry point for ERP R12 RAG pipeline using hybrid processing.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        mode: The processing mode (default: ERP)
        session_id: Session identifier for training data collection
        client_ip: Client IP address for training data collection
        user_agent: User agent string for training data collection
        page: Page number for pagination (default: 1)
        page_size: Number of rows per page (default: 1000)
        cancellation_token: Function that returns True if operation should be cancelled
        
    Returns:
        Dictionary containing the response with SQL, results, and summary
    """
    try:
        logger.info(f"Processing ERP R12 query with hybrid processor: {user_query}")
        
        # Import the ERP hybrid processor locally to avoid circular imports
        from app.ERP_R12_Test_DB.hybrid_processor import ERPHybridProcessor
        
        # Create an instance of the ERP hybrid processor
        erp_hybrid_processor = ERPHybridProcessor()
        
        # Use the hybrid processor for ERP queries
        result = await erp_hybrid_processor.process_query(
            user_query=user_query,
            selected_db=selected_db,
            mode=mode,
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent,
            page=page,
            page_size=page_size,
            chat_id=chat_id,  # Pass chat_id for message recording
            cancellation_token=cancellation_token
        )
        
        return result
        
    except Exception as e:
        logger.error(f"ERP R12 RAG pipeline failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"ERP R12 processing failed: {str(e)}",
            "schema_context": [],
            "schema_context_ids": []
        }

def get_erp_schema_context(user_query: str, selected_db: str = "source_db_2") -> Tuple[List[str], List[str]]:
    """
    Get ERP R12 schema context for a user query with enhanced dynamic discovery.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        
    Returns:
        Tuple containing (schema_context_texts, schema_context_ids)
    """
    try:
        # Search for similar schema documents with higher top_k for better coverage
        schema_docs = search_similar_schema(user_query, selected_db, top_k=30)
        
        # Extract schema context texts and IDs
        schema_context_texts = []
        schema_context_ids = []
        processed_tables = set()  # To avoid duplicates
        processed_columns = set()  # To avoid duplicate columns
        
        # First pass: Get table-level information
        for doc in schema_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about a table
                if doc['metadata'].get('kind') == 'table':
                    table_name = doc['metadata'].get('table')
                    if table_name and table_name not in processed_tables:
                        schema_context_texts.append(doc['document'])
                        schema_context_ids.append(doc.get('id', ''))
                        processed_tables.add(table_name)
        
        # Second pass: Get column-level information for the identified tables
        for doc in schema_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about columns of tables we've identified
                if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') in processed_tables:
                    column_key = f"{doc['metadata'].get('source_table')}.{doc['metadata'].get('column')}"
                    if column_key not in processed_columns:
                        schema_context_texts.append(doc['document'])
                        schema_context_ids.append(doc.get('id', ''))
                        processed_columns.add(column_key)
        
        # Third pass: Get relationship information between identified tables
        for doc in schema_docs:
            if 'document' in doc and 'metadata' in doc:
                # Check if this document is about relationships between our tables
                if doc['metadata'].get('kind') == 'relationship':
                    left_table = doc['metadata'].get('left_table')
                    right_table = doc['metadata'].get('right_table')
                    if left_table in processed_tables and right_table in processed_tables:
                        schema_context_texts.append(doc['document'])
                        schema_context_ids.append(doc.get('id', ''))
        
        # If we don't have enough context, get general ERP schema info
        if len(schema_context_texts) < 8:
            # Get general schema information
            general_docs = search_similar_schema("ERP R12 schema overview", selected_db, top_k=15)
            for doc in general_docs:
                if 'document' in doc and doc['document'] not in schema_context_texts:
                    schema_context_texts.append(doc['document'])
                    schema_context_ids.append(doc.get('id', ''))
        
        # If we still don't have enough context, get relationship information
        if len(schema_context_texts) < 15:
            # Get relationship information
            relationship_docs = search_similar_schema("ERP R12 table relationships", selected_db, top_k=15)
            for doc in relationship_docs:
                if 'document' in doc and doc['document'] not in schema_context_texts:
                    schema_context_texts.append(doc['document'])
                    schema_context_ids.append(doc.get('id', ''))
        
        # Enhanced: Get dynamic schema information for better context
        erp_tables = _get_erp_schema_info()
        if erp_tables:
            schema_info = "ERP R12 Dynamic Schema Context:\n"
            for table_name, table_info in erp_tables.items():
                schema_info += f"Table: {table_name}\n"
                schema_info += f"Description: {table_info.get('description', 'No description available')}\n"
                columns = table_info.get('columns', [])
                if columns:
                    schema_info += f"Columns: {', '.join(columns[:20])}\n"  # Limit to first 20 columns
                schema_info += "\n"
            
            # Add this dynamic schema info to the context
            schema_context_texts.append(schema_info)
            schema_context_ids.append("dynamic_schema_info")
        
        return schema_context_texts, schema_context_ids
    except Exception as e:
        logger.error(f"Failed to get ERP schema context: {e}")
        return [], []

def _optimize_local_sql_for_better_results(sql: str, user_query: str) -> str:
    """
    Optimize locally generated SQL when initial execution returns no results.
    
    Args:
        sql: The original SQL query
        user_query: The user's natural language query
        
    Returns:
        Optimized SQL query
    """
    optimized_sql = sql
    
    # Check if this is a sales analysis query that might have restrictive date filtering
    if "sales" in user_query.lower() or "month" in user_query.lower() or "compare" in user_query.lower():
        logger.info("Optimizing local SQL for sales analysis query with potentially restrictive date filtering")
        
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
        logger.info(f"Local SQL optimized from: {sql[:200]}...")
        logger.info(f"Local SQL optimized to: {optimized_sql[:200]}...")
        
    return optimized_sql

def _local_erp_processing(user_query: str, selected_db: str = "source_db_2", mode: str = "ERP", page: int = 1, page_size: int = 1000, cancellation_token: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """
    Process an ERP R12 query using local processing with enhanced dynamic capabilities.
    This method now properly delegates to the hybrid processor instead of using hardcoded SQL.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        mode: The processing mode (default: ERP)
        page: Page number for pagination (default: 1)
        page_size: Number of rows per page (default: 1000)
        cancellation_token: Function that returns True if operation should be cancelled
        
    Returns:
        Dictionary containing the response with SQL, results, and summary
    """
    try:
        logger.info(f"Processing ERP R12 query with local processing: {user_query}")
        
        # Get enhanced schema context
        schema_context_texts, schema_context_ids = get_erp_schema_context(user_query, selected_db)
        
        # For simple queries, try to generate SQL locally
        sql_query = _generate_simple_erp_sql(user_query)
        
        if sql_query and sql_query != "API_BASED_SQL_GENERATION_REQUIRED":
            # Execute the locally generated SQL
            try:
                raw_results = execute_query(sql_query, selected_db, page, page_size, cancellation_token, user_query)
                results = format_erp_results(raw_results)
                
                # Check if we got any results
                if results.get("row_count", 0) == 0:
                    logger.info("Local SQL returned 0 rows, trying optimization")
                    # Try to optimize the query
                    optimized_sql = _optimize_local_sql_for_better_results(sql_query, user_query)
                    
                    if optimized_sql != sql_query:
                        logger.info("Retrying with optimized SQL")
                        try:
                            raw_results = execute_query(optimized_sql, selected_db, page, page_size, cancellation_token, user_query)
                            results = format_erp_results(raw_results)
                            
                            # If optimization helped, use the optimized SQL
                            if results.get("row_count", 0) > 0:
                                logger.info(f"Optimized SQL returned {results.get('row_count', 0)} rows")
                                sql_query = optimized_sql
                        except Exception as opt_error:
                            logger.warning(f"Optimized SQL execution failed: {opt_error}")
                
                # Generate a simple summary
                summary = _generate_simple_summary(user_query, results)
                
                result = {
                    "status": "success",
                    "sql": sql_query,
                    "results": results,
                    "summary": summary,
                    "schema_context": schema_context_texts,
                    "schema_context_ids": schema_context_ids,
                    "mode": mode
                }
                
                return result
            except Exception as e:
                logger.warning(f"Local SQL execution failed: {e}")
        
        # If local SQL generation failed, indicate that API-based generation is required
        sql_query = "API_BASED_SQL_GENERATION_REQUIRED"
        
        # Return a response that indicates API-based processing is needed
        result = {
            "status": "requires_api",
            "message": "This query requires API-based SQL generation as per system requirements",
            "sql": sql_query,
            "results": {"columns": [], "rows": [], "row_count": 0},
            "summary": "API-based SQL generation required for this query",
            "schema_context": schema_context_texts,
            "schema_context_ids": schema_context_ids,
            "mode": mode
        }
        
        return result
    except Exception as e:
        logger.error(f"ERP R12 local processing failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"ERP R12 local processing failed: {str(e)}",
            "schema_context": [],
            "schema_context_ids": []
        }

def _generate_simple_erp_sql(user_query: str) -> Optional[str]:
    """
    Generate simple SQL for common ERP queries with enhanced dynamic capabilities.
    
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

def _generate_simple_summary(user_query: str, results: Dict[str, Any]) -> str:
    """
    Generate a simple summary for query results.
    
    Args:
        user_query: The user's natural language query
        results: The query results
        
    Returns:
        Generated summary text
    """
    row_count = results.get("row_count", 0)
    columns = results.get("columns", [])
    
    if row_count == 0:
        return f"I found no records matching your query: '{user_query}'"
    elif row_count == 1:
        return f"I found 1 record matching your query: '{user_query}'"
    else:
        return f"I found {row_count} records matching your query: '{user_query}'"

# Test code removed for production use