"""
Service module for dashboard_error_logs table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class ErrorLogsService(BaseService):
    """Service class for error logs-related database operations."""
    
    def log_error(self, error_type: str, error_message: str, severity: str,
                 component: str, user_id: Optional[str] = None, 
                 chat_id: Optional[int] = None, error_details: Optional[str] = None) -> Optional[int]:
        """
        Log an error.
        
        Args:
            error_type: Type of error
            error_message: Error message
            severity: Severity level (low, medium, high, critical)
            component: Component where error occurred
            user_id: User identifier (optional)
            chat_id: Chat identifier (optional)
            error_details: Additional error details (optional)
            
        Returns:
            Error ID of the newly created record or None
        """
        insert_query = """
            INSERT INTO dashboard_error_logs 
            (error_type, error_message, error_details, severity, component, user_id, chat_id, timestamp)
            VALUES (:error_type, :error_message, :error_details, :severity, :component, :user_id, :chat_id, CURRENT_TIMESTAMP)
        """
        
        params = {
            "error_type": error_type,
            "error_message": error_message,
            "error_details": error_details,
            "severity": severity,
            "component": component,
            "user_id": user_id,
            "chat_id": chat_id
        }
        
        self._execute_non_query(insert_query, params)
        
        # Get the ID of the newly inserted record
        # Use ROWNUM to get the most recently inserted record for this error type
        select_query = """
            SELECT error_id FROM (
                SELECT error_id FROM dashboard_error_logs 
                WHERE error_type = :error_type
                ORDER BY timestamp DESC, error_id DESC
            ) WHERE ROWNUM = 1
        """
        
        result = self._execute_query(select_query, {"error_type": error_type})
        return result[0]["error_id"] if result and len(result) > 0 and "error_id" in result[0] else None
    
    def get_errors_by_type(self, error_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get errors by type.
        
        Args:
            error_type: Type of error
            limit: Maximum number of records to return
            
        Returns:
            List of error records
        """
        query = """
            SELECT error_id, error_type, error_message, error_details, severity, 
                   component, user_id, chat_id, timestamp
            FROM dashboard_error_logs 
            WHERE error_type = :error_type
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"error_type": error_type, "limit": limit})
    
    def get_errors_by_severity(self, severity: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get errors by severity.
        
        Args:
            severity: Severity level
            limit: Maximum number of records to return
            
        Returns:
            List of error records
        """
        query = """
            SELECT error_id, error_type, error_message, error_details, severity, 
                   component, user_id, chat_id, timestamp
            FROM dashboard_error_logs 
            WHERE severity = :severity
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"severity": severity, "limit": limit})
    
    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent errors.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent error records
        """
        query = """
            SELECT error_id, error_type, error_message, error_details, severity, 
                   component, user_id, chat_id, timestamp
            FROM dashboard_error_logs 
            ORDER BY timestamp DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics.
        
        Returns:
            Dictionary with error statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_errors,
                COUNT(CASE WHEN severity = 'low' THEN 1 END) as low_severity_errors,
                COUNT(CASE WHEN severity = 'medium' THEN 1 END) as medium_severity_errors,
                COUNT(CASE WHEN severity = 'high' THEN 1 END) as high_severity_errors,
                COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_severity_errors,
                COUNT(DISTINCT error_type) as unique_error_types,
                COUNT(DISTINCT component) as affected_components
            FROM dashboard_error_logs
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}