"""
Base service class for dashboard database operations.
"""
import logging
from typing import Any, Dict, List, Optional
from app.db_connector import connect_to_source, connect_vector, connect_feedback
from app.config import DATABASE_CONFIG

logger = logging.getLogger(__name__)

class BaseService:
    """Base service class with common database operations."""
    
    def __init__(self, db_key: Optional[str] = None):
        """
        Initialize base service.
        
        Args:
            db_key: Database key to connect to specific database
        """
        self.db_key = db_key or DATABASE_CONFIG.get("default_dashboard_db", "feedback_db")
    
    def _execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        try:
            with connect_feedback() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                # Get column names and normalize them to lowercase
                columns = [desc[0].lower() for desc in cursor.description] if cursor.description else []
                
                # Fetch all rows and convert to list of dictionaries
                rows = cursor.fetchall()
                result = []
                for row in rows:
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
                    result.append(row_dict)
                
                return result
        except Exception as e:
            logger.error(f"Error executing query: {query}, Error: {str(e)}")
            raise
    
    def _execute_non_query(self, query: str, params: Optional[Dict] = None) -> int:
        """
        Execute a non-SELECT query (INSERT, UPDATE, DELETE) and return affected rows.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            Number of affected rows
        """
        try:
            with connect_feedback() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error executing non-query: {query}, Error: {str(e)}")
            raise
    
    def _execute_scalar(self, query: str, params: Optional[Dict] = None) -> Any:
        """
        Execute a query that returns a single value.
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            Single value result
        """
        try:
            with connect_feedback() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error executing scalar query: {query}, Error: {str(e)}")
            raise