# backend/app/openrouter_client.py
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
    OPENROUTER_API_KEY, 
    OPENROUTER_BASE_URL,
    API_REQUEST_TIMEOUT,
    API_MAX_RETRIES,
    API_RETRY_DELAY,
    API_MODELS,
    OPENROUTER_ENABLED
)

logger = logging.getLogger(__name__)

@dataclass
class OpenRouterResponse:
    """Response object from OpenRouter API."""
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

class OpenRouterError(Exception):
    """Custom exception for OpenRouter API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

class OpenRouterClient:
    """
    OpenRouter API client with retry logic, error handling, and rate limiting.
    Supports multiple models and provides manufacturing domain-specific prompting.
    """
    
    def __init__(self):
        if not OPENROUTER_ENABLED:
            raise OpenRouterError("OpenRouter is not enabled. Check HYBRID_ENABLED and OPENROUTER_API_KEY in config.")
        
        self.api_key = OPENROUTER_API_KEY
        self.base_url = OPENROUTER_BASE_URL
        self.timeout = API_REQUEST_TIMEOUT
        self.max_retries = API_MAX_RETRIES
        self.retry_delay = API_RETRY_DELAY
        
        # Rate limiting tracking
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Minimum 100ms between requests
        
        logger.info(f"OpenRouter client initialized with {self.max_retries} retries, {self.timeout}s timeout")
    
    async def _make_request(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> OpenRouterResponse:
        """Make HTTP request to OpenRouter API with retry logic."""
        
        start_time = time.time()
        last_error = None
        
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
                                
                                return OpenRouterResponse(
                                    content=content.strip(),
                                    model=payload.get("model", "unknown"),
                                    usage=usage,
                                    response_time=response_time,
                                    success=True,
                                    status_code=response.status,
                                    metadata={
                                        "attempt": attempt + 1, 
                                        "total_requests": self.request_count,
                                        "raw_response": data
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
                        
                        elif response.status >= 500:  # Server errors
                            last_error = f"Server error (HTTP {response.status}): {response_text}"
                            if attempt < self.max_retries:
                                wait_time = self.retry_delay * (attempt + 1)
                                logger.warning(f"Server error, retrying in {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                        
                        else:  # Other client errors
                            last_error = f"HTTP {response.status}: {response_text}"
                            logger.warning(f"API error (attempt {attempt + 1}): {last_error}")
                            if attempt < self.max_retries:
                                await asyncio.sleep(self.retry_delay)
                                continue
                        
                        # If we reach here, it's the final attempt or a non-retryable error
                        return OpenRouterResponse(
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
                    
            except aiohttp.ClientError as e:
                last_error = f"Connection error: {str(e)}"
                if attempt < self.max_retries:
                    logger.warning(f"Connection error (attempt {attempt + 1}): {last_error}")
                    await asyncio.sleep(self.retry_delay)
                    continue
                    
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.exception(f"Unexpected error (attempt {attempt + 1})")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    continue
        
        # All retries exhausted
        return OpenRouterResponse(
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
        model: str = "deepseek/deepseek-chat",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        top_p: float = 0.9,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        **kwargs
    ) -> OpenRouterResponse:
        """
        Send a chat completion request to OpenRouter API.
        
        Args:
            messages: List of message objects with 'role' and 'content'
            model: Model name (e.g., 'deepseek/deepseek-chat')
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            top_p: Nucleus sampling parameter
            frequency_penalty: Frequency penalty (-2.0 to 2.0)
            presence_penalty: Presence penalty (-2.0 to 2.0)
            **kwargs: Additional model-specific parameters
            
        Returns:
            OpenRouterResponse object with result
        """
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8090",
            "X-Title": "Oracle SQL Assistant - Hybrid AI System"
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
                
                return ModelTestResult(
                    model=model,
                    available=is_available,
                    response_time=response_time,
                    test_response=response.content,
                    error=None if is_available else f"Unexpected response: {response.content}"
                )
            else:
                return ModelTestResult(
                    model=model,
                    available=False,
                    response_time=response_time,
                    error=response.error,
                    test_response=None
                )
                
        except Exception as e:
            return ModelTestResult(
                model=model,
                available=False,
                response_time=time.time() - start_time,
                error=f"Test exception: {str(e)}",
                test_response=None
            )
    
    async def get_sql_response(
        self, 
        user_query: str, 
        schema_context: str, 
        model_type: str = "production"
    ) -> OpenRouterResponse:
        """
        Generate SQL response using appropriate model for query type.
        
        Args:
            user_query: User's natural language query
            schema_context: Database schema information
            model_type: Type of query (production, hr, tna, general)
            
        Returns:
            OpenRouterResponse with generated SQL
        """
        
        # Select model based on query type
        model_config = API_MODELS.get(model_type, API_MODELS["general"])
        model = model_config["primary"]
        
        # Manufacturing domain-specific system prompt with comprehensive schema awareness
        system_prompt = f"""You are an expert Oracle SQL assistant for a manufacturing company (Chorka Apparel Limited - CAL, Winner, BIP). 
Generate precise Oracle SQL queries based on user questions and ONLY use tables and columns that exist in the provided schema.

ACTUAL SCHEMA CONTEXT FROM DATABASE:
{schema_context}

CRITICAL RULES - MUST FOLLOW:
1. ONLY use columns that exist in the schema context above
2. NEVER assume column names - validate against schema first
3. NO 'COMPANY' column exists anywhere - use FLOOR_NAME patterns instead
4. For company filtering: Use flexible patterns to match company names within FLOOR_NAME
   - For CAL: UPPER(FLOOR_NAME) LIKE '%CAL%' 
   - For Winner: UPPER(FLOOR_NAME) LIKE '%WINNER%'
   - For BIP: UPPER(FLOOR_NAME) LIKE '%BIP%'
5. Always validate table and column names against the provided schema

VERIFIED TABLE STRUCTURES (use these as reference):
Production Tables:
- T_PROD: PROD_DATE, FLOOR_NAME, PM_OR_APM_NAME, PRODUCTION_QTY, DEFECT_QTY, DHU, FLOOR_EF, DEFECT_PERS, UNCUT_THREAD, DIRTY_STAIN, BROKEN_STITCH, SKIP_STITCH, OPEN_SEAM, LAST_UPDATE
- T_PROD_DAILY: Same as T_PROD plus AC_PRODUCTION_HOUR, AC_WORKING_HOUR

TNA Tables:
- T_TNA_STATUS: JOB_NO, PO_NUMBER_ID, TASK_NUMBER, TASK_FINISH_DATE, ACTUAL_FINISH_DATE, TASK_SHORT_NAME, PO_NUMBER, PO_RECEIVED_DATE, PUB_SHIPMENT_DATE, SHIPMENT_DATE, STYLE_REF_NO, STYLE_DESCRIPTION, BUYER_NAME, TEAM_MEMBER_NAME, TEAM_LEADER_NAME
- V_TNA_STATUS: Similar to T_TNA_STATUS with additional computed fields

Employee Tables:
- EMP: EMPNO, ENAME, JOB, MGR, HIREDATE, SAL, COMM, DEPTNO
- T_USERS: USER_ID, USERNAME, FULL_NAME, PHONE_NUMBER, EMAIL_ADDRESS, IMAGE, IS_ACTIVE, PIN, FILENAME, LAST_UPDATED, ADDED_DATE, UPDATE_DATE, MIME_TYPE, LAST_LOGIN
- DEPT: DEPTNO, DNAME, LOC

Order Tables:
- T_ORDC: BUYER_NAME, STYLEPO, STYLE, JOB, ITEM_NAME, FACTORY, POQTY, CUTQTY, SINPUT, SOUTPUT, SHIPQTY, LEFTQTY, FOBP, SMV, CM, CEFFI, AEFFI, CMER, ACM, EXMAT, SHIPDATE

Master Tables:
- COMPANIES: COMPANY_ID, COMPANY_NAME, COMPANY_ADDRESS, COMPANY_CNCL
- ITEM_MASTER: ITEM_ID, ITEM_CODE, DESCRIPTION, LENGTH_CM, WIDTH_CM, HEIGHT_CM, CBM
- CONTAINER_MASTER: CONTAINER_ID, CONTAINER_TYPE, INNER_LENGTH_CM, INNER_WIDTH_CM, INNER_HEIGHT_CM, MAX_CBM, MAX_WEIGHT_KG

QUERY GENERATION GUIDELINES:
- For floor-wise analysis: GROUP BY FLOOR_NAME
- For production metrics: use PRODUCTION_QTY, DEFECT_QTY, DHU, FLOOR_EF
- For date filtering: use PROD_DATE for production tables, TASK_FINISH_DATE for TNA
- For employee queries: use EMP or T_USERS tables
- For case-insensitive matching: use UPPER() function
- Always include appropriate ORDER BY clauses
- For company name matching in FLOOR_NAME: Use flexible patterns like UPPER(FLOOR_NAME) LIKE '%CAL%' to match company identifiers anywhere in the floor name

COMMON QUERY PATTERNS:
- Floor production: SELECT FLOOR_NAME, SUM(PRODUCTION_QTY) FROM T_PROD_DAILY GROUP BY FLOOR_NAME
- Company filtering: WHERE UPPER(FLOOR_NAME) LIKE '%CAL%' OR UPPER(FLOOR_NAME) LIKE '%WINNER%'
- Employee lookup: SELECT FULL_NAME, EMAIL_ADDRESS FROM T_USERS WHERE UPPER(FULL_NAME) LIKE '%NAME%'
- TNA tasks: SELECT JOB_NO, TASK_SHORT_NAME FROM T_TNA_STATUS WHERE conditions

RESPONSE FORMAT:
- Return ONLY executable Oracle SQL
- No explanations or comments
- Use proper Oracle SQL syntax
- Include column aliases for readability
- Add ORDER BY when appropriate for meaningful results

VALIDATION CHECKLIST:
✓ All table names exist in schema
✓ All column names exist in selected tables  
✓ No assumed or non-existent columns used
✓ Proper Oracle SQL syntax
✓ Appropriate filtering and grouping"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
        
        logger.info(f"Generating SQL for {model_type} query using {model}")
        
        return await self.chat_completion(
            messages=messages, 
            model=model,
            temperature=0.1,  # Low temperature for precise SQL generation
            max_tokens=1024,
            top_p=0.9
        )
    
    async def get_model_with_fallback(
        self, 
        model_type: str, 
        user_query: str, 
        schema_context: str
    ) -> OpenRouterResponse:
        """
        Try to get SQL response with fallback to secondary and tertiary models.
        
        Args:
            model_type: Type of query (production, hr, tna, general)
            user_query: User's natural language query
            schema_context: Database schema information
            
        Returns:
            OpenRouterResponse from the first successful model
        """
        
        model_config = API_MODELS.get(model_type, API_MODELS["general"])
        models_to_try = [model_config["primary"], model_config["secondary"], model_config["fallback"]]
        
        for i, model in enumerate(models_to_try):
            logger.info(f"Attempting SQL generation with {model} (attempt {i + 1}/3)")
            
            response = await self.get_sql_response(user_query, schema_context, model_type)
            
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
        return OpenRouterResponse(
            content="",
            model=models_to_try[-1],
            success=False,
            error="All models failed to generate SQL",
            metadata={"all_models_failed": True, "models_tried": models_to_try}
        )
    
    @staticmethod
    def create_multimodal_message(
        text_content: str,
        file_data: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Create a multimodal message for API transmission.
        
        Args:
            text_content: Text content for the message
            file_data: Optional file data (filename and base64 encoded content)
            
        Returns:
            List of message dictionaries formatted for multimodal API calls
        """
        message_content = [{"type": "text", "text": text_content}]
        
        if file_data:
            message_content.append({
                "type": "file",
                "file": file_data
            })
        
        return [
            {
                "role": "user",
                "content": message_content
            }
        ]
    
    @staticmethod
    def encode_file_for_api(file_path: str) -> Optional[Dict[str, str]]:
        """
        Encode a file for API transmission using base64 encoding.
        
        Args:
            file_path: Path to the file to encode
            
        Returns:
            Dictionary with filename and base64 encoded file data, or None if failed
        """
        import base64
        import os
        
        try:
            if not os.path.exists(file_path):
                return None
                
            # Determine MIME type based on file extension
            mime_types = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.txt': 'text/plain',
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif'
            }
            
            file_extension = os.path.splitext(file_path)[1].lower()
            mime_type = mime_types.get(file_extension, 'application/octet-stream')
            
            # Read and encode file
            with open(file_path, "rb") as f:
                file_content = f.read()
                file_base64 = base64.b64encode(file_content).decode('utf-8')
                
            # Create data URL
            data_url = f"data:{mime_type};base64,{file_base64}"
            
            return {
                "filename": os.path.basename(file_path),
                "file_data": data_url
            }
            
        except Exception as e:
            logger.error(f"Failed to encode file {file_path}: {e}")
            return None
    
    def _make_request_sync(
        self,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None
    ) -> OpenRouterResponse:
        """
        Make synchronous HTTP request to OpenRouter API.
        Used for file processing and other synchronous operations.
        
        Args:
            payload: Request payload
            headers: Optional headers (uses default if not provided)
            
        Returns:
            OpenRouterResponse object with result
        """
        import requests
        
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8090",
                "X-Title": "Oracle SQL Assistant - Hybrid AI System"
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
                    
                    return OpenRouterResponse(
                        content=content.strip(),
                        model=payload.get("model", "unknown"),
                        usage=usage,
                        response_time=response_time,
                        success=True,
                        status_code=response.status_code,
                        metadata={"raw_response": data}
                    )
                except Exception as e:
                    return OpenRouterResponse(
                        content="",
                        model=payload.get("model", "unknown"),
                        usage={},
                        response_time=response_time,
                        success=False,
                        error=f"JSON decode error: {str(e)}",
                        status_code=response.status_code
                    )
            else:
                return OpenRouterResponse(
                    content="",
                    model=payload.get("model", "unknown"),
                    usage={},
                    response_time=response_time,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code
                )
                
        except requests.Timeout:
            return OpenRouterResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Request timeout after {self.timeout}s"
            )
        except requests.RequestException as e:
            return OpenRouterResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Request error: {str(e)}"
            )
        except Exception as e:
            return OpenRouterResponse(
                content="",
                model=payload.get("model", "unknown"),
                usage={},
                response_time=time.time() - start_time,
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

# Global client instance (singleton pattern)
_openrouter_client: Optional[OpenRouterClient] = None

def get_openrouter_client() -> OpenRouterClient:
    """Get singleton OpenRouter client instance."""
    global _openrouter_client
    if _openrouter_client is None:
        _openrouter_client = OpenRouterClient()
    return _openrouter_client

async def test_all_models() -> Dict[str, List[ModelTestResult]]:
    """Test all configured models for availability."""
    client = get_openrouter_client()
    results = {}
    
    for model_type, models in API_MODELS.items():
        results[model_type] = []
        for priority, model in models.items():
            result = await client.test_model_availability(model)
            result.metadata = {"priority": priority, "model_type": model_type}
            results[model_type].append(result)
    
    return results