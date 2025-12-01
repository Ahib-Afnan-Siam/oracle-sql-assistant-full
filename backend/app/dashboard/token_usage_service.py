"""
Service module for dashboard_token_usage table operations.
"""
import logging
from typing import Any, Dict, List, Optional
from .base_service import BaseService

logger = logging.getLogger(__name__)

class TokenUsageService(BaseService):
    """Service class for token usage-related database operations."""
    
    def record_token_usage(self, chat_id: int, message_id: Optional[int], model_type: str,
                          model_name: str, prompt_tokens: int, completion_tokens: int,
                          total_tokens: int, cost_usd: float, database_type: Optional[str] = None) -> Optional[int]:
        """
        Record token usage for a message or chat.
        
        Args:
            chat_id: Chat identifier
            message_id: Message identifier (optional)
            model_type: Model type (api or local)
            model_name: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total number of tokens
            cost_usd: Cost in USD
            database_type: Database type (optional)
            
        Returns:
            Usage ID of the newly created record or None
        """
        try:
            insert_query = """
                INSERT INTO dashboard_token_usage 
                (chat_id, message_id, model_type, model_name, prompt_tokens, completion_tokens, 
                 total_tokens, cost_usd, timestamp, database_type)
                VALUES (:chat_id, :message_id, :model_type, :model_name, :prompt_tokens, 
                        :completion_tokens, :total_tokens, :cost_usd, CURRENT_TIMESTAMP, :database_type)
            """
            
            params = {
                "chat_id": chat_id,
                "message_id": message_id,
                "model_type": model_type,
                "model_name": model_name,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
                "database_type": database_type
            }
            
            self._execute_non_query(insert_query, params)
            
            # Get the ID of the newly inserted record
            # Use ROWNUM to get the most recently inserted record for this chat
            select_query = """
                SELECT usage_id FROM (
                    SELECT usage_id FROM dashboard_token_usage 
                    WHERE chat_id = :chat_id 
                    ORDER BY timestamp DESC, usage_id DESC
                ) WHERE ROWNUM = 1
            """
            
            result = self._execute_query(select_query, {"chat_id": chat_id})
            return result[0]["usage_id"] if result and len(result) > 0 and "usage_id" in result[0] else None
        except Exception as e:
            logger.error(f"Error recording token usage for chat {chat_id}: {str(e)}", exc_info=True)
            return None
    
    def get_token_usage_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get token usage records for a chat.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            List of token usage records
        """
        query = """
            SELECT usage_id, chat_id, message_id, model_type, model_name, 
                   prompt_tokens, completion_tokens, total_tokens, cost_usd, timestamp
            FROM dashboard_token_usage 
            WHERE chat_id = :chat_id
            ORDER BY timestamp ASC
        """
        
        return self._execute_query(query, {"chat_id": chat_id})
    
    def get_token_usage_statistics(self) -> Dict[str, Any]:
        """
        Get token usage statistics.
        
        Returns:
            Dictionary with token usage statistics
        """
        query = """
            SELECT 
                COUNT(*) as total_usage_records,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(cost_usd) as total_cost_usd,
                AVG(prompt_tokens) as avg_prompt_tokens,
                AVG(completion_tokens) as avg_completion_tokens,
                AVG(total_tokens) as avg_total_tokens,
                AVG(cost_usd) as avg_cost_usd
            FROM (
                SELECT chat_id, model_type, model_name,
                       MAX(prompt_tokens) as prompt_tokens,
                       MAX(completion_tokens) as completion_tokens,
                       MAX(total_tokens) as total_tokens,
                       MAX(cost_usd) as cost_usd
                FROM dashboard_token_usage
                GROUP BY chat_id, model_type, model_name
            )
        """
        
        result = self._execute_query(query)
        return result[0] if result and len(result) > 0 else {}

    def get_token_usage_by_model(self) -> List[Dict[str, Any]]:
        """
        Get token usage aggregated by model.
        
        Returns:
            List of token usage statistics by model
        """
        query = """
            SELECT 
                model_name,
                model_type,
                COUNT(*) as usage_count,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(cost_usd) as total_cost_usd,
                AVG(prompt_tokens) as avg_prompt_tokens,
                AVG(completion_tokens) as avg_completion_tokens,
                AVG(total_tokens) as avg_total_tokens,
                AVG(cost_usd) as avg_cost_usd
            FROM (
                SELECT chat_id, model_type, model_name,
                       MAX(prompt_tokens) as prompt_tokens,
                       MAX(completion_tokens) as completion_tokens,
                       MAX(total_tokens) as total_tokens,
                       MAX(cost_usd) as cost_usd
                FROM dashboard_token_usage
                GROUP BY chat_id, model_type, model_name
            )
            GROUP BY model_name, model_type
            ORDER BY total_tokens DESC
        """
        
        return self._execute_query(query)

    def get_token_usage_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get token usage data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily token usage data
        """
        query = """
            SELECT 
                usage_date,
                SUM(total_tokens) as total_tokens
            FROM (
                SELECT 
                    TRUNC(timestamp) as usage_date,
                    chat_id,
                    MAX(total_tokens) as total_tokens
                FROM dashboard_token_usage
                WHERE timestamp >= SYSDATE - :days
                GROUP BY TRUNC(timestamp), chat_id
            )
            GROUP BY usage_date
            ORDER BY usage_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_token_cost_over_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get token cost data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of daily token cost data
        """
        query = """
            SELECT 
                usage_date,
                SUM(total_cost) as total_cost
            FROM (
                SELECT 
                    TRUNC(timestamp) as usage_date,
                    chat_id,
                    MAX(cost_usd) as total_cost
                FROM dashboard_token_usage
                WHERE timestamp >= SYSDATE - :days
                GROUP BY TRUNC(timestamp), chat_id
            )
            GROUP BY usage_date
            ORDER BY usage_date
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_hourly_token_usage(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get hourly token usage data over time.
        
        Args:
            days: Number of days to get data for
            
        Returns:
            List of hourly token usage data with cost information
        """
        query = """
            SELECT 
                hour,
                SUM(total_tokens) as total_tokens,
                SUM(total_cost) as total_cost
            FROM (
                SELECT 
                    TRUNC(timestamp, 'HH24') as hour,
                    chat_id,
                    MAX(total_tokens) as total_tokens,
                    MAX(cost_usd) as total_cost
                FROM dashboard_token_usage
                WHERE timestamp >= SYSDATE - :days
                GROUP BY TRUNC(timestamp, 'HH24'), chat_id
            )
            GROUP BY hour
            ORDER BY hour
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_token_usage_forecast(self, days: int = 30, forecast_days: int = 7) -> List[Dict[str, Any]]:
        """
        Get token usage forecast based on historical patterns using simple moving average.
        
        Args:
            days: Number of historical days to use for forecasting
            forecast_days: Number of days to forecast
            
        Returns:
            List of forecasted token usage data
        """
        # Get historical data
        historical_data = self.get_token_usage_over_time(days)
        
        if not historical_data or len(historical_data) < 2:
            return []
        
        # Calculate simple moving average for forecasting
        total_tokens_list = [item["total_tokens"] for item in historical_data]
        avg_tokens = sum(total_tokens_list) / len(total_tokens_list)
        
        # Simple forecast: use average as the forecasted value
        # In a more advanced implementation, we could use linear regression or other methods
        forecast_data = []
        last_date = historical_data[-1]["usage_date"]
        
        from datetime import datetime, timedelta
        current_date = last_date + timedelta(days=1)
        
        for i in range(forecast_days):
            forecast_data.append({
                "usage_date": current_date,
                "total_tokens": int(avg_tokens),
                "forecast": True
            })
            current_date += timedelta(days=1)
        
        return forecast_data
    
    def get_cost_forecast(self, days: int = 30, forecast_days: int = 7) -> List[Dict[str, Any]]:
        """
        Get cost forecast based on historical patterns using simple moving average.
        
        Args:
            days: Number of historical days to use for forecasting
            forecast_days: Number of days to forecast
            
        Returns:
            List of forecasted cost data
        """
        # Get historical data
        historical_data = self.get_token_cost_over_time(days)
        
        if not historical_data or len(historical_data) < 2:
            return []
        
        # Calculate simple moving average for forecasting
        total_cost_list = [item["total_cost"] for item in historical_data]
        avg_cost = sum(total_cost_list) / len(total_cost_list)
        
        # Simple forecast: use average as the forecasted value
        forecast_data = []
        last_date = historical_data[-1]["usage_date"]
        
        from datetime import datetime, timedelta
        current_date = last_date + timedelta(days=1)
        
        for i in range(forecast_days):
            forecast_data.append({
                "usage_date": current_date,
                "total_cost": round(avg_cost, 6),
                "forecast": True
            })
            current_date += timedelta(days=1)
        
        return forecast_data
    
    def get_token_usage_by_model_and_date_range(self, start_date: str, end_date: str, 
                                               model_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get token usage by model and date range for filtering capabilities.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            model_name: Optional model name to filter by
            
        Returns:
            List of token usage records
        """
        query = """
            SELECT 
                model_name,
                model_type,
                usage_date,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(total_cost) as total_cost,
                COUNT(*) as usage_count
            FROM (
                SELECT 
                    model_name,
                    model_type,
                    TRUNC(timestamp) as usage_date,
                    chat_id,
                    MAX(prompt_tokens) as prompt_tokens,
                    MAX(completion_tokens) as completion_tokens,
                    MAX(total_tokens) as total_tokens,
                    MAX(cost_usd) as total_cost
                FROM dashboard_token_usage
                WHERE timestamp >= TO_DATE(:start_date, 'YYYY-MM-DD')
                AND timestamp <= TO_DATE(:end_date, 'YYYY-MM-DD') + 1
                GROUP BY model_name, model_type, TRUNC(timestamp), chat_id
            )
        """
        
        params = {
            "start_date": start_date,
            "end_date": end_date
        }
        
        if model_name:
            query += " AND model_name = :model_name"
            params["model_name"] = model_name
        
        query += """
            GROUP BY model_name, model_type, TRUNC(timestamp)
            ORDER BY usage_date, model_name
        """
        
        return self._execute_query(query, params)
    
    def get_hourly_token_usage_by_session(self, session_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get hourly token usage for a specific user session.
        
        Args:
            session_id: User session identifier
            days: Number of days to get data for
            
        Returns:
            List of hourly token usage data for the session
        """
        # First get the chat_ids for this session
        chat_query = """
            SELECT chat_id FROM dashboard_chats WHERE session_id = :session_id
        """
        chat_results = self._execute_query(chat_query, {"session_id": session_id})
        
        if not chat_results:
            return []
        
        chat_ids = [str(chat["chat_id"]) for chat in chat_results]
        chat_ids_str = ",".join(chat_ids)
        
        query = f"""
            SELECT 
                hour,
                SUM(total_tokens) as total_tokens,
                SUM(total_cost) as total_cost
            FROM (
                SELECT 
                    TRUNC(timestamp, 'HH24') as hour,
                    chat_id,
                    MAX(total_tokens) as total_tokens,
                    MAX(cost_usd) as total_cost
                FROM dashboard_token_usage
                WHERE chat_id IN ({chat_ids_str})
                AND timestamp >= SYSDATE - :days
                GROUP BY TRUNC(timestamp, 'HH24'), chat_id
            )
            GROUP BY hour
            ORDER BY hour
        """
        
        results = self._execute_query(query, {"days": days})
        return results if results else []

    def get_pricing_configuration(self) -> Dict[str, float]:
        """
        Get current pricing configuration for cost estimation.
        
        Returns:
            Dictionary with pricing configuration
        """
        # In a production system, this would be stored in a database table
        # For now, we'll return default pricing values
        return {
            "prompt_token_cost": 0.0000001,      # Cost per prompt token
            "completion_token_cost": 0.0000002,  # Cost per completion token
            "deepseek_chat_cost": 0.0001,        # Cost per request for deepseek-chat
            "llama3_cost": 0.00005               # Cost per request for llama3
        }
    
    def update_pricing_configuration(self, pricing_config: Dict[str, float]) -> bool:
        """
        Update pricing configuration for cost estimation.
        
        Args:
            pricing_config: Dictionary with new pricing values
            
        Returns:
            True if update successful, False otherwise
        """
        # In a production system, this would update a database table
        # For now, we'll just log the update and return True
        logger.info(f"Updating pricing configuration: {pricing_config}")
        return True
    
    def calculate_cost_from_tokens(self, prompt_tokens: int, completion_tokens: int, 
                                 model_name: Optional[str] = None) -> float:
        """
        Calculate cost based on token usage and model.
        
        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            model_name: Name of the model used (optional)
            
        Returns:
            Estimated cost in USD
        """
        pricing = self.get_pricing_configuration()
        
        # Calculate cost based on token usage
        prompt_cost = prompt_tokens * pricing["prompt_token_cost"]
        completion_cost = completion_tokens * pricing["completion_token_cost"]
        
        # Add model-specific cost if provided
        model_cost = 0.0
        if model_name:
            if "deepseek" in model_name.lower():
                model_cost = pricing["deepseek_chat_cost"]
            elif "llama" in model_name.lower():
                model_cost = pricing["llama3_cost"]
        
        total_cost = prompt_cost + completion_cost + model_cost
        return round(total_cost, 6)