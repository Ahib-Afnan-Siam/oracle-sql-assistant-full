"""
Token usage logger for detailed cost tracking and monitoring.
"""
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Create a dedicated logger for token tracking
logger = logging.getLogger("token_tracker")
logger.setLevel(logging.INFO)

# Create file handler for token tracking logs
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

file_handler = logging.FileHandler(log_dir / "token_usage.log")
file_handler.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s | %(name)s | %(levelname)s | %(message)s'
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

class TokenUsageLogger:
    """Detailed token usage logger for cost monitoring and analysis."""
    
    def __init__(self):
        self.log_file = log_dir / "token_usage_detailed.log"
        self.daily_summary = {}
        
    def log_token_usage(self, module: str, model: str, usage: Dict[str, int], request_content: Optional[str] = None):
        """
        Log detailed token usage information.
        
        Args:
            module: Module name (SOS, ERP, etc.)
            model: Model name used
            usage: Token usage dictionary with prompt_tokens, completion_tokens, total_tokens
            request_content: Optional request content for context (first 100 chars)
        """
        timestamp = datetime.now().isoformat()
        
        # Create detailed log entry
        log_entry = {
            "timestamp": timestamp,
            "module": module,
            "model": model,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "request_preview": request_content[:100] if request_content else None
        }
        
        # Log to dedicated logger
        logger.info(
            f"TOKEN_USAGE | Module: {module} | Model: {model} | "
            f"Prompt: {usage.get('prompt_tokens', 0)} | "
            f"Completion: {usage.get('completion_tokens', 0)} | "
            f"Total: {usage.get('total_tokens', 0)}"
        )
        
        # Write detailed entry to file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write detailed token log: {e}")
        
        # Update daily summary
        today = datetime.now().date().isoformat()
        if today not in self.daily_summary:
            self.daily_summary[today] = {
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_requests": 0,
                "modules": {}
            }
        
        day_summary = self.daily_summary[today]
        day_summary["total_prompt_tokens"] += usage.get("prompt_tokens", 0)
        day_summary["total_completion_tokens"] += usage.get("completion_tokens", 0)
        day_summary["total_requests"] += 1
        
        if module not in day_summary["modules"]:
            day_summary["modules"][module] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "requests": 0
            }
        
        module_summary = day_summary["modules"][module]
        module_summary["prompt_tokens"] += usage.get("prompt_tokens", 0)
        module_summary["completion_tokens"] += usage.get("completion_tokens", 0)
        module_summary["requests"] += 1
    
    def get_daily_summary(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get daily token usage summary.
        
        Args:
            date: Date in ISO format (YYYY-MM-DD). If None, uses today.
            
        Returns:
            Daily summary dictionary
        """
        if date is None:
            date = datetime.now().date().isoformat()
        
        return self.daily_summary.get(date, {})
    
    def calculate_daily_cost(self, date: Optional[str] = None, pricing: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """
        Calculate estimated cost for a day.
        
        Args:
            date: Date in ISO format (YYYY-MM-DD). If None, uses today.
            pricing: Dictionary with pricing information
            
        Returns:
            Cost breakdown dictionary
        """
        if pricing is None:
            pricing = {
                "prompt_token_cost": 0.0000001,
                "completion_token_cost": 0.0000002
            }
        
        summary = self.get_daily_summary(date)
        prompt_tokens = summary.get("total_prompt_tokens", 0)
        completion_tokens = summary.get("total_completion_tokens", 0)
        
        prompt_cost = prompt_tokens * pricing["prompt_token_cost"]
        completion_cost = completion_tokens * pricing["completion_token_cost"]
        total_cost = prompt_cost + completion_cost
        
        return {
            "prompt_tokens": float(prompt_tokens),
            "completion_tokens": float(completion_tokens),
            "prompt_cost": float(prompt_cost),
            "completion_cost": float(completion_cost),
            "total_cost": float(total_cost),
            "pricing": pricing or {}
        }

# Global instance
token_logger = TokenUsageLogger()

def get_token_logger() -> TokenUsageLogger:
    """Get the global token logger instance."""
    return token_logger