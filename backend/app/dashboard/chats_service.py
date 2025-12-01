"""
Service module for dashboard_chats table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class ChatsService(BaseService):
    """Service class for chat-related database operations."""
    
    def create_chat(self, session_id: str, user_id: str, username: str,
                   database_type: Optional[str] = None, query_mode: Optional[str] = None) -> Optional[int]:
        """
        Create a new chat session.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            username: Username
            database_type: Database type (optional)
            query_mode: Query mode (optional)
            
        Returns:
            Chat ID of the newly created chat or None
        """
        # First insert the chat record
        insert_query = """
            INSERT INTO dashboard_chats 
            (session_id, user_id, username, start_time, status, database_type, query_mode)
            VALUES (:session_id, :user_id, :username, CURRENT_TIMESTAMP, 'active', :database_type, :query_mode)
        """
        
        params = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "database_type": database_type,
            "query_mode": query_mode
        }
        
        try:
            # Execute the insert
            self._execute_non_query(insert_query, params)
            
            # Then select the chat_id of the newly inserted record
            # Use ROWNUM to get the most recently inserted record for this session
            select_query = """
                SELECT chat_id FROM (
                    SELECT chat_id FROM dashboard_chats 
                    WHERE session_id = :session_id 
                    ORDER BY start_time DESC, chat_id DESC
                ) WHERE ROWNUM = 1
            """
            
            result = self._execute_query(select_query, {"session_id": session_id})
            return result[0]["chat_id"] if result and len(result) > 0 and "chat_id" in result[0] else None
        except Exception as e:
            logger.error(f"Error creating chat: {str(e)}")
            return None
    
    def update_chat_end(self, chat_id: int, status: str = 'completed') -> bool:
        """
        Update chat end time and duration.
        
        Args:
            chat_id: Chat identifier
            status: Chat status (completed, abandoned)
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dashboard_chats 
            SET end_time = CURRENT_TIMESTAMP,
                duration_seconds = EXTRACT(SECOND FROM (CURRENT_TIMESTAMP - start_time)),
                status = :status
            WHERE chat_id = :chat_id
        """
        
        params = {
            "chat_id": chat_id,
            "status": status
        }
        
        rows_affected = self._execute_non_query(query, params)
        return rows_affected > 0
    
    def get_chat_by_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chat details by ID.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            Chat details or None if not found
        """
        query = """
            SELECT chat_id, session_id, user_id, username, start_time, end_time, 
                   duration_seconds, status, database_type, query_mode
            FROM dashboard_chats 
            WHERE chat_id = :chat_id
        """
        
        result = self._execute_query(query, {"chat_id": chat_id})
        return result[0] if result else None
    
    def get_chats_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all chats for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of chat details
        """
        query = """
            SELECT chat_id, session_id, user_id, username, start_time, end_time, 
                   duration_seconds, status, database_type, query_mode
            FROM dashboard_chats 
            WHERE session_id = :session_id
            ORDER BY start_time DESC
        """
        
        return self._execute_query(query, {"session_id": session_id})
    
    def get_active_chats(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get active chats.
        
        Args:
            limit: Maximum number of chats to return
            
        Returns:
            List of active chat details
        """
        query = """
            SELECT chat_id, session_id, user_id, username, start_time, end_time, 
                   duration_seconds, status, database_type, query_mode
            FROM dashboard_chats 
            WHERE status = 'active'
            ORDER BY start_time DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_chat_statistics(self) -> Dict[str, Any]:
        """
        Get chat statistics.
        
        Returns:
            Dictionary with chat statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_chats,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_chats,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_chats,
                COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned_chats,
                AVG(duration_seconds) as avg_duration_seconds
            FROM dashboard_chats
        """
        
        result = self._execute_query(query)
        return result[0] if result else {}

    def get_chat_volume_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get chat volume data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily chat volume data
        """
        query = """
            SELECT 
                TRUNC(start_time) as chat_date,
                COUNT(*) as chat_count
            FROM dashboard_chats
            WHERE start_time >= SYSDATE - :days
            GROUP BY TRUNC(start_time)
            ORDER BY chat_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_active_chats_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get active chats data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily active chats data
        """
        query = """
            SELECT 
                TRUNC(start_time) as chat_date,
                COUNT(*) as active_chats
            FROM dashboard_chats
            WHERE start_time >= SYSDATE - :days
            AND status = 'active'
            GROUP BY TRUNC(start_time)
            ORDER BY chat_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_response_time_analysis(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get response time analysis data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily response time data with performance indicators
        """
        query = """
            SELECT 
                TRUNC(start_time) as chat_date,
                AVG(duration_seconds) as avg_response_time,
                MIN(duration_seconds) as min_response_time,
                MAX(duration_seconds) as max_response_time,
                COUNT(*) as total_chats
            FROM dashboard_chats
            WHERE start_time >= SYSDATE - :days
            AND duration_seconds IS NOT NULL
            GROUP BY TRUNC(start_time)
            ORDER BY chat_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []
