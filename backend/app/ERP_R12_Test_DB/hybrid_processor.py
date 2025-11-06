# ERP R12 Hybrid Processor
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
from app.ERP_R12_Test_DB.query_router import route_query
from app.ERP_R12_Test_DB.query_classifier import QueryClassifier
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema
from app.ERP_R12_Test_DB.query_interpreter import erp_query_interpreter
from app.config import (
    HYBRID_ENABLED, LOCAL_CONFIDENCE_THRESHOLD, 
    SKIP_API_THRESHOLD, FORCE_HYBRID_THRESHOLD,
    API_MODELS
)
# Use the ERP-specific DeepSeek client
from app.ERP_R12_Test_DB.deepseek_client import get_erp_deepseek_client, DeepSeekError

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

@dataclass
class ProcessingResult:
    selected_response: str = ""
    local_response: Optional[str] = None
    api_response: Optional[str] = None
    processing_mode: str = "unknown"
    selection_reasoning: str = "No reasoning provided"
    local_confidence: float = 0.0
    api_confidence: float = 0.0
    processing_time: float = 0.0
    model_used: str = "unknown"

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

class ERPHybridProcessor:
    """
    Hybrid processor for ERP R12 queries that can process queries using both local and API models.
    Dynamically adapts to ERP R12 schema information from the vector store.
    """
    
    def __init__(self):
        self.processing_stats = {
            "total_queries": 0,
            "local_processed": 0,
            "api_processed": 0,
            "hybrid_processed": 0
        }
        self.query_classifier = QueryClassifier()
    
    def _discover_erp_tables(self) -> List[str]:
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
    
    def _get_erp_schema_info(self) -> Dict[str, Any]:
        """
        Dynamically retrieve ERP schema information from the vector store.
        
        Returns:
            Dictionary containing table and column information
        """
        try:
            # Dynamically discover ERP tables instead of hardcoding them
            table_names = self._discover_erp_tables()
            
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
    
    def _is_erp_query_dynamic(self, user_query: str) -> bool:
        """
        Dynamically determine if a query should be routed to ERP R12 based on schema information.
        
        Args:
            user_query: The user's natural language query
            
        Returns:
            True if the query should be routed to ERP R12, False otherwise
        """
        query_lower = user_query.lower()
        
        # Get dynamic schema information
        erp_tables = self._get_erp_schema_info()
        
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
    
    def _is_valid_sql_query(self, sql: str) -> bool:
        """
        Basic validation to check if the generated SQL looks valid.
        
        Args:
            sql: The SQL query to validate
            
        Returns:
            True if the SQL looks valid, False otherwise
        """
        if not sql or not isinstance(sql, str):
            logger.debug(f"SQL validation failed: Empty or non-string SQL")
            return False
            
        sql = sql.strip()
        
        # Log the SQL for debugging
        logger.debug(f"Validating SQL: {sql[:300]}...")
        
        # Must start with SELECT or WITH (CTE)
        if not (sql.upper().startswith("SELECT") or sql.upper().startswith("WITH")):
            logger.warning(f"SQL validation failed: Doesn't start with SELECT or WITH - {sql[:100]}...")
            return False
            
        # Must have FROM clause for SELECT statements (unless it's a VALUES clause)
        if sql.upper().startswith("SELECT") and "FROM" not in sql.upper() and "VALUES" not in sql.upper():
            logger.warning(f"SQL validation failed: No FROM clause in SELECT statement - {sql[:100]}...")
            return False
            
        # Should not have incomplete clauses - basic check for unmatched parentheses
        if sql.count("(") != sql.count(")"):
            logger.warning(f"SQL validation failed: Unmatched parentheses - {sql[:100]}...")
            return False
            
        # Additional checks for common issues
        if "..." in sql:
            logger.warning(f"SQL validation failed: Contains ellipsis - {sql[:100]}...")
            return False
            
        # Check for common SQL injection patterns (basic security check)
        dangerous_patterns = ["DROP", "DELETE", "UPDATE", "INSERT", "CREATE", "ALTER", "TRUNCATE"]
        sql_upper = sql.upper()
        for pattern in dangerous_patterns:
            if pattern in sql_upper and not (pattern + "_") in sql_upper and not ("_" + pattern) in sql_upper:
                # Make sure it's not part of a table/column name
                if f" {pattern} " in sql_upper or sql_upper.startswith(pattern + " ") or sql_upper.endswith(" " + pattern):
                    logger.warning(f"SQL validation failed: Contains dangerous pattern '{pattern}' - {sql[:100]}...")
                    return False
            
        # Check that it doesn't end with a partial keyword that would make it incomplete
        invalid_endings = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "AND", "OR", "ORDER", "GROUP", "HAVING", "BY", "UNION", "INTERSECT", "EXCEPT"]
        if sql.split():
            last_token = sql.split()[-1].upper().rstrip(';')
            if last_token in invalid_endings:
                logger.warning(f"SQL validation failed: Ends with invalid token '{last_token}' - {sql[:100]}...")
                return False
        
        logger.debug("SQL validation passed")
        return True
    
    def _clean_sql_query(self, sql: str) -> str:
        """
        Clean up SQL query to ensure it's properly formatted for execution.
        
        Args:
            sql: The SQL query to clean
            
        Returns:
            Cleaned SQL query
        """
        if not sql or not isinstance(sql, str):
            return sql
            
        logger.debug(f"Cleaning SQL: {sql[:200]}...")
        
        # First, try to extract just the SQL part if there's explanatory text
        # Look for the first SELECT or WITH statement
        select_pos = sql.upper().find('SELECT')
        with_pos = sql.upper().find('WITH')
        
        # Use the first occurrence of either SELECT or WITH
        sql_start = -1
        if select_pos >= 0 and with_pos >= 0:
            sql_start = min(select_pos, with_pos)
        elif select_pos >= 0:
            sql_start = select_pos
        elif with_pos >= 0:
            sql_start = with_pos
            
        if sql_start > 0:
            sql = sql[sql_start:]
        elif sql_start == -1:
            # No SELECT or WITH found, return as is but cleaned
            sql = sql.strip()
        
        # Split into lines and clean each line
        lines = sql.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Strip leading/trailing whitespace
            cleaned_line = line.strip()
            
            # Skip empty lines
            if not cleaned_line:
                continue
                
            # Remove any trailing semicolons (we'll add one at the end)
            cleaned_line = cleaned_line.rstrip(';')
            
            # Remove any markdown code block markers
            if cleaned_line.startswith("```sql"):
                cleaned_line = cleaned_line[6:].strip()
            if cleaned_line.startswith("```"):
                cleaned_line = cleaned_line[3:].strip()
            if cleaned_line.endswith("```"):
                cleaned_line = cleaned_line[:-3].strip()
                
            # Add the cleaned line if it's not just metadata or explanatory text
            if not (cleaned_line.startswith("```") or cleaned_line.startswith("--") or 
                   cleaned_line.startswith("/*") or cleaned_line.startswith("*/") or
                   "SQL Query:" in cleaned_line or "Example format:" in cleaned_line or
                   cleaned_line.upper().startswith("USER QUERY:") or
                   cleaned_line.upper().startswith("ORIGINAL QUERY:") or
                   cleaned_line.upper().startswith("RESPONSE:") or
                   cleaned_line.upper().startswith("EXPLANATION:") or
                   cleaned_line.upper().startswith("NOTE:") or
                   cleaned_line.upper().startswith("COMMENT:")):
                cleaned_lines.append(cleaned_line)
        
        # Join lines with spaces (not newlines) to avoid formatting issues
        cleaned_sql = ' '.join(cleaned_lines)
        
        # Remove any explanatory text before the SQL
        select_pos = cleaned_sql.upper().find('SELECT')
        with_pos = cleaned_sql.upper().find('WITH')
        sql_start = -1
        if select_pos >= 0 and with_pos >= 0:
            sql_start = min(select_pos, with_pos)
        elif select_pos >= 0:
            sql_start = select_pos
        elif with_pos >= 0:
            sql_start = with_pos
            
        if sql_start > 0:
            cleaned_sql = cleaned_sql[sql_start:]
        
        # Ensure it ends with a semicolon
        if cleaned_sql and not cleaned_sql.endswith(';'):
            cleaned_sql += ';'
            
        # Final validation - remove any trailing whitespace
        cleaned_sql = cleaned_sql.strip()
        
        logger.debug(f"Cleaned SQL: {cleaned_sql[:200]}...")
        return cleaned_sql
    
    async def _generate_sql_with_api(self, user_query: str, schema_context: List[str]) -> Optional[str]:
        """
        Generate SQL using API models with fallback mechanism.
        
        Args:
            user_query: The user's natural language query
            schema_context: Schema context information
            
        Returns:
            Generated SQL query or None if failed
        """
        try:
            # Get ERP DeepSeek client
            client = get_erp_deepseek_client()
            
            # Get ERP schema info
            erp_tables = self._get_erp_schema_info()
            
            # Update the query interpreter with current schema context
            erp_query_interpreter.update_schema_context(erp_tables)
            
            # Create a strict prompt for ERP R12 SQL generation to avoid content moderation issues
            schema_info = ''
            for table_name, table_info in erp_tables.items():
                schema_info += f"{table_name}: {table_info['description']} | Columns: {', '.join(table_info['columns'][:15])}\n"
            
            # Use the get_model_with_fallback method instead of direct chat_completion
            response = await client.get_model_with_fallback("hr", user_query, schema_info)
            
            if response.success:
                logger.debug(f"API response content: {response.content[:500]}...")
                
                # Extract SQL from response (remove any extra text)
                sql = response.content.strip()
                
                # Log the raw SQL before cleaning
                logger.debug(f"Raw SQL before cleaning: {repr(sql[:300])}")
                
                # More robust extraction of SQL from the response
                # First, try to find the SQL by looking for SELECT or WITH
                select_pos = sql.upper().find('SELECT')
                with_pos = sql.upper().find('WITH')
                sql_start = -1
                
                if select_pos >= 0 and with_pos >= 0:
                    sql_start = min(select_pos, with_pos)
                elif select_pos >= 0:
                    sql_start = select_pos
                elif with_pos >= 0:
                    sql_start = with_pos
                
                if sql_start >= 0:
                    # Extract from the first SELECT/WITH to the end
                    sql_content = sql[sql_start:]
                    
                    # Find the end of the SQL statement (look for semicolon or end of content)
                    semicolon_pos = sql_content.find(';')
                    if semicolon_pos >= 0:
                        # Include the semicolon
                        sql_content = sql_content[:semicolon_pos + 1]
                    else:
                        # No semicolon found, try to find the end by looking for a complete statement
                        # We'll take everything from SELECT/WITH to the end and clean it up
                        pass
                    
                    sql = sql_content
                
                # Remove any markdown code block markers and explanatory text
                lines = sql.split('\n')
                sql_lines = []
                
                for line in lines:
                    stripped_line = line.strip()
                    
                    # Skip empty lines and markdown markers
                    if not stripped_line or stripped_line.startswith("```"):
                        continue
                        
                    # Remove trailing code block markers
                    if stripped_line.endswith('```'):
                        stripped_line = stripped_line[:-3].strip()
                        
                    # Add the line if it's not explanatory text
                    if not any(word in stripped_line.upper() for word in ['EXPLANATION', 'NOTE', 'COMMENT', 'DESCRIPTION', 'SQL QUERY:', 'EXAMPLE FORMAT:', 'RESPONSE:']):
                        sql_lines.append(stripped_line)
                
                # Join the lines back together
                sql = ' '.join(sql_lines).strip()
                
                # Additional cleanup for common markdown artifacts
                if sql.startswith("```sql"):
                    sql = sql[6:].strip()
                if sql.startswith("```"):
                    sql = sql[3:].strip()
                if sql.endswith("```"):
                    sql = sql[:-3].strip()
                
                # Remove any explanatory text before the SQL
                select_pos = sql.upper().find('SELECT')
                with_pos = sql.upper().find('WITH')
                sql_start = -1
                if select_pos >= 0 and with_pos >= 0:
                    sql_start = min(select_pos, with_pos)
                elif select_pos >= 0:
                    sql_start = select_pos
                elif with_pos >= 0:
                    sql_start = with_pos
                    
                if sql_start > 0:
                    sql = sql[sql_start:]
                
                # Remove any explanatory text after the semicolon
                semicolon_pos = sql.find(';')
                if semicolon_pos > 0 and len(sql) > semicolon_pos + 1:
                    # Check if there's actual SQL after the semicolon
                    remaining_text = sql[semicolon_pos + 1:].strip()
                    if remaining_text and not remaining_text.upper().startswith(('SELECT', 'WITH')):
                        sql = sql[:semicolon_pos + 1]
                
                # Final cleanup - remove any leading/trailing whitespace
                sql = sql.strip()
                
                logger.debug(f"Extracted SQL: {repr(sql[:300])}")
                
                # Validate that this looks like a proper SQL query
                if self._is_valid_sql_query(sql):
                    logger.info(f"Successfully generated valid SQL: {sql[:200]}...")
                    return sql
                else:
                    logger.warning(f"Generated SQL is not valid: {repr(sql[:200])}")
                    # Log more details about why it's invalid
                    if not sql:
                        logger.warning("SQL is empty")
                    elif not (sql.upper().startswith("SELECT") or sql.upper().startswith("WITH")):
                        logger.warning("SQL doesn't start with SELECT or WITH")
                    elif sql.upper().startswith("SELECT") and "FROM" not in sql.upper() and "VALUES" not in sql.upper():
                        logger.warning("SQL doesn't contain FROM clause")
                    elif "..." in sql:
                        logger.warning("SQL contains ellipsis")
                    return None
            else:
                logger.warning(f"Failed to generate SQL with API models: {response.error}")
                # Check if it was a content moderation issue
                if response.status_code == 403 and "moderation" in (response.error or "").lower():
                    logger.info("Content moderation flagged the query, will try local processing as fallback")
                    
            return None
        except Exception as e:
            logger.error(f"Failed to generate SQL with API: {e}")
            logger.exception("Exception details:")
            return None
    
    async def _generate_summary_with_api(self, user_query: str, columns: List[str], rows: List[Dict], sql: str) -> Optional[str]:
        """
        Generate summary using API models.
        
        Args:
            user_query: The user's natural language query
            columns: Column names from the query results
            rows: Query result rows
            sql: The SQL query that was executed
            
        Returns:
            Generated summary or None if failed
        """
        try:
            # Get ERP DeepSeek client
            client = get_erp_deepseek_client()
            
            # Create a minimal summary prompt
            prompt = f"Q: {user_query}\n\nResults:\nColumns: {', '.join(columns)}\nCount: {len(rows)}\n\nSummarize:"

            # Use only the primary model to avoid content moderation and 404 issues
            primary_model = API_MODELS["hr"]["primary"]  # Updated to use configured model
            
            try:
                # Create messages for the API
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
                
                # Generate summary using API with only the primary model
                response = await client.chat_completion(
                    messages=messages,
                    model=primary_model,
                    temperature=0.3,
                    max_tokens=300
                )
                
                if response.success:
                    # Clean up the response content
                    summary = response.content.strip()
                    
                    # Remove any markdown code block markers
                    if summary.startswith("```"):
                        summary = summary[3:].strip()
                    if summary.endswith("```"):
                        summary = summary[:-3].strip()
                    
                    return summary
                else:
                    logger.warning(f"Failed to generate summary with {primary_model}: {response.error}")
                    
            except Exception as model_error:
                logger.warning(f"Error with model {primary_model}: {model_error}")
                logger.exception("Exception details:")
                    
            return None
        except Exception as e:
            logger.error(f"Failed to generate summary with API: {e}")
            logger.exception("Exception details:")
            return None
    
    def _optimize_sql_for_better_results(self, sql: str, user_query: str) -> str:
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

    async def process_query(self, user_query: str, selected_db: str = "source_db_2", mode: str = "ERP", session_id: Optional[str] = None, client_ip: Optional[str] = None, user_agent: Optional[str] = None, page: int = 1, page_size: int = 1000, cancellation_token: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """
        Process an ERP R12 query using hybrid approach with dynamic schema context.
        
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
        start_time = time.time()
        self.processing_stats["total_queries"] += 1
        
        try:
            logger.info(f"Processing ERP R12 query: {user_query}")
            
            # Route the query to determine the best processing approach
            routing_info = route_query(user_query, selected_db)
            target_module = routing_info.get("module", "ERP_R12")  # Fixed: use "module" instead of "target_module"
            routing_confidence = routing_info.get("confidence", 0.8)
            target_db = routing_info.get("db_id", selected_db)
            
            logger.info(f"Query routed to {target_module} with confidence {routing_confidence:.2f}")
            
            # Process based on routing
            if target_module == "ERP_R12":
                # Import the ERP R12 functions locally to avoid circular imports
                from app.ERP_R12_Test_DB.rag_engine import get_erp_schema_context
                from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results
                
                # Get schema context for API processing
                schema_context_texts, schema_context_ids = get_erp_schema_context(user_query, target_db)
                
                # Try to generate SQL with API first
                api_sql = await self._generate_sql_with_api(user_query, schema_context_texts)
                
                if api_sql:
                    # Clean up the SQL before execution
                    api_sql = self._clean_sql_query(api_sql)
                    logger.info(f"Generated SQL: {api_sql}")
                    # Execute the API-generated SQL
                    try:
                        # Import the functions locally to ensure they're in scope
                        from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results
                        raw_results = execute_query(api_sql, target_db, page, page_size, cancellation_token, user_query)
                        results = format_erp_results(raw_results)
                        
                        # Check if we got any results
                        if results.get("row_count", 0) == 0:
                            # If no results, try to optimize the SQL query
                            logger.info("API-generated SQL returned 0 rows, attempting to optimize query")
                            optimized_sql = self._optimize_sql_for_better_results(api_sql, user_query)
                            
                            if optimized_sql != api_sql:
                                logger.info("Retrying with optimized SQL")
                                raw_results = execute_query(optimized_sql, target_db, page, page_size, cancellation_token, user_query)
                                results = format_erp_results(raw_results)
                                
                                # Check if optimization helped
                                if results.get("row_count", 0) > 0:
                                    logger.info(f"Optimized SQL returned {results.get('row_count', 0)} rows")
                                    api_sql = optimized_sql  # Use the optimized SQL for further processing
                                else:
                                    logger.info("Optimized SQL also returned 0 rows, trying local processing as fallback")
                                    # If still no results, try local processing as a fallback
                                    from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                                    local_result = _local_erp_processing(user_query, target_db, mode, page, page_size, cancellation_token)
                                    if local_result.get("status") == "success" and local_result.get("results", {}).get("row_count", 0) > 0:
                                        logger.info("Local processing returned results, using local results")
                                        local_result["hybrid_metadata"] = {
                                            "processing_mode": "local_erp_fallback",
                                            "model_used": "local_erp_r12",
                                            "selection_reasoning": f"API-generated SQL returned 0 rows even after optimization, local processing returned results. Routing confidence: {routing_confidence:.2f}",
                                            "processing_time": time.time() - start_time,
                                            "routing_confidence": routing_confidence,
                                            "target_module": target_module,
                                            "target_db": target_db
                                        }
                                        self.processing_stats["local_processed"] += 1
                                        return local_result
                                    else:
                                        logger.info("Local processing also returned 0 rows or failed, using API results")
                            else:
                                # No optimization was possible, try local processing as a fallback
                                logger.info("API-generated SQL returned 0 rows, trying local processing as fallback")
                                from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                                local_result = _local_erp_processing(user_query, target_db, mode, page, page_size, cancellation_token)
                                if local_result.get("status") == "success" and local_result.get("results", {}).get("row_count", 0) > 0:
                                    logger.info("Local processing returned results, using local results")
                                    local_result["hybrid_metadata"] = {
                                        "processing_mode": "local_erp_fallback",
                                        "model_used": "local_erp_r12",
                                        "selection_reasoning": f"API-generated SQL returned 0 rows, local processing returned results. Routing confidence: {routing_confidence:.2f}",
                                        "processing_time": time.time() - start_time,
                                        "routing_confidence": routing_confidence,
                                        "target_module": target_module,
                                        "target_db": target_db
                                    }
                                    self.processing_stats["local_processed"] += 1
                                    return local_result
                                else:
                                    logger.info("Local processing also returned 0 rows or failed, using API results")
                        
                        # Try to generate summary with API
                        api_summary = await self._generate_summary_with_api(
                            user_query, 
                            results.get("columns", []), 
                            results.get("rows", []), 
                            api_sql
                        )
                        
                        # Use API results
                        processing_time = time.time() - start_time
                        result = {
                            "status": "success",
                            "sql": api_sql,
                            "results": results,
                            "summary": api_summary if api_summary else "API summary generation failed.",
                            "schema_context": schema_context_texts,
                            "schema_context_ids": schema_context_ids,
                            "mode": mode
                        }
                        
                        self.processing_stats["api_processed"] += 1
                        
                        # Add hybrid metadata
                        result["hybrid_metadata"] = {
                            "processing_mode": "api_erp",
                            "model_used": "api_erp_r12",
                            "selection_reasoning": f"API-generated SQL and summary for ERP query. Routing confidence: {routing_confidence:.2f}",
                            "processing_time": processing_time,
                            "routing_confidence": routing_confidence,
                            "target_module": target_module,
                            "target_db": target_db
                        }
                        
                        return result
                    except Exception as e:
                        logger.error(f"API SQL execution failed: {e}")
                        logger.error(f"Failed SQL was: {api_sql}")
                        # Fall back to local processing - import locally to avoid circular imports
                        from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                        # Import the functions locally to ensure they're in scope
                        from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results
                        result = _local_erp_processing(user_query, target_db, mode, page, page_size, cancellation_token)
                        self.processing_stats["local_processed"] += 1
                        
                        # Add hybrid metadata
                        processing_time = time.time() - start_time
                        result["hybrid_metadata"] = {
                            "processing_mode": "local_erp_fallback",
                            "model_used": "local_erp_r12",
                            "selection_reasoning": f"API SQL execution failed, falling back to local processing. Routing confidence: {routing_confidence:.2f}",
                            "processing_time": processing_time,
                            "routing_confidence": routing_confidence,
                            "target_module": target_module,
                            "target_db": target_db,
                            "error": str(e)
                        }
                        return result
                else:
                    # Fall back to local processing if API SQL generation failed
                    from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                    # Import the functions locally to ensure they're in scope
                    from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results
                    result = _local_erp_processing(user_query, target_db, mode, page, page_size, cancellation_token)
                    self.processing_stats["local_processed"] += 1
                    
                    # Add hybrid metadata
                    processing_time = time.time() - start_time
                    result["hybrid_metadata"] = {
                        "processing_mode": "local_erp_fallback",
                        "model_used": "local_erp_r12",
                        "selection_reasoning": f"API SQL generation failed, falling back to local processing. Routing confidence: {routing_confidence:.2f}",
                        "processing_time": processing_time,
                        "routing_confidence": routing_confidence,
                        "target_module": target_module,
                        "target_db": target_db,
                        "error": "API SQL generation failed"
                    }
            else:
                # For non-ERP queries, fall back to local processing
                from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                result = _local_erp_processing(user_query, target_db, mode, page, page_size, cancellation_token)
                self.processing_stats["local_processed"] += 1
                
                # Add hybrid metadata
                processing_time = time.time() - start_time
                result["hybrid_metadata"] = {
                    "processing_mode": "local_general",
                    "model_used": "local_erp_r12",
                    "selection_reasoning": routing_info.get("reason", "Default fallback for non-ERP queries"),
                    "processing_time": processing_time,
                    "routing_confidence": routing_confidence,
                    "target_module": target_module,
                    "target_db": target_db
                }
            
            logger.info(f"Query processed in {processing_time:.2f} seconds")
            return result
            
        except Exception as e:
            logger.error(f"ERP hybrid processing failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"ERP processing failed: {str(e)}",
                "hybrid_metadata": {
                    "processing_mode": "error",
                    "processing_time": time.time() - start_time,
                    "error": str(e)
                }
            }
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns:
            Dictionary containing processing statistics
        """
        return self.processing_stats.copy()
    
    def reset_stats(self):
        """
        Reset processing statistics.
        """
        self.processing_stats = {
            "total_queries": 0,
            "local_processed": 0,
            "api_processed": 0,
            "hybrid_processed": 0
        }

# Global instance
erp_hybrid_processor = ERPHybridProcessor()