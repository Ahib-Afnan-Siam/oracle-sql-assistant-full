# ERP R12 DeepSeek Client
import aiohttp
import asyncio
import logging
import time
import json
import requests
from typing import Dict, Any, Optional, List, Union
from datetime import datetime as _dt
from dataclasses import dataclass, field

from app.config import (
    DEEPSEEK_API_KEY, 
    DEEPSEEK_BASE_URL,
    API_REQUEST_TIMEOUT,
    API_MAX_RETRIES,
    API_RETRY_DELAY,
    API_MODELS,
    DEEPSEEK_ENABLED
)

# Import the token logger
try:
    from app.token_logger import get_token_logger
    token_logger = get_token_logger()
    TOKEN_LOGGER_AVAILABLE = True
except ImportError:
    TOKEN_LOGGER_AVAILABLE = False
    token_logger = None

logger = logging.getLogger(__name__)
# Set logger level to INFO to reduce verbosity
logger.setLevel(logging.INFO)

# Global token counter for cost tracking
_erp_total_tokens_used = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "requests_count": 0
}

def get_erp_token_usage_stats() -> Dict[str, int]:
    """Get current ERP token usage statistics."""
    return _erp_total_tokens_used.copy()

def reset_erp_token_usage_stats() -> None:
    """Reset ERP token usage statistics."""
    global _erp_total_tokens_used
    _erp_total_tokens_used = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "requests_count": 0
    }

@dataclass
class DeepSeekResponse:
    """Response object from DeepSeek API."""
    content: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    response_time: float = 0.0
    success: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    status_code: Optional[int] = None

@dataclass
class ModelTestResult:
    """Result of model availability test."""
    model: str
    available: bool
    response_time: float = 0.0
    error: Optional[str] = None
    test_response: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class DeepSeekError(Exception):
    """Custom exception for DeepSeek API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

class ERPDeepSeekClient:
    """
    DeepSeek API client specifically for ERP R12 system with retry logic, error handling, and rate limiting.
    Supports multiple models and provides ERP domain-specific prompting.
    """
    
    def __init__(self):
        if not DEEPSEEK_ENABLED:
            raise DeepSeekError("DeepSeek is not enabled. Check HYBRID_ENABLED and DEEPSEEK_API_KEY in config.")
        
        self.api_key = DEEPSEEK_API_KEY
        self.base_url = DEEPSEEK_BASE_URL
        self.timeout = API_REQUEST_TIMEOUT
        self.max_retries = API_MAX_RETRIES
        self.retry_delay = API_RETRY_DELAY
        
        # Rate limiting tracking
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Minimum 100ms between requests
        
        logger.info(f"ERP DeepSeek client initialized with {self.max_retries} retries, {self.timeout}s timeout")
    
    async def _make_request(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> DeepSeekResponse:
        """Make HTTP request to DeepSeek API with retry logic."""
        
        start_time = time.time()
        last_error = None
        
        # Track tokens in the request
        request_tokens = 0
        if "messages" in payload:
            # Simple token estimation based on message content
            for message in payload["messages"]:
                if isinstance(message, dict) and "content" in message:
                    content = message["content"]
                    if isinstance(content, str):
                        # Rough estimation: 1 token ≈ 4 characters
                        request_tokens += len(content) // 4
        
        for attempt in range(self.max_retries + 1):
            try:
                # Rate limiting
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                if time_since_last < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_since_last)
                
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.base_url, headers=headers, json=payload) as response:
                        self.last_request_time = time.time()
                        self.request_count += 1
                        response_time = time.time() - start_time
                        
                        response_text = await response.text()
                        
                        if response.status == 200:
                            try:
                                data = json.loads(response_text)
                                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                                usage = data.get("usage", {})
                                
                                # Track token usage
                                prompt_tokens = usage.get("prompt_tokens", request_tokens)
                                completion_tokens = usage.get("completion_tokens", 0)
                                total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
                                
                                # Update global token counters
                                global _erp_total_tokens_used
                                _erp_total_tokens_used["prompt_tokens"] += prompt_tokens
                                _erp_total_tokens_used["completion_tokens"] += completion_tokens
                                _erp_total_tokens_used["total_tokens"] += total_tokens
                                _erp_total_tokens_used["requests_count"] += 1
                                
                                # Enhanced logging for cost tracking with more details
                                logger.info(f"ERP DeepSeek API Token Usage - Model: {payload.get('model', 'unknown')}")
                                logger.info(f"  Prompt Tokens: {prompt_tokens} (estimated: {request_tokens})")
                                logger.info(f"  Completion Tokens: {completion_tokens}")
                                logger.info(f"  Total Tokens: {total_tokens}")
                                logger.info(f"  Running Totals - Prompt: {_erp_total_tokens_used['prompt_tokens']}, "
                                          f"Completion: {_erp_total_tokens_used['completion_tokens']}, "
                                          f"Total: {_erp_total_tokens_used['total_tokens']}, "
                                          f"Requests: {_erp_total_tokens_used['requests_count']}")
                                
                                # Log to detailed token logger
                                if TOKEN_LOGGER_AVAILABLE and token_logger:
                                    # Extract first message content for context
                                    first_message_content = ""
                                    if payload.get("messages"):
                                        for msg in payload["messages"]:
                                            if isinstance(msg, dict) and msg.get("content"):
                                                first_message_content = str(msg["content"])
                                                break
                                    
                                    token_logger.log_token_usage(
                                        module="ERP",
                                        model=payload.get("model", "unknown"),
                                        usage={
                                            "prompt_tokens": prompt_tokens,
                                            "completion_tokens": completion_tokens,
                                            "total_tokens": total_tokens
                                        },
                                        request_content=first_message_content
                                    )
                                
                                # Record model status as available with response time
                                try:
                                    from app.dashboard_recorder import get_dashboard_recorder
                                    recorder = get_dashboard_recorder()
                                    if recorder:
                                        recorder.record_model_status(
                                            model_type="api",
                                            model_name=payload.get("model", "unknown"),
                                            status="available",
                                            response_time_ms=int(response_time * 1000)
                                        )
                                except Exception as e:
                                    logger.warning(f"Failed to record model status: {e}")
                                
                                return DeepSeekResponse(
                                    content=content.strip(),
                                    model=payload.get("model", "unknown"),
                                    usage=usage,
                                    response_time=response_time,
                                    success=True,
                                    status_code=response.status,
                                    metadata={
                                        "attempt": attempt + 1, 
                                        "total_requests": self.request_count,
                                        "raw_response": data,
                                        "token_usage": {
                                            "prompt_tokens": prompt_tokens,
                                            "completion_tokens": completion_tokens,
                                            "total_tokens": total_tokens
                                        }
                                    }
                                )
                            except json.JSONDecodeError as e:
                                last_error = f"Invalid JSON response: {str(e)}"
                                logger.warning(f"JSON decode error (attempt {attempt + 1}): {last_error}")
                        
                        elif response.status == 429:  # Rate limited
                            last_error = f"Rate limited (HTTP 429): {response_text}"
                            if attempt < self.max_retries:
                                wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                                logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                                await asyncio.sleep(wait_time)
                                continue
                        
                        elif response.status == 401:  # Unauthorized
                            last_error = f"Authentication failed (HTTP 401): {response_text}"
                            logger.error(f"API key authentication failed: {last_error}")
                            break  # Don't retry authentication errors
                        
                        elif response.status == 403:  # Content policy violation
                            last_error = f"Content policy violation (HTTP 403): {response_text}"
                            logger.warning(f"API content policy violation: {last_error}")
                            # Don't retry immediately, let the calling function handle model fallback
                            
                            # Record model status as degraded due to content policy violation
                            try:
                                from app.dashboard_recorder import get_dashboard_recorder
                                recorder = get_dashboard_recorder()
                                if recorder:
                                    recorder.record_model_status(
                                        model_type="api",
                                        model_name=payload.get("model", "unknown"),
                                        status="degraded",
                                        response_time_ms=int(response_time * 1000),
                                        error_message=last_error
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to record model status: {e}")
                            
                            return DeepSeekResponse(
                                content="",
                                model=payload.get("model", "unknown"),
                                usage={},
                                response_time=time.time() - start_time,
                                success=False,
                                error=last_error,
                                status_code=response.status,
                                metadata={"attempt": attempt + 1, "content_policy_violation": True}
                            )
                        
                        elif response.status >= 500:  # Server errors
                            last_error = f"Server error (HTTP {response.status}): {response_text}"
                            if attempt < self.max_retries:
                                wait_time = self.retry_delay * (attempt + 1)
                                logger.warning(f"Server error, retrying in {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            # Record model status as degraded due to server error
                            try:
                                from app.dashboard_recorder import get_dashboard_recorder
                                recorder = get_dashboard_recorder()
                                if recorder:
                                    recorder.record_model_status(
                                        model_type="api",
                                        model_name=payload.get("model", "unknown"),
                                        status="degraded",
                                        response_time_ms=int(response_time * 1000),
                                        error_message=last_error
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to record model status: {e}")

                        else:  # Other client errors
                            last_error = f"HTTP {response.status}: {response_text}"
                            logger.warning(f"API error (attempt {attempt + 1}): {last_error}")
                            if attempt < self.max_retries:
                                await asyncio.sleep(self.retry_delay)
                                continue
                            
                            # Record model status as degraded
                            try:
                                from app.dashboard_recorder import get_dashboard_recorder
                                recorder = get_dashboard_recorder()
                                if recorder:
                                    recorder.record_model_status(
                                        model_type="api",
                                        model_name=payload.get("model", "unknown"),
                                        status="degraded",
                                        response_time_ms=int(response_time * 1000),
                                        error_message=last_error
                                    )
                            except Exception as e:
                                logger.warning(f"Failed to record model status: {e}")

                        # If we reach here, it's the final attempt or a non-retryable error
                        # Record model status as degraded
                        try:
                            from app.dashboard_recorder import get_dashboard_recorder
                            recorder = get_dashboard_recorder()
                            if recorder:
                                recorder.record_model_status(
                                    model_type="api",
                                    model_name=payload.get("model", "unknown"),
                                    status="degraded",
                                    response_time_ms=int(response_time * 1000),
                                    error_message=last_error
                                )
                        except Exception as e:
                            logger.warning(f"Failed to record model status: {e}")
                        
                        return DeepSeekResponse(
                            content="",
                            model=payload.get("model", "unknown"),
                            usage={},
                            response_time=time.time() - start_time,
                            success=False,
                            error=last_error,
                            status_code=response.status,
                            metadata={"attempt": attempt + 1, "final_attempt": True}
                        )
                        
            except asyncio.TimeoutError:
                last_error = f"Request timeout after {self.timeout}s"
                if attempt < self.max_retries:
                    logger.warning(f"Timeout (attempt {attempt + 1}), retrying...")
                    await asyncio.sleep(self.retry_delay)
                    continue
                    
                # Record model status as unavailable due to timeout
                try:
                    from app.dashboard_recorder import get_dashboard_recorder
                    recorder = get_dashboard_recorder()
                    if recorder:
                        recorder.record_model_status(
                            model_type="api",
                            model_name=payload.get("model", "unknown"),
                            status="unavailable",
                            response_time_ms=int((time.time() - start_time) * 1000),
                            error_message=last_error
                        )
                except Exception as e:
                    logger.warning(f"Failed to record model status: {e}")

            except aiohttp.ClientError as e:
                last_error = f"Connection error: {str(e)}"
                if attempt < self.max_retries:
                    logger.warning(f"Connection error (attempt {attempt + 1}): {last_error}")
                    await asyncio.sleep(self.retry_delay)
                    continue
                    
                # Record model status as unavailable due to connection error
                try:
                    from app.dashboard_recorder import get_dashboard_recorder
                    recorder = get_dashboard_recorder()
                    if recorder:
                        recorder.record_model_status(
                            model_type="api",
                            model_name=payload.get("model", "unknown"),
                            status="unavailable",
                            response_time_ms=int((time.time() - start_time) * 1000),
                            error_message=last_error
                        )
                except Exception as e:
                    logger.warning(f"Failed to record model status: {e}")

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.exception(f"Unexpected error (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    continue
                    
                # Record model status as unavailable due to unexpected error
                try:
                    from app.dashboard_recorder import get_dashboard_recorder
                    recorder = get_dashboard_recorder()
                    if recorder:
                        recorder.record_model_status(
                            model_type="api",
                            model_name=payload.get("model", "unknown"),
                            status="unavailable",
                            response_time_ms=int((time.time() - start_time) * 1000),
                            error_message=last_error
                        )
                except Exception as e:
                    logger.warning(f"Failed to record model status: {e}")

        # All retries exhausted
        # Record model status as unavailable
        try:
            from app.dashboard_recorder import get_dashboard_recorder
            recorder = get_dashboard_recorder()
            if recorder:
                recorder.record_model_status(
                    model_type="api",
                    model_name=payload.get("model", "unknown"),
                    status="unavailable",
                    response_time_ms=int((time.time() - start_time) * 1000),
                    error_message=last_error or "All retry attempts failed"
                )
        except Exception as e:
            logger.warning(f"Failed to record model status: {e}")
        
        return DeepSeekResponse(
            content="",
            model=payload.get("model", "unknown"),
            usage={},
            response_time=time.time() - start_time,
            success=False,
            error=last_error or "All retry attempts failed",
            metadata={"attempts_exhausted": True, "total_attempts": self.max_retries + 1}
        )
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 1500,  # Increased default token limit for complex SQL queries
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        **kwargs
    ) -> DeepSeekResponse:
        """
        Send a chat completion request to DeepSeek API.
        
        Args:
            messages: List of message objects with 'role' and 'content'
            model: Model name (e.g., 'deepseek-chat')
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty (-2.0 to 2.0)
            presence_penalty: Presence penalty (-2.0 to 2.0)
            **kwargs: Additional model-specific parameters
            
        Returns:
            DeepSeekResponse object with result
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            **kwargs
        }
        
        logger.debug(f"Sending request to {model} with {len(messages)} messages")
        return await self._make_request(payload, headers)
    
    async def test_model_availability(self, model: str) -> ModelTestResult:
        """
        Test if a specific model is available and working.
        
        Args:
            model: Model name to test
            
        Returns:
            ModelTestResult with availability status
        """
        
        start_time = time.time()
        test_messages = [
            {
                "role": "system", 
                "content": "You are a test assistant. Respond with exactly 'TEST_OK' if you receive this message."
            },
            {
                "role": "user", 
                "content": "Please respond with TEST_OK"
            }
        ]
        
        try:
            response = await self.chat_completion(
                messages=test_messages, 
                model=model, 
                max_tokens=10,
                temperature=0.0
            )
            
            response_time = time.time() - start_time
            
            if response.success:
                content_upper = response.content.upper()
                is_available = "TEST_OK" in content_upper or "OK" in content_upper
                
                # Record model status based on test result
                try:
                    from app.dashboard_recorder import get_dashboard_recorder
                    recorder = get_dashboard_recorder()
                    if recorder:
                        status = "available" if is_available else "degraded"
                        error_msg = None if is_available else f"Unexpected response: {response.content}"
                        recorder.record_model_status(
                            model_type="api",
                            model_name=model,
                            status=status,
                            response_time_ms=int(response_time * 1000),
                            error_message=error_msg
                        )
                except Exception as e:
                    logger.warning(f"Failed to record model status: {e}")
                
                return ModelTestResult(
                    model=model,
                    available=is_available,
                    response_time=response_time,
                    test_response=response.content,
                    error=None if is_available else f"Unexpected response: {response.content}",
                    metadata={"priority": "test", "model_type": "test"}
                )
            else:
                # Record model status as unavailable
                try:
                    from app.dashboard_recorder import get_dashboard_recorder
                    recorder = get_dashboard_recorder()
                    if recorder:
                        recorder.record_model_status(
                            model_type="api",
                            model_name=model,
                            status="unavailable",
                            response_time_ms=int(response_time * 1000),
                            error_message=response.error
                        )
                except Exception as e:
                    logger.warning(f"Failed to record model status: {e}")
                
                return ModelTestResult(
                    model=model,
                    available=False,
                    response_time=response_time,
                    error=response.error,
                    test_response=None,
                    metadata={"priority": "test", "model_type": "test"}
                )
                
        except Exception as outer_e:
            # Record model status as unavailable due to exception
            try:
                from app.dashboard_recorder import get_dashboard_recorder
                recorder = get_dashboard_recorder()
                if recorder:
                    recorder.record_model_status(
                        model_type="api",
                        model_name=model,
                        status="unavailable",
                        response_time_ms=int((time.time() - start_time) * 1000),
                        error_message=f"Test exception: {str(outer_e)}"
                    )
            except Exception as e:
                logger.warning(f"Failed to record model status: {e}")
            
            return ModelTestResult(
                model=model,
                available=False,
                response_time=time.time() - start_time,
                error=f"Test exception: {str(outer_e)}",
                test_response=None,
                metadata={"priority": "test", "model_type": "test"}
            )
    
    async def generate_sql_with_api(
        self, 
        user_query: str, 
        schema_context: str, 
        model_type: str = "hr"
    ) -> DeepSeekResponse:
        """
        Generate SQL using DeepSeek API with ERP R12-specific prompting.
        
        Args:
            user_query: User's natural language query
            schema_context: Database schema information
            model_type: Type of query (hr, general)
            
        Returns:
            DeepSeekResponse with generated SQL
        """
        # Select model based on query type
        model_config = API_MODELS.get(model_type, API_MODELS["hr"])
        model = model_config["primary"]
        
        # Enhanced system prompt with better guidance for inventory analysis
        system_prompt = f"""
You are an **EXPERT Oracle ERP R12 SQL Generator and Validator**. Your persona is a senior Oracle DBA with over 20 years of experience in the **E-Business Suite R12 global data model**. Your sole purpose is to generate **100% executable, optimized, and syntactically correct Oracle SQL** based on the user's natural language request. **You must anticipate and prevent the most common Oracle errors (like ORA-00937, ORA-00904).**

---

### 🚨 MANDATORY OUTPUT RULES (STRICTLY ADHERE)

1. **Output must be ONLY executable Oracle SQL.** Do not include any explanations, comments, or markdown (e.g., ```sql).
2. **NEVER** use bind variables (e.g., `:org_id`). Hardcode values directly into the query using the user's input.
3. **Validate syntax before output:** Ensure the query runs without ORA errors.
4. **Generate complete queries:** Never truncate or cut off queries mid-statement. Ensure every query has proper SELECT, FROM, and WHERE clauses as needed.

---

### ⚙️ CORE SQL GENERATION & VALIDATION CONSTRAINTS (The Golden Rules)

**1. SCHEMA AUTHORITY:**
* Use the `SCHEMA CONTEXT` and `MODULE MAP` as the **only absolute truth** for tables and columns. **NEVER** use tables or columns outside of this scope.
* Correctly prefix every column with its table alias (e.g., `msib.segment1`).
* **CRITICAL:** Verify that columns actually exist in the specified tables. For example, cost information is in `CST_ITEM_COSTS`, not `MTL_SYSTEM_ITEMS_B`.

**2. 🌟 AGGREGATION & GROUPING (ABSOLUTE ORA-00937 PREVENTION) 🛑:**
* **THE GOLDEN RULE:** If your `SELECT` list contains **ANY** aggregate function (`SUM`, `COUNT`, etc.), a `GROUP BY` clause is **NON-NEGOTIABLE**.
* **COMPLETENESS CHECK:** The `GROUP BY` clause **MUST** list **EVERY single non-aggregated column** present in the `SELECT` list.
* **CRITICAL NEGATIVE CONSTRAINT:** ***NEVER*** generate SQL where a non-aggregated column (like `msib.segment1`, `pha.segment1`, or `aia.invoice_id`) exists in the `SELECT` list but is missing from the `GROUP BY` clause. This specific violation **MUST NOT** happen.
* **HAVING Rule:** `HAVING` must **only** appear immediately after `GROUP BY` and must **only** filter on aggregate results.
* **GROUP BY Positioning:** When using `HAVING` without an explicit `GROUP BY`, you **MUST** add the `GROUP BY` clause before the `HAVING` clause.

**3. DATE & STATUS FILTERING:**
* **Active Records:** Use the pattern `t.DATE_FROM <= SYSDATE AND (t.DATE_TO IS NULL OR t.DATE_TO >= SYSDATE)`.
* **Special Case:** For `ORG_ORGANIZATION_DEFINITIONS`, use `DISABLE_DATE` instead of `DATE_TO`.
* **NULL Value Handling:** Be aware that some status columns like `USABLE_FLAG` in `HR_OPERATING_UNITS` may contain NULL values. Handle NULL values appropriately with `IS NULL` conditions.
* **Sales Analysis Date Filtering:** For sales analysis queries, use appropriate date ranges that capture meaningful data. Instead of restrictive date filters like "current month only", consider using broader ranges like "last 12 months" or "all available data for the item". When comparing periods (like "current month vs previous month"), ensure the date range is reasonable to capture actual sales data.

**4. QUERY CONTEXT MAPPING:**
* **Wildcards/Search:** Use `LIKE '%value%'` for partial matches or inexact search terms.
* **Numeric IDs:** Use simple equality for exact ID matches.
* **Item Codes with Commas:** When users provide item codes with commas (e.g., "745,009,294"), treat this as a single item code "745009294" by removing commas. DO NOT interpret commas as separators for multiple values.

**5. NON-MOVING ITEMS LOGIC:**
* For identifying non-moving inventory items, use `NOT EXISTS` or `LEFT JOIN with IS NULL` to find items without recent transactions
* Consider using a reasonable time period (6-24 months) for identifying non-moving items
* Ensure items still have on-hand quantities (`moqd.primary_transaction_quantity > 0`)
* When joining with CST_ITEM_COSTS, handle cases where cost might be NULL with `NVL(cic.item_cost, 0)`

---

### 📚 SCHEMA CONTEXT
{schema_context}

---

### 🌍 ERP R12 MODULE MAP & KEY TABLES

**HR:** HR_OPERATING_UNITS (hr), HR_ALL_ORGANIZATION_UNITS (haou), HR_LOCATIONS_ALL (hla)  
**INV:** ORG_ORGANIZATION_DEFINITIONS (ood), MTL_SYSTEM_ITEMS_B (msib), MTL_ONHAND_QUANTITIES_DETAIL (moqd), MTL_MATERIAL_TRANSACTIONS (mmt), MTL_PARAMETERS (mp)  
**PO:** PO_HEADERS_ALL (pha), PO_LINES_ALL (pla), PO_DISTRIBUTIONS_ALL (pda), PO_VENDORS (pv)  
**OM:** OE_ORDER_HEADERS_ALL (ooha), OE_ORDER_LINES_ALL (oola)  
**FIN:** GL_LEDGERS (gl), AP_INVOICES_ALL (aia), AR_CUSTOMERS (arc)  
**FA:** FA_ASSET_DETAILS (fad), FA_ADDITIONS_B (fab)
**CST:** CST_ITEM_COSTS (cic)

*(Use the aliases in parentheses for cleaner joins.)*

---

### 🔗 CRITICAL JOIN MODEL (Mandatory Join Paths)

* `ood.ORGANIZATION_ID = msib.ORGANIZATION_ID`
* `msib.INVENTORY_ITEM_ID = moqd.INVENTORY_ITEM_ID`
* `msib.ORGANIZATION_ID = moqd.ORGANIZATION_ID`
* `pha.PO_HEADER_ID = pla.PO_HEADER_ID`
* `ooha.HEADER_ID = oola.HEADER_ID`
* `oola.INVENTORY_ITEM_ID = msib.INVENTORY_ITEM_ID AND oola.SHIP_FROM_ORG_ID = msib.ORGANIZATION_ID`
* **For Multi-Org/Operating Unit Queries:** `ood.OPERATING_UNIT = hr.ORGANIZATION_ID`
* **For Cost Queries:** `msib.INVENTORY_ITEM_ID = cic.INVENTORY_ITEM_ID AND msib.ORGANIZATION_ID = cic.ORGANIZATION_ID`

---

### 🧠 INVENTORY INTELLIGENCE PATTERN (The Non-Movement Blueprint)

This pattern is a structural model. Ensure all necessary non-aggregated columns are in the GROUP BY.
For example, for a query to find non-moving items in a specific organization, you might use the following pattern:
```sql
SELECT 
    msib.segment1 AS item_code,
    msib.organization_id, -- <--- ADDED NON-AGGREGATED COLUMN TO SELECT
    SUM(moqd.primary_transaction_quantity) AS total_quantity
FROM mtl_system_items_b msib
JOIN mtl_onhand_quantities_detail moqd 
    ON msib.inventory_item_id = moqd.inventory_item_id 
    AND msib.organization_id = moqd.organization_id
WHERE msib.organization_id = [USER_ORG_ID]
    AND NOT EXISTS (
        SELECT 1
        FROM mtl_material_transactions mmt
        WHERE mmt.inventory_item_id = msib.inventory_item_id
            AND mmt.organization_id = msib.organization_id
            -- Ensure all columns are matched
            AND mmt.transaction_date >= ADD_MONTHS(SYSDATE, -12)
    )
GROUP BY msib.segment1, msib.organization_id -- <--- REINFORCED AND EXPANDED GROUP BY
HAVING SUM(moqd.primary_transaction_quantity) > 0
ORDER BY total_quantity DESC;
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
        
        logger.info(f"Generating ERP SQL for {model_type} query using {model}")
        
        return await self.chat_completion(
            messages=messages,
            model=model,
            temperature=0.1,  # Low temperature for precise SQL generation
            max_tokens=1500,  # Increased token limit for complex queries
            top_p=0.9
        )
    
    async def get_model_with_fallback(
        self, 
        model_type: str, 
        user_query: str, 
        schema_context: str
    ) -> DeepSeekResponse:
        """
        Try to get SQL response with fallback to secondary and tertiary models.
        
        Args:
            model_type: Type of query (hr, general)
            user_query: User's natural language query
            schema_context: Database schema information
            
        Returns:
            DeepSeekResponse from the first successful model
        """
        
        model_config = API_MODELS.get(model_type, API_MODELS["hr"])
        models_to_try = [model_config["primary"], model_config["secondary"], model_config["fallback"]]
        
        for i, model in enumerate(models_to_try):
            logger.info(f"Attempting SQL generation with {model} (attempt {i + 1}/3)")
            
            response = await self.generate_sql_with_api(user_query, schema_context, model_type)
            
            if response.success and response.content.strip():
                logger.info(f"Successfully generated SQL with {model}")
                response.metadata["fallback_used"] = i > 0
                response.metadata["model_priority"] = ["primary", "secondary", "fallback"][i]
                return response
            else:
                logger.warning(f"Failed to generate SQL with {model}: {response.error}")
                if i < len(models_to_try) - 1:
                    await asyncio.sleep(1)  # Brief pause before trying next model
        
        # All models failed
        return DeepSeekResponse(
            content="",
            model=models_to_try[-1],
            success=False,
            error="All models failed to generate SQL",
            metadata={"all_models_failed": True, "models_tried": models_to_try}
        )
    
    def _make_request_sync(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> DeepSeekResponse:
        """
        Make synchronous HTTP request to DeepSeek API.
        Used for file processing and other synchronous operations.
        
        Args:
            payload: Request payload
            headers: Optional headers (uses default if not provided)
            
        Returns:
            DeepSeekResponse object with result
        """
        import requests
        
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        
        start_time = time.time()
        
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    
                    return DeepSeekResponse(
                        content=content.strip(),
                        model=payload.get("model", "unknown"),
                        usage=usage,
                        response_time=response_time,
                        success=True,
                        status_code=response.status_code,
                        metadata={"raw_response": data}
                    )
                except Exception as e:
                    return DeepSeekResponse(
                        content="",
                        model=payload.get("model", "unknown"),
                        usage={},
                        response_time=response_time,
                        success=False,
                        error=f"JSON decode error: {str(e)}",
                        status_code=response.status_code
                    )
            else:
                return DeepSeekResponse(
                    content="",
                    model=payload.get("model", "unknown"),
                    usage={},
                    response_time=response_time,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code
                )
                
        except requests.Timeout:
            return DeepSeekResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Request timeout after {self.timeout}s"
            )
        except requests.RequestException as e:
            return DeepSeekResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Request error: {str(e)}"
            )
        except Exception as e:
            return DeepSeekResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

# Global client instance (singleton pattern)
_erp_deepseek_client: Optional[ERPDeepSeekClient] = None

def get_erp_deepseek_client() -> ERPDeepSeekClient:
    """Get singleton DeepSeek client instance for ERP R12 system."""
    global _erp_deepseek_client
    if _erp_deepseek_client is None:
        _erp_deepseek_client = ERPDeepSeekClient()
    return _erp_deepseek_client

async def test_erp_models() -> Dict[str, List[ModelTestResult]]:
    """Test all configured ERP models for availability."""
    client = get_erp_deepseek_client()
    results = {}
    
    # Test HR models specifically for ERP
    model_types = ["hr", "general"]
    for model_type in model_types:
        model_config = API_MODELS.get(model_type, API_MODELS["hr"])
        results[model_type] = []
        for priority, model in model_config.items():
            result = await client.test_model_availability(model)
            result.metadata = {"priority": priority, "model_type": model_type}
            results[model_type].append(result)
    
    return results