"""
Token tracking utility for DeepSeek API usage monitoring and cost calculation.
"""
import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

# Import token tracking functions from both clients
try:
    from .SOS.deepseek_client import get_token_usage_stats as get_sos_token_usage
    SOS_CLIENT_AVAILABLE = True
except ImportError:
    SOS_CLIENT_AVAILABLE = False
    def get_sos_token_usage():
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests_count": 0}

try:
    from .ERP_R12_Test_DB.deepseek_client import get_erp_token_usage_stats as get_erp_token_usage
    ERP_CLIENT_AVAILABLE = True
except ImportError:
    ERP_CLIENT_AVAILABLE = False
    def get_erp_token_usage():
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests_count": 0}

logger = logging.getLogger(__name__)

class TokenTracker:
    """Tracks and reports token usage for cost monitoring."""
    
    def __init__(self):
        self.usage_history = defaultdict(list)  # Store usage by time period
        self.start_time = datetime.now()
        
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current token usage from both clients."""
        sos_usage = get_sos_token_usage() if SOS_CLIENT_AVAILABLE else {}
        erp_usage = get_erp_token_usage() if ERP_CLIENT_AVAILABLE else {}
        
        # Combine usage from both clients
        combined_usage = {
            "sos": sos_usage,
            "erp": erp_usage,
            "total": {
                "prompt_tokens": sos_usage.get("prompt_tokens", 0) + erp_usage.get("prompt_tokens", 0),
                "completion_tokens": sos_usage.get("completion_tokens", 0) + erp_usage.get("completion_tokens", 0),
                "total_tokens": sos_usage.get("total_tokens", 0) + erp_usage.get("total_tokens", 0),
                "requests_count": sos_usage.get("requests_count", 0) + erp_usage.get("requests_count", 0)
            }
        }
        
        # Store in history
        timestamp = datetime.now()
        self.usage_history[timestamp] = combined_usage
        
        return combined_usage
    
    def get_usage_since(self, hours: int = 24) -> Dict[str, Any]:
        """Get token usage for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        period_usage = {
            "sos": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests_count": 0},
            "erp": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests_count": 0},
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "requests_count": 0}
        }
        
        for timestamp, usage in self.usage_history.items():
            if timestamp >= cutoff_time:
                period_usage["sos"]["prompt_tokens"] += usage["sos"].get("prompt_tokens", 0)
                period_usage["sos"]["completion_tokens"] += usage["sos"].get("completion_tokens", 0)
                period_usage["sos"]["total_tokens"] += usage["sos"].get("total_tokens", 0)
                period_usage["sos"]["requests_count"] += usage["sos"].get("requests_count", 0)
                
                period_usage["erp"]["prompt_tokens"] += usage["erp"].get("prompt_tokens", 0)
                period_usage["erp"]["completion_tokens"] += usage["erp"].get("completion_tokens", 0)
                period_usage["erp"]["total_tokens"] += usage["erp"].get("total_tokens", 0)
                period_usage["erp"]["requests_count"] += usage["erp"].get("requests_count", 0)
                
                period_usage["total"]["prompt_tokens"] += (
                    usage["sos"].get("prompt_tokens", 0) + usage["erp"].get("prompt_tokens", 0)
                )
                period_usage["total"]["completion_tokens"] += (
                    usage["sos"].get("completion_tokens", 0) + usage["erp"].get("completion_tokens", 0)
                )
                period_usage["total"]["total_tokens"] += (
                    usage["sos"].get("total_tokens", 0) + usage["erp"].get("total_tokens", 0)
                )
                period_usage["total"]["requests_count"] += (
                    usage["sos"].get("requests_count", 0) + usage["erp"].get("requests_count", 0)
                )
        
        return period_usage
    
    def calculate_cost(self, usage_data: Dict[str, Any], pricing: Dict[str, float] = None) -> Dict[str, float]:
        """
        Calculate estimated cost based on token usage.
        
        Args:
            usage_data: Token usage data from get_current_usage() or get_usage_since()
            pricing: Dictionary with pricing information (default values will be used if not provided)
            
        Returns:
            Dictionary with cost breakdown
        """
        if pricing is None:
            # Default pricing (these should be updated with actual DeepSeek pricing)
            pricing = {
                "prompt_token_cost": 0.0000001,  # Cost per prompt token
                "completion_token_cost": 0.0000002  # Cost per completion token
            }
        
        prompt_cost = usage_data["total"]["prompt_tokens"] * pricing["prompt_token_cost"]
        completion_cost = usage_data["total"]["completion_tokens"] * pricing["completion_token_cost"]
        total_cost = prompt_cost + completion_cost
        
        # Enhanced logging for cost tracking
        logger.info("=== DeepSeek API Cost Calculation ===")
        logger.info(f"Prompt Tokens: {usage_data['total']['prompt_tokens']:,} @ ${pricing['prompt_token_cost']:.7f}/token = ${prompt_cost:.6f}")
        logger.info(f"Completion Tokens: {usage_data['total']['completion_tokens']:,} @ ${pricing['completion_token_cost']:.7f}/token = ${completion_cost:.6f}")
        logger.info(f"Total Estimated Cost: ${total_cost:.6f}")
        
        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": total_cost,
            "pricing_model": pricing
        }
    
    def get_usage_report(self, hours: int = 24) -> str:
        """Generate a formatted usage report."""
        usage = self.get_usage_since(hours)
        cost = self.calculate_cost(usage)
        
        report = f"""
=== DeepSeek API Usage Report (Last {hours} Hours) ===
Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

--- Token Usage ---
SOS Module:
  Prompt Tokens:     {usage['sos']['prompt_tokens']:,}
  Completion Tokens: {usage['sos']['completion_tokens']:,}
  Total Tokens:      {usage['sos']['total_tokens']:,}
  Requests:          {usage['sos']['requests_count']:,}

ERP Module:
  Prompt Tokens:     {usage['erp']['prompt_tokens']:,}
  Completion Tokens: {usage['erp']['completion_tokens']:,}
  Total Tokens:      {usage['erp']['total_tokens']:,}
  Requests:          {usage['erp']['requests_count']:,}

Combined Total:
  Prompt Tokens:     {usage['total']['prompt_tokens']:,}
  Completion Tokens: {usage['total']['completion_tokens']:,}
  Total Tokens:      {usage['total']['total_tokens']:,}
  Requests:          {usage['total']['requests_count']:,}

--- Cost Estimate ---
Prompt Cost:    ${cost['prompt_cost']:.6f}
Completion Cost: ${cost['completion_cost']:.6f}
Total Cost:     ${cost['total_cost']:.6f}

Note: Cost estimates are based on default pricing rates.
Please update pricing information for accurate cost calculations.
"""
        
        # Enhanced logging for the report
        logger.info("=== DeepSeek API Usage Report ===")
        logger.info(f"Time Period: Last {hours} Hours")
        logger.info(f"SOS Tokens: {usage['sos']['total_tokens']:,} in {usage['sos']['requests_count']:,} requests")
        logger.info(f"ERP Tokens: {usage['erp']['total_tokens']:,} in {usage['erp']['requests_count']:,} requests")
        logger.info(f"Total Tokens: {usage['total']['total_tokens']:,} in {usage['total']['requests_count']:,} requests")
        logger.info(f"Estimated Total Cost: ${cost['total_cost']:.6f}")
        
        return report.strip()
    
    def reset_tracking(self) -> None:
        """Reset all token tracking."""
        global SOS_CLIENT_AVAILABLE, ERP_CLIENT_AVAILABLE
        
        # Reset client counters
        if SOS_CLIENT_AVAILABLE:
            try:
                from .SOS.deepseek_client import reset_token_usage_stats
                reset_token_usage_stats()
            except ImportError:
                pass
                
        if ERP_CLIENT_AVAILABLE:
            try:
                from .ERP_R12_Test_DB.deepseek_client import reset_erp_token_usage_stats
                reset_erp_token_usage_stats()
            except ImportError:
                pass
        
        # Reset history
        self.usage_history.clear()
        self.start_time = datetime.now()
        
        logger.info("Token tracking reset completed")

# Global token tracker instance
token_tracker = TokenTracker()

def get_token_tracker() -> TokenTracker:
    """Get the global token tracker instance."""
    return token_tracker

# Convenience functions
def log_current_usage() -> None:
    """Log current token usage."""
    tracker = get_token_tracker()
    usage = tracker.get_current_usage()
    logger.info(f"Current Token Usage - Total: {usage['total']['total_tokens']:,} tokens, "
                f"Requests: {usage['total']['requests_count']:,}")

def get_usage_report(hours: int = 24) -> str:
    """Get formatted usage report."""
    tracker = get_token_tracker()
    return tracker.get_usage_report(hours)

def reset_all_tracking() -> None:
    """Reset all token tracking."""
    tracker = get_token_tracker()
    tracker.reset_tracking()