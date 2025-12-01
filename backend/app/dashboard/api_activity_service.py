"""
Service module for dashboard_api_activity table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class APIActivityService(BaseService):
    """Service class for API activity-related database operations."""
    
    def log_api_call(self, api_endpoint: str, http_method: str, response_status: int,
                    response_time_ms: int, user_id: Optional[str] = None,
                    ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> Optional[int]:
        """
        Log an API call.
        
        Args:
            api_endpoint: API endpoint
            http_method: HTTP method (GET, POST, etc.)
            response_status: HTTP response status code
            response_time_ms: Response time in milliseconds
            user_id: User identifier (optional)
            ip_address: IP address (optional)
            user_agent: User agent string (optional)
            
        Returns:
            Activity ID of the newly created record or None
        """
        insert_query = """
            INSERT INTO dashboard_api_activity 
            (api_endpoint, http_method, response_status, response_time_ms, 
             user_id, ip_address, user_agent, timestamp)
            VALUES (:api_endpoint, :http_method, :response_status, :response_time_ms, 
                    :user_id, :ip_address, :user_agent, CURRENT_TIMESTAMP)
        """
        
        params = {
            "api_endpoint": api_endpoint,
            "http_method": http_method,
            "response_status": response_status,
            "response_time_ms": response_time_ms,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent
        }
        
        self._execute_non_query(insert_query, params)
        
        # Get the ID of the newly inserted record
        # Use ROWNUM to get the most recently inserted record for this endpoint
        select_query = """
            SELECT activity_id FROM (
                SELECT activity_id FROM dashboard_api_activity 
                WHERE api_endpoint = :api_endpoint
                ORDER BY timestamp DESC, activity_id DESC
            ) WHERE ROWNUM = 1
        """
        
        result = self._execute_query(select_query, {"api_endpoint": api_endpoint})
        return result[0]["activity_id"] if result and len(result) > 0 and "activity_id" in result[0] else None
    
    def get_activity_by_endpoint(self, api_endpoint: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get API activity by endpoint.
        
        Args:
            api_endpoint: API endpoint
            limit: Maximum number of records to return
            
        Returns:
            List of API activity records
        """
        query = """
            SELECT activity_id, api_endpoint, http_method, response_status, 
                   response_time_ms, user_id, ip_address, user_agent, timestamp
            FROM dashboard_api_activity 
            WHERE api_endpoint = :api_endpoint
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"api_endpoint": api_endpoint, "limit": limit})
    
    def get_activity_by_user(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get API activity by user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of records to return
            
        Returns:
            List of API activity records
        """
        query = """
            SELECT activity_id, api_endpoint, http_method, response_status, 
                   response_time_ms, user_id, ip_address, user_agent, timestamp
            FROM dashboard_api_activity 
            WHERE user_id = :user_id
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"user_id": user_id, "limit": limit})
    
    def get_recent_activity(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent API activity.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent API activity records
        """
        query = """
            SELECT activity_id, api_endpoint, http_method, response_status, 
                   response_time_ms, user_id, ip_address, user_agent, timestamp
            FROM dashboard_api_activity 
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_api_statistics(self) -> Dict[str, Any]:
        """
        Get API activity statistics.
        
        Returns:
            Dictionary with API statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_requests,
                COUNT(CASE WHEN response_status >= 200 AND response_status < 300 THEN 1 END) as successful_requests,
                COUNT(CASE WHEN response_status >= 400 AND response_status < 500 THEN 1 END) as client_errors,
                COUNT(CASE WHEN response_status >= 500 THEN 1 END) as server_errors,
                AVG(response_time_ms) as avg_response_time_ms,
                MIN(response_time_ms) as min_response_time_ms,
                MAX(response_time_ms) as max_response_time_ms
            FROM dashboard_api_activity
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}
    
    def get_endpoint_statistics(self) -> List[Dict[str, Any]]:
        """
        Get API activity statistics by endpoint.
        
        Returns:
            List of endpoint statistics
        """
        query = """
            SELECT 
                api_endpoint,
                COUNT(*) as request_count,
                AVG(response_time_ms) as avg_response_time_ms,
                MIN(response_time_ms) as min_response_time_ms,
                MAX(response_time_ms) as max_response_time_ms,
                COUNT(CASE WHEN response_status >= 200 AND response_status < 300 THEN 1 END) as successful_requests,
                COUNT(CASE WHEN response_status >= 400 AND response_status < 500 THEN 1 END) as client_errors,
                COUNT(CASE WHEN response_status >= 500 THEN 1 END) as server_errors
            FROM dashboard_api_activity
            GROUP BY api_endpoint
            ORDER BY request_count DESC
        """
        
        return self._execute_query(query)