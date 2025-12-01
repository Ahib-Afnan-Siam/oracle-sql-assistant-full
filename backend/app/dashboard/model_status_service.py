"""
Service module for dashboard_model_status table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class ModelStatusService(BaseService):
    """Service class for model status-related database operations."""
    
    def update_model_status(self, model_type: str, model_name: str, status: str,
                           response_time_ms: Optional[int] = None, 
                           error_message: Optional[str] = None) -> Optional[int]:
        """
        Update or create model status record.
        
        Args:
            model_type: Model type (api or local)
            model_name: Model name
            status: Model status (available, unavailable, degraded)
            response_time_ms: Response time in milliseconds
            error_message: Error message if any
            
        Returns:
            Status ID of the updated/created record or None
        """
        # First try to update existing record
        update_query = """
            UPDATE dashboard_model_status 
            SET status = :status,
                response_time_ms = :response_time_ms,
                error_message = :error_message,
                last_checked = CURRENT_TIMESTAMP
            WHERE model_type = :model_type AND model_name = :model_name
        """
        
        update_params = {
            "model_type": model_type,
            "model_name": model_name,
            "status": status,
            "response_time_ms": response_time_ms,
            "error_message": error_message
        }
        
        rows_affected = self._execute_non_query(update_query, update_params)
        
        # If no rows were affected, insert a new record
        if rows_affected == 0:
            insert_query = """
                INSERT INTO dashboard_model_status 
                (model_type, model_name, status, response_time_ms, error_message, last_checked)
                VALUES (:model_type, :model_name, :status, :response_time_ms, :error_message, CURRENT_TIMESTAMP)
            """
            
            self._execute_non_query(insert_query, update_params)
        
        # Get the ID of the updated/inserted record
        select_query = """
            SELECT status_id FROM dashboard_model_status 
            WHERE model_type = :model_type AND model_name = :model_name
        """
        
        result = self._execute_query(select_query, {"model_type": model_type, "model_name": model_name})
        return result[0]["status_id"] if result and len(result) > 0 and "status_id" in result[0] else None
    
    def get_model_status(self, model_type: str, model_name: str) -> Optional[Dict[str, Any]]:
        """
        Get model status by type and name.
        
        Args:
            model_type: Model type (api or local)
            model_name: Model name
            
        Returns:
            Model status details or None if not found
        """
        query = """
            SELECT status_id, model_type, model_name, status, response_time_ms, 
                   error_message, last_checked
            FROM dashboard_model_status 
            WHERE model_type = :model_type AND model_name = :model_name
        """
        
        result = self._execute_query(query, {"model_type": model_type, "model_name": model_name})
        return result[0] if result else None
    
    def get_all_model_statuses(self) -> List[Dict[str, Any]]:
        """
        Get status of all models.
        
        Returns:
            List of all model statuses
        """
        query = """
            SELECT status_id, model_type, model_name, status, response_time_ms, 
                   error_message, last_checked
            FROM dashboard_model_status 
            ORDER BY model_type, model_name
        """
        
        return self._execute_query(query)
    
    def get_model_statistics(self) -> Dict[str, Any]:
        """
        Get model status statistics.
        
        Returns:
            Dictionary with model statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_models,
                COUNT(CASE WHEN status = 'available' THEN 1 END) as available_models,
                COUNT(CASE WHEN status = 'unavailable' THEN 1 END) as unavailable_models,
                COUNT(CASE WHEN status = 'degraded' THEN 1 END) as degraded_models,
                AVG(response_time_ms) as avg_response_time_ms
            FROM dashboard_model_status
        """
        
        result = self._execute_query(query)
        return result[0] if result else {}