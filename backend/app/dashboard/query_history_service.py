"""
Query History Service for Uttoron Admin Dashboard
This service handles storage and retrieval of query history with final SQL.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base_service import BaseService

logger = logging.getLogger(__name__)

class QueryHistoryService(BaseService):
    """Service for managing query history with final SQL storage."""
    
    def insert_query_record(self, user_id: Optional[str], session_id: str, user_query: str,
                          final_sql: str, execution_status: str = 'success',
                          execution_time_ms: Optional[int] = None, row_count: Optional[int] = None,
                          database_type: Optional[str] = None, query_mode: Optional[str] = None,
                          feedback_type: Optional[str] = None, feedback_comment: Optional[str] = None) -> Optional[int]:
        """
        Insert a new query record with final SQL.
        
        Args:
            user_id: User identifier (optional)
            session_id: Session identifier
            user_query: Original user query
            final_sql: Final SQL query generated
            execution_status: Execution status ('success', 'error', 'timeout') - NOT 'pending'
            execution_time_ms: Execution time in milliseconds
            row_count: Number of rows returned
            database_type: Database type
            query_mode: Query mode
            feedback_type: Feedback type (optional)
            feedback_comment: Feedback comment (optional)
            
        Returns:
            Query ID of the newly created record or None
        """
        # Validate execution_status to ensure it meets check constraints
        valid_execution_statuses = ['success', 'error', 'timeout']
        if execution_status not in valid_execution_statuses:
            logger.warning(f"Invalid execution_status '{execution_status}', defaulting to 'success'")
            execution_status = 'success'
        
        # Validate feedback_type if provided
        if feedback_type is not None:
            valid_feedback_types = ['good', 'wrong', 'needs_improvement']
            if feedback_type not in valid_feedback_types:
                logger.warning(f"Invalid feedback_type '{feedback_type}', setting to None")
                feedback_type = None
        
        # Truncate long strings to prevent constraint violations
        if user_query and len(user_query) > 4000:
            user_query = user_query[:3997] + "..."
            logger.warning("Truncated user_query to 4000 characters")
        
        if final_sql and len(final_sql) > 4000:
            final_sql = final_sql[:3997] + "..."
            logger.warning("Truncated final_sql to 4000 characters")
        
        if feedback_comment and len(feedback_comment) > 4000:
            feedback_comment = feedback_comment[:3997] + "..."
            logger.warning("Truncated feedback_comment to 4000 characters")
        
        query = """
            INSERT INTO dashboard_query_history 
            (user_id, session_id, user_query, final_sql, execution_status, execution_time_ms, 
             row_count, database_type, query_mode, feedback_type, feedback_comment, created_at, completed_at)
            VALUES (:user_id, :session_id, :user_query, :final_sql, :execution_status, 
                    :execution_time_ms, :row_count, :database_type, :query_mode, 
                    :feedback_type, :feedback_comment, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        
        params = {
            "user_id": user_id,
            "session_id": session_id,
            "user_query": user_query,
            "final_sql": final_sql,
            "execution_status": execution_status,
            "execution_time_ms": execution_time_ms,
            "row_count": row_count,
            "database_type": database_type,
            "query_mode": query_mode,
            "feedback_type": feedback_type,
            "feedback_comment": feedback_comment
        }
        
        try:
            self._execute_non_query(query, params)
            
            # Get the ID of the newly inserted record
            # Use ROWNUM to get the most recently inserted record for this session
            select_query = """
                SELECT query_id FROM (
                    SELECT query_id FROM dashboard_query_history 
                    WHERE session_id = :session_id 
                    ORDER BY created_at DESC, query_id DESC
                ) WHERE ROWNUM = 1
            """
            
            result = self._execute_query(select_query, {"session_id": session_id})
            return result[0]["query_id"] if result and len(result) > 0 and "query_id" in result[0] else None
        except Exception as e:
            logger.error(f"Error inserting query record: {str(e)}")
            return None
    
    def update_query_feedback(self, query_id: int, feedback_type: str, 
                            feedback_comment: Optional[str] = None) -> bool:
        """
        Update feedback for a query record.
        
        Args:
            query_id: Query identifier
            feedback_type: Feedback type (good, wrong, needs_improvement)
            feedback_comment: Feedback comment (optional)
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dashboard_query_history 
            SET feedback_type = :feedback_type, feedback_comment = :feedback_comment
            WHERE query_id = :query_id
        """
        
        params = {
            "query_id": query_id,
            "feedback_type": feedback_type,
            "feedback_comment": feedback_comment
        }
        
        try:
            rows_affected = self._execute_non_query(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Error updating query feedback: {str(e)}")
            return False
    
    def update_query_execution_result(self, query_id: int, execution_status: str,
                                    execution_time_ms: Optional[int] = None, 
                                    row_count: Optional[int] = None) -> bool:
        """
        Update execution result for a query record.
        
        Args:
            query_id: Query identifier
            execution_status: Execution status (success, error, timeout)
            execution_time_ms: Execution time in milliseconds
            row_count: Number of rows returned
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dashboard_query_history 
            SET execution_status = :execution_status, execution_time_ms = :execution_time_ms, 
                row_count = :row_count, completed_at = CURRENT_TIMESTAMP
            WHERE query_id = :query_id
        """
        
        params = {
            "query_id": query_id,
            "execution_status": execution_status,
            "execution_time_ms": execution_time_ms,
            "row_count": row_count
        }
        
        try:
            rows_affected = self._execute_non_query(query, params)
            return rows_affected > 0
        except Exception as e:
            logger.error(f"Error updating query execution result: {str(e)}")
            return False
    
    def get_query_by_id(self, query_id: int) -> Optional[Dict[str, Any]]:
        """
        Get query record by ID.
        
        Args:
            query_id: Query identifier
            
        Returns:
            Query record or None if not found
        """
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            WHERE query_id = :query_id
        """
        
        result = self._execute_query(query, {"query_id": query_id})
        return result[0] if result and len(result) > 0 else None
    
    def get_queries_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get query records by user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of records to return
            
        Returns:
            List of query records
        """
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"user_id": user_id, "limit": limit})
    
    def get_queries_by_session(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get query records by session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of records to return
            
        Returns:
            List of query records
        """
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            WHERE session_id = :session_id
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"session_id": session_id, "limit": limit})
    
    def get_recent_queries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent query records.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent query records
        """
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """
        Get query statistics.
        
        Returns:
            Dictionary with query statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_queries,
                COUNT(CASE WHEN execution_status = 'success' THEN 1 END) as successful_queries,
                COUNT(CASE WHEN execution_status = 'error' THEN 1 END) as error_queries,
                COUNT(CASE WHEN execution_status = 'timeout' THEN 1 END) as timeout_queries,
                COUNT(CASE WHEN feedback_type = 'good' THEN 1 END) as positive_feedback,
                COUNT(CASE WHEN feedback_type = 'wrong' THEN 1 END) as negative_feedback,
                COUNT(CASE WHEN feedback_type = 'needs_improvement' THEN 1 END) as improvement_feedback,
                AVG(execution_time_ms) as avg_execution_time_ms,
                AVG(row_count) as avg_row_count
            FROM dashboard_query_history
        """
        
        result = self._execute_query(query)
        return result[0] if result else {}
    
    def get_feedback_statistics(self) -> Dict[str, Any]:
        """
        Get feedback statistics.
        
        Returns:
            Dictionary with feedback statistics
        """
        query = """
            SELECT 
                feedback_type,
                COUNT(*) as count
            FROM dashboard_query_history
            WHERE feedback_type IS NOT NULL
            GROUP BY feedback_type
            ORDER BY count DESC
        """
        
        results = self._execute_query(query)
        return {row["feedback_type"]: row["count"] for row in results} if results else {}

    def get_query_by_chat_and_message(self, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get query record by chat_id and message_id.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier
            
        Returns:
            Query record or None if not found
        """
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            WHERE session_id = (
                SELECT session_id FROM dashboard_chats WHERE chat_id = :chat_id
            )
            AND user_query = (
                SELECT content FROM dashboard_messages WHERE message_id = :message_id AND chat_id = :chat_id
            )
            AND ROWNUM = 1
        """
        
        result = self._execute_query(query, {"chat_id": chat_id, "message_id": message_id})
        return result[0] if result and len(result) > 0 else None

    def get_filtered_query_history(self, user_id: str, database_type: Optional[str] = None, 
                                 query_mode: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get filtered query history based on user, database type, and query mode.
        
        Args:
            user_id: User identifier
            database_type: Database type filter (optional)
            query_mode: Query mode filter (optional)
            limit: Maximum number of records to return
            
        Returns:
            List of query records filtered by success status and ordered by creation time
        """
        # Normalize query_mode to match the format used in the database
        normalized_query_mode = None
        if query_mode:
            normalized_query_mode = self._normalize_mode(query_mode)
        
        # Base query with required filters
        query = """
            SELECT query_id, user_id, session_id, user_query, final_sql, execution_status,
                   execution_time_ms, row_count, database_type, query_mode, feedback_type,
                   feedback_comment, created_at, completed_at
            FROM dashboard_query_history 
            WHERE user_id = :user_id
            AND execution_status = 'success'
        """
        
        # Add parameters
        params = {
            "user_id": user_id,
            "limit": limit
        }
        
        # Add optional filters
        if database_type:
            query += " AND database_type = :database_type"
            params["database_type"] = database_type
            
        if normalized_query_mode:
            query += " AND query_mode = :query_mode"
            params["query_mode"] = normalized_query_mode
            
        # Add ordering and limit
        query += """
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, params)
    
    def _normalize_mode(self, mode: Optional[str]) -> str:
        """
        Normalize inbound mode strings to one of: 'General', 'SOS', 'PRAN_ERP', 'RFL_ERP'
        Accepts legacy/loose inputs.
        """
        if not mode:
            return "General"
        m = mode.strip().lower()
        if m in ("general", "gen"):
            return "General"
        if m in ("sos", "source_db_1", "db1"):
            return "SOS"
        if m in ("erp", "source_db_2", "db2", "r12", "test db", "test_db", "pran erp"):
            return "PRAN_ERP"
        if m in ("rfl erp", "source_db_3", "db3"):
            return "RFL_ERP"
        return "General"
