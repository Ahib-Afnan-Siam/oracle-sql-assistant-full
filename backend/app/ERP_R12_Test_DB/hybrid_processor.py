# ERP R12 Hybrid Processor
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
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
# Use the ERP-specific OpenRouter client
from app.ERP_R12_Test_DB.openrouter_client import get_erp_openrouter_client, OpenRouterError

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
    
    def _get_erp_schema_info(self) -> Dict[str, Any]:
        """
        Dynamically retrieve ERP schema information from the vector store.
        
        Returns:
            Dictionary containing table and column information
        """
        try:
            # Search for schema information about our key tables
            hr_ou_docs = search_similar_schema("HR_OPERATING_UNITS", "source_db_2", top_k=20)
            org_def_docs = search_similar_schema("ORG_ORGANIZATION_DEFINITIONS", "source_db_2", top_k=20)
            mtl_onhand_docs = search_similar_schema("MTL_ONHAND_QUANTITIES_DETAIL", "source_db_2", top_k=20)
            mtl_secondary_docs = search_similar_schema("MTL_SECONDARY_INVENTORIES", "source_db_2", top_k=20)
            
            # Extract table and column information from schema documents
            erp_tables = {}
            
            # Process HR_OPERATING_UNITS documents
            hr_columns = []
            for doc in hr_ou_docs:
                if 'document' in doc and 'metadata' in doc:
                    # Check if this document is about columns
                    if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'HR_OPERATING_UNITS':
                        column_name = doc['metadata'].get('column')
                        if column_name and column_name not in hr_columns:
                            hr_columns.append(column_name)
            
            erp_tables["HR_OPERATING_UNITS"] = {
                "columns": hr_columns,
                "description": "Contains operating unit definitions with business group associations. Key columns: ORGANIZATION_ID (PK), NAME, DATE_FROM, DATE_TO, BUSINESS_GROUP_ID, USABLE_FLAG. IMPORTANT: The primary key is ORGANIZATION_ID, not OPERATING_UNIT_ID."
            }
            
            # Process ORG_ORGANIZATION_DEFINITIONS documents
            org_columns = []
            for doc in org_def_docs:
                if 'document' in doc and 'metadata' in doc:
                    # Check if this document is about columns
                    if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'ORG_ORGANIZATION_DEFINITIONS':
                        column_name = doc['metadata'].get('column')
                        if column_name and column_name not in org_columns:
                            org_columns.append(column_name)
            
            erp_tables["ORG_ORGANIZATION_DEFINITIONS"] = {
                "columns": org_columns,
                "description": "Defines organizations with their codes and relationships to operating units. Key columns: ORGANIZATION_ID, ORGANIZATION_NAME, ORGANIZATION_CODE, OPERATING_UNIT (FK to HR_OPERATING_UNITS.ORGANIZATION_ID), DISABLE_DATE, INVENTORY_ENABLED_FLAG. IMPORTANT: The foreign key OPERATING_UNIT links to HR_OPERATING_UNITS.ORGANIZATION_ID, not HR_OPERATING_UNITS.OPERATING_UNIT_ID."
            }
            
            # Process MTL_ONHAND_QUANTITIES_DETAIL documents
            mtl_onhand_columns = []
            for doc in mtl_onhand_docs:
                if 'document' in doc and 'metadata' in doc:
                    # Check if this document is about columns
                    if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'MTL_ONHAND_QUANTITIES_DETAIL':
                        column_name = doc['metadata'].get('column')
                        if column_name and column_name not in mtl_onhand_columns:
                            mtl_onhand_columns.append(column_name)
            
            erp_tables["MTL_ONHAND_QUANTITIES_DETAIL"] = {
                "columns": mtl_onhand_columns,
                "description": "Contains detailed on-hand inventory quantities with subinventory locations. Key columns: INVENTORY_ITEM_ID, ORGANIZATION_ID, DATE_RECEIVED, PRIMARY_TRANSACTION_QUANTITY, SUBINVENTORY_CODE"
            }
            
            # Process MTL_SECONDARY_INVENTORIES documents
            mtl_secondary_columns = []
            for doc in mtl_secondary_docs:
                if 'document' in doc and 'metadata' in doc:
                    # Check if this document is about columns
                    if doc['metadata'].get('kind') == 'column' and doc['metadata'].get('source_table') == 'MTL_SECONDARY_INVENTORIES':
                        column_name = doc['metadata'].get('column')
                        if column_name and column_name not in mtl_secondary_columns:
                            mtl_secondary_columns.append(column_name)
            
            erp_tables["MTL_SECONDARY_INVENTORIES"] = {
                "columns": mtl_secondary_columns,
                "description": "Defines secondary inventories (subinventories) with their attributes. Key columns: SECONDARY_INVENTORY_NAME, ORGANIZATION_ID, DESCRIPTION, DISABLE_DATE, RESERVABLE_TYPE, DEFAULT_COST_GROUP_ID"
            }
            
            return erp_tables
        except Exception as e:
            logger.warning(f"Failed to retrieve dynamic schema info: {e}. Using empty schema.")
            return {
                "HR_OPERATING_UNITS": {"columns": [], "description": ""},
                "ORG_ORGANIZATION_DEFINITIONS": {"columns": [], "description": ""},
                "MTL_ONHAND_QUANTITIES_DETAIL": {"columns": [], "description": ""},
                "MTL_SECONDARY_INVENTORIES": {"columns": [], "description": ""}
            }
    
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
        
        for column in all_columns:
            if column.lower() in query_lower:
                return True
        
        # Use generic pattern matching instead of hardcoded business terms
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
            
        # Check that it doesn't end with a partial keyword that would make it incomplete
        invalid_endings = ["SELECT", "FROM", "WHERE", "JOIN", "ON", "AND", "OR", "ORDER", "GROUP", "HAVING", "BY"]
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
            
            # Add the cleaned line if it's not just markdown or explanatory text
            if not (cleaned_line.startswith("```") or cleaned_line.startswith("--") or 
                   cleaned_line.startswith("/*") or cleaned_line.startswith("*/") or
                   "SQL Query:" in cleaned_line or "Example format:" in cleaned_line or
                   cleaned_line.upper().startswith("USER QUERY:") or
                   cleaned_line.upper().startswith("ORIGINAL QUERY:") or
                   cleaned_line.upper().startswith("RESPONSE:")):
                cleaned_lines.append(cleaned_line)
        
        # Join lines with spaces (not newlines) to avoid formatting issues
        cleaned_sql = ' '.join(cleaned_lines)
        
        # Remove any markdown code block markers
        if cleaned_sql.startswith("```sql"):
            cleaned_sql = cleaned_sql[6:].strip()
        if cleaned_sql.startswith("```"):
            cleaned_sql = cleaned_sql[3:].strip()
        if cleaned_sql.endswith("```"):
            cleaned_sql = cleaned_sql[:-3].strip()
            
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
            # Get ERP OpenRouter client
            client = get_erp_openrouter_client()
            
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
            # Get ERP OpenRouter client
            client = get_erp_openrouter_client()
            
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
    
    async def process_query(
        self, 
        user_query: str, 
        selected_db: str = "", 
        mode: str = "ERP",
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process an ERP R12 query using hybrid approach with dynamic schema awareness.
        
        Args:
            user_query: The user's natural language query
            selected_db: Selected database ID
            mode: Processing mode (ERP, General)
            session_id: User session identifier
            client_ip: Client IP address
            user_agent: User agent string
            
        Returns:
            Dictionary containing the response with results and metadata
        """
        start_time = time.time()
        
        try:
            self.processing_stats["total_queries"] += 1
            logger.info(f"Processing ERP R12 query: {user_query}")
            
            # Route the query to determine the appropriate module
            routing_info = route_query(user_query, selected_db, mode)
            target_module = routing_info["module"]
            target_db = routing_info["db_id"]
            routing_confidence = routing_info["confidence"]
            
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
                        raw_results = execute_query(api_sql, target_db)
                        results = format_erp_results(raw_results)
                        
                        # Check if we got any results
                        if results.get("row_count", 0) == 0:
                            # If no results, try local processing as a fallback
                            logger.info("API-generated SQL returned 0 rows, trying local processing as fallback")
                            from app.ERP_R12_Test_DB.rag_engine import _local_erp_processing
                            local_result = _local_erp_processing(user_query, target_db, mode)
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
                        result = _local_erp_processing(user_query, target_db, mode)
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
                    result = _local_erp_processing(user_query, target_db, mode)
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
                result = _local_erp_processing(user_query, target_db, mode)
                self.processing_stats["local_processed"] += 1
                
                # Add hybrid metadata
                processing_time = time.time() - start_time
                result["hybrid_metadata"] = {
                    "processing_mode": "local_general",
                    "model_used": "local_erp_r12",
                    "selection_reasoning": routing_info["reason"],
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