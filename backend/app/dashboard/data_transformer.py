"""
Data transformation utilities for converting database records to structured JSON responses.
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)

class DataTransformer:
    """Utility class for transforming raw database records into structured JSON responses."""
    
    @staticmethod
    def to_jsonable(value: Any) -> Any:
        """
        Convert a value to a JSON-serializable format.
        
        Args:
            value: Value to convert
            
        Returns:
            JSON-serializable value
        """
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='ignore')
        if isinstance(value, (list, tuple)):
            return [DataTransformer.to_jsonable(item) for item in value]
        if isinstance(value, dict):
            return {key: DataTransformer.to_jsonable(val) for key, val in value.items()}
        return value
    
    @staticmethod
    def transform_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a single database record to JSON-serializable format.
        
        Args:
            record: Database record
            
        Returns:
            Transformed record
        """
        if not record:
            return {}
        
        transformed = {}
        for key, value in record.items():
            transformed[key] = DataTransformer.to_jsonable(value)
        return transformed
    
    @staticmethod
    def transform_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform a list of database records to JSON-serializable format.
        
        Args:
            records: List of database records
            
        Returns:
            List of transformed records
        """
        return [DataTransformer.transform_record(record) for record in records]
    
    @staticmethod
    def format_response(data: Any, message: str = "Operation completed successfully", 
                       success: bool = True) -> Dict[str, Any]:
        """
        Format data into a consistent JSON response structure.
        
        Args:
            data: Data to include in response
            message: Success/error message
            success: Whether the operation was successful
            
        Returns:
            Formatted JSON response
        """
        return {
            "status": "success" if success else "error",
            "data": DataTransformer.to_jsonable(data),
            "message": message
        }
    
    @staticmethod
    def format_error(message: str, error_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Format an error response.
        
        Args:
            message: Error message
            error_code: Error code (optional)
            
        Returns:
            Formatted error response
        """
        response = {
            "status": "error",
            "data": None,
            "message": message
        }
        
        if error_code:
            response["error_code"] = error_code
            
        return response
    
    @staticmethod
    def aggregate_chat_metrics(chats: List[Dict[str, Any]], 
                              messages: List[Dict[str, Any]],
                              token_usage: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate chat-related metrics.
        
        Args:
            chats: List of chat records
            messages: List of message records
            token_usage: List of token usage records
            
        Returns:
            Aggregated chat metrics
        """
        try:
            # Chat statistics
            total_chats = len(chats)
            active_chats = len([c for c in chats if c.get("status") == "active"])
            completed_chats = len([c for c in chats if c.get("status") == "completed"])
            
            # Message statistics
            total_messages = len(messages)
            user_queries = len([m for m in messages if m.get("message_type") == "user_query"])
            ai_responses = len([m for m in messages if m.get("message_type") == "ai_response"])
            
            # Token usage statistics
            total_tokens = sum(tu.get("total_tokens", 0) for tu in token_usage)
            total_cost = sum(tu.get("cost_usd", 0) for tu in token_usage)
            
            return {
                "chats": {
                    "total": total_chats,
                    "active": active_chats,
                    "completed": completed_chats
                },
                "messages": {
                    "total": total_messages,
                    "user_queries": user_queries,
                    "ai_responses": ai_responses
                },
                "token_usage": {
                    "total_tokens": total_tokens,
                    "total_cost": total_cost
                }
            }
        except Exception as e:
            logger.error(f"Error aggregating chat metrics: {str(e)}")
            return {}
    
    @staticmethod
    def aggregate_time_series_data(records: List[Dict[str, Any]], 
                                  timestamp_field: str,
                                  value_field: str,
                                  interval: str = "day") -> List[Dict[str, Any]]:
        """
        Aggregate data into time series format.
        
        Args:
            records: List of records with timestamps
            timestamp_field: Name of timestamp field
            value_field: Name of value field
            interval: Time interval (day, hour, minute)
            
        Returns:
            List of time series data points
        """
        try:
            # Group records by time interval
            grouped = {}
            for record in records:
                timestamp = record.get(timestamp_field)
                value = record.get(value_field, 0)
                
                if not timestamp:
                    continue
                
                # Convert to datetime if it's a string
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                
                # Group by interval
                if interval == "day":
                    key = timestamp.date().isoformat()
                elif interval == "hour":
                    key = timestamp.strftime("%Y-%m-%d %H:00")
                else:  # minute
                    key = timestamp.strftime("%Y-%m-%d %H:%M")
                
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(value)
            
            # Calculate averages for each time period
            time_series = []
            for time_period, values in sorted(grouped.items()):
                time_series.append({
                    "timestamp": time_period,
                    "value": sum(values) / len(values) if values else 0,
                    "count": len(values)
                })
            
            return time_series
        except Exception as e:
            logger.error(f"Error aggregating time series data: {str(e)}")
            return []
    
    @staticmethod
    def normalize_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize metrics for consistent formatting.
        
        Args:
            metrics: Dictionary of metrics
            
        Returns:
            Normalized metrics
        """
        try:
            normalized = {}
            for key, value in metrics.items():
                # Convert to appropriate types
                if isinstance(value, (int, float)):
                    # Format numbers appropriately
                    if isinstance(value, float):
                        normalized[key] = round(value, 2)
                    else:
                        normalized[key] = value
                elif isinstance(value, dict):
                    # Recursively normalize nested dictionaries
                    normalized[key] = DataTransformer.normalize_metrics(value)
                else:
                    normalized[key] = value
            return normalized
        except Exception as e:
            logger.error(f"Error normalizing metrics: {str(e)}")
            return metrics