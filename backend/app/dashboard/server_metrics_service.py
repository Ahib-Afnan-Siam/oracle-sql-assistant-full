"""
Service module for dashboard_server_metrics table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class ServerMetricsService(BaseService):
    """Service class for server metrics-related database operations."""
    
    def record_metric(self, metric_name: str, metric_value: float, 
                     metric_unit: Optional[str] = None) -> Optional[int]:
        """
        Record a server metric.
        
        Args:
            metric_name: Name of the metric
            metric_value: Value of the metric
            metric_unit: Unit of the metric
            
        Returns:
            Metric ID of the newly created record or None
        """
        insert_query = """
            INSERT INTO dashboard_server_metrics 
            (metric_name, metric_value, metric_unit, recorded_at)
            VALUES (:metric_name, :metric_value, :metric_unit, CURRENT_TIMESTAMP)
        """
        
        params = {
            "metric_name": metric_name,
            "metric_value": metric_value,
            "metric_unit": metric_unit
        }
        
        self._execute_non_query(insert_query, params)
        
        # Get the ID of the newly inserted record
        # Use ROWNUM to get the most recently inserted record for this metric name
        select_query = """
            SELECT metric_id FROM (
                SELECT metric_id FROM dashboard_server_metrics 
                WHERE metric_name = :metric_name
                ORDER BY recorded_at DESC, metric_id DESC
            ) WHERE ROWNUM = 1
        """
        
        result = self._execute_query(select_query, {"metric_name": metric_name})
        return result[0]["metric_id"] if result and len(result) > 0 and "metric_id" in result[0] else None
    
    def get_metrics_by_name(self, metric_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get metrics by name.
        
        Args:
            metric_name: Name of the metric
            limit: Maximum number of records to return
            
        Returns:
            List of metric records
        """
        query = """
            SELECT metric_id, metric_name, metric_value, metric_unit, recorded_at
            FROM dashboard_server_metrics 
            WHERE metric_name = :metric_name
            ORDER BY recorded_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"metric_name": metric_name, "limit": limit})
    
    def get_recent_metrics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent metrics.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent metric records
        """
        query = """
            SELECT metric_id, metric_name, metric_value, metric_unit, recorded_at
            FROM dashboard_server_metrics 
            ORDER BY recorded_at DESC
            FETCH FIRST :limit ROWS ONLY
        """
        
        return self._execute_query(query, {"limit": limit})
    
    def get_metric_statistics(self, metric_name: str) -> Dict[str, Any]:
        """
        Get statistics for a specific metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            Dictionary with metric statistics
        """
        query = """
            SELECT 
                COUNT(*) as count,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value,
                AVG(metric_value) as avg_value,
                STDDEV(metric_value) as stddev_value
            FROM dashboard_server_metrics
            WHERE metric_name = :metric_name
        """
        
        result = self._execute_query(query, {"metric_name": metric_name})
        return result[0] if result and len(result) > 0 else {}