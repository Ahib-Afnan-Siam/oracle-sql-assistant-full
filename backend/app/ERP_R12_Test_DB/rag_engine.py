# ERP R12 RAG Engine
import logging
import re
from typing import Dict, List, Optional, Tuple, Any

# Import ERP-specific modules
from app.ERP_R12_Test_DB.vector_store_chroma import search_similar_schema
from app.ERP_R12_Test_DB.query_engine import execute_query, format_erp_results

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

async def answer(user_query: str, selected_db: str = "source_db_2", mode: str = "ERP", session_id: Optional[str] = None, client_ip: Optional[str] = None, user_agent: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point for ERP R12 RAG pipeline using hybrid processing.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        mode: The processing mode (default: ERP)
        session_id: Session identifier for training data collection
        client_ip: Client IP address for training data collection
        user_agent: User agent string for training data collection
        
    Returns:
        Dictionary containing the response with SQL, results, and summary
    """
    try:
        logger.info(f"Processing ERP R12 query with hybrid processor: {user_query}")
        
        # Import the ERP hybrid processor locally to avoid circular imports
        from app.ERP_R12_Test_DB.hybrid_processor import erp_hybrid_processor
        
        # Use the hybrid processor for ERP queries
        result = await erp_hybrid_processor.process_query(
            user_query=user_query,
            selected_db=selected_db,
            mode=mode,
            session_id=session_id,
            client_ip=client_ip,
            user_agent=user_agent
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
    Get ERP R12 schema context for a user query.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        
    Returns:
        Tuple containing (schema_context_texts, schema_context_ids)
    """
    try:
        # Search for similar schema documents with higher top_k for better coverage
        schema_docs = search_similar_schema(user_query, selected_db, top_k=10)
        
        # Extract schema context texts and IDs
        schema_context_texts = []
        schema_context_ids = []
        
        for doc in schema_docs:
            if 'document' in doc:
                schema_context_texts.append(doc['document'])
                schema_context_ids.append(doc.get('id', ''))
        
        # If we don't have enough context, get general ERP schema info
        if len(schema_context_texts) < 3:
            # Get general schema information
            general_docs = search_similar_schema("ERP R12 schema overview", selected_db, top_k=5)
            for doc in general_docs:
                if 'document' in doc and doc['document'] not in schema_context_texts:
                    schema_context_texts.append(doc['document'])
                    schema_context_ids.append(doc.get('id', ''))
        
        return schema_context_texts, schema_context_ids
    except Exception as e:
        logger.error(f"Failed to get ERP schema context: {e}")
        return [], []

def _local_erp_processing(user_query: str, selected_db: str = "source_db_2", mode: str = "ERP") -> Dict[str, Any]:
    """
    Process an ERP R12 query using local processing.
    This method now properly delegates to the hybrid processor instead of using hardcoded SQL.
    
    Args:
        user_query: The user's natural language query
        selected_db: The database ID to query (default: source_db_2 for ERP R12)
        mode: The processing mode (default: ERP)
        
    Returns:
        Dictionary containing the response with SQL, results, and summary
    """
    try:
        logger.info(f"Processing ERP R12 query with local processing: {user_query}")
        
        # Get schema context
        schema_context_texts, schema_context_ids = get_erp_schema_context(user_query, selected_db)
        
        # For simple queries, try to generate SQL locally
        sql_query = _generate_simple_erp_sql(user_query)
        
        if sql_query:
            # Execute the locally generated SQL
            try:
                raw_results = execute_query(sql_query, selected_db)
                results = format_erp_results(raw_results)
                
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