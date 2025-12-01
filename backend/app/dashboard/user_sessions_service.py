"""
Service module for dashboard_user_sessions table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class UserSessionsService(BaseService):
    """Service class for user sessions-related database operations."""
    
    def create_session(self, session_id: str, user_id: str, username: str,
                      ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> bool:
        """
        Create a new user session.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            username: Username
            ip_address: IP address (optional)
            user_agent: User agent string (optional)
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            INSERT INTO dashboard_user_sessions 
            (session_id, user_id, username, ip_address, user_agent, login_time, status)
            VALUES (:session_id, :user_id, :username, :ip_address, :user_agent, CURRENT_TIMESTAMP, 'active')
        """
        
        params = {
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "ip_address": ip_address,
            "user_agent": user_agent
        }
        
        try:
            self._execute_non_query(query, params)
            return True
        except Exception as e:
            logger.error(f"Error creating session: {str(e)}")
            return False
    
    def update_session_logout(self, session_id: str) -> bool:
        """
        Update session logout time and duration.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        query = """
            UPDATE dashboard_user_sessions 
            SET logout_time = CURRENT_TIMESTAMP,
                session_duration_seconds = EXTRACT(SECOND FROM (CURRENT_TIMESTAMP - login_time)),
                status = 'completed'
            WHERE session_id = :session_id
        """
        
        rows_affected = self._execute_non_query(query, {"session_id": session_id})
        return rows_affected > 0
    
    def get_session_by_id(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session details by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session details or None if not found
        """
        query = """
            SELECT session_id, user_id, username, login_time, logout_time, 
                   session_duration_seconds, ip_address, user_agent, status
            FROM dashboard_user_sessions 
            WHERE session_id = :session_id
        """
        
        result = self._execute_query(query, {"session_id": session_id})
        return result[0] if result and len(result) > 0 else None
    
    def get_sessions_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get sessions by user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of records to return
            
        Returns:
            List of session records
        """
        query = """
            SELECT session_id, user_id, username, login_time, logout_time, 
                   session_duration_seconds, ip_address, user_agent, status
            FROM dashboard_user_sessions 
            WHERE user_id = :user_id
            ORDER BY login_time DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"user_id": user_id, "limit": limit})
    
    def get_active_sessions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get active sessions.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of active session records
        """
        query = """
            SELECT session_id, user_id, username, login_time, logout_time, 
                   session_duration_seconds, ip_address, user_agent, status
            FROM dashboard_user_sessions 
            WHERE status = 'active'
            ORDER BY login_time DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """
        Get session statistics.
        
        Returns:
            Dictionary with session statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_sessions,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_sessions,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_sessions,
                COUNT(CASE WHEN status = 'expired' THEN 1 END) as expired_sessions,
                AVG(session_duration_seconds) as avg_session_duration_seconds
            FROM dashboard_user_sessions
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}

    def get_session_trend_data(self) -> List[Dict[str, Any]]:
        """
        Get session trend data for the last 7 days.
        
        Returns:
            List of session trend data
        """
        query = """
            SELECT 
                COUNT(*) as total_sessions,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active_sessions,
                TRUNC(login_time) as date
            FROM dashboard_user_sessions
            WHERE login_time >= SYSDATE - 7
            GROUP BY TRUNC(login_time)
            ORDER BY date
        """
        
        results = self._execute_query(query)
        return results if results else []

    def get_user_growth_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get user growth data for a specified number of days using user_access_list table.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily user growth data
        """
        query = """
            SELECT 
                TRUNC(created_at) as creation_date,
                COUNT(*) as new_users
            FROM user_access_list
            WHERE created_at >= SYSDATE - :days
            GROUP BY TRUNC(created_at)
            ORDER BY creation_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_active_users_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get active users data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily active users data
        """
        query = """
            SELECT 
                TRUNC(login_time) as session_date,
                COUNT(DISTINCT user_id) as active_users
            FROM dashboard_user_sessions
            WHERE login_time >= SYSDATE - :days
            AND status IN ('active', 'completed')
            GROUP BY TRUNC(login_time)
            ORDER BY session_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []