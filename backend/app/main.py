# app/main.py
"""
Oracle SQL Assistant - Hybrid AI System

This is the main application entry point for the Oracle SQL Assistant with hybrid AI processing.
The system combines local Ollama models with cloud API models (OpenRouter) for optimal SQL generation.

Phase 6: Continuous Learning Loop (Day 15+)

New API Endpoints for Continuous Learning:
- GET /learning/performance-comparison: Compare local vs API model performance by query type
- GET /learning/model-strengths: Identify model strengths by domain/query type
- GET /learning/user-preferences: Analyze user preference patterns for different models
- GET /learning/insights: Get comprehensive learning insights from pattern analysis
- GET /learning/test-system: Test the continuous learning system end-to-end
- GET /learning/test-processor: Test the continuous learning system through the hybrid processor

New API Endpoints for Training Data Preparation (Step 6.2):
- GET /training-data/high-quality-samples: Identify high-quality samples for training data preparation
- GET /training-data/datasets/{type}: Create training datasets for different domains
- GET /training-data/processor/high-quality-samples: Identify high-quality samples through the hybrid processor
- GET /training-data/processor/datasets/{type}: Create training datasets through the hybrid processor

These endpoints provide insights into:
1. Performance Comparison: Local vs API accuracy by query type, response time analysis, user preference patterns
2. Model Strength Identification: DeepSeek strengths (production, TNA, Oracle), Llama strengths (HR, business logic), local model improvement areas
3. Training Data Preparation: High-quality sample identification and training dataset creation

Training Data Preparation Features:
- High-quality sample identification (API responses that outperformed local, successful query-response pairs, domain-specific improvements needed)
- Training dataset creation (Manufacturing query patterns, Oracle SQL best practices, Business logic examples)
"""
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from pathlib import Path
import os
import logging
import time
import json
import csv
import re
import hashlib
import uuid
import asyncio
import threading
from typing import Any, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware

# PDF handling
import PyPDF2

# In-memory storage for token-username mapping (in production, use Redis or database)
token_username_map = {}
token_username_map_lock = threading.Lock()
# Token expiration time (24 hours)
TOKEN_EXPIRATION_TIME = 24 * 60 * 60

# Function to clean up expired tokens
def _cleanup_expired_tokens():
    """Clean up expired tokens from the token-username mapping."""
    try:
        # In this simple implementation, we don't track token creation time
        # In a production system, you would store timestamp with each token
        # and remove tokens older than expiration time
        pass
    except Exception as e:
        logger.warning(f"Error cleaning up expired tokens: {e}")



# Oracle error type (be tolerant to either driver)
try:
    from oracledb import DatabaseError as _OraDatabaseError
    OraDatabaseError = _OraDatabaseError
except ImportError:
    try:
        from cx_Oracle import DatabaseError as _OraDatabaseError
        OraDatabaseError = _OraDatabaseError
    except ImportError:
        class OraDatabaseError(Exception):
            pass

# Import the new AI training recorder
try:
    from app.ai_training_data_recorder import AITrainingDataRecorder
    AI_TRAINING_RECORDER_AVAILABLE = True
except ImportError:
    AI_TRAINING_RECORDER_AVAILABLE = False
    AITrainingDataRecorder = None

# Import datetime for timestamp handling
from datetime import datetime as _dt

# === Use the RAG orchestrator ===
from app.SOS.rag_engine import answer as sos_rag_answer
from app.ERP_R12_Test_DB.rag_engine import answer as erp_rag_answer

# Optional: vector search utility still useful for debugging endpoints if you add any later
from app.SOS.vector_store_chroma import hybrid_schema_value_search  # noqa: F401 (kept for parity)

# Optional feedback DB exports
from app.db_connector import connect_feedback

# Phase 5.2: Import quality metrics system
try:
    from app.ai_training_data_recorder import ai_training_data_recorder
    QUALITY_METRICS_AVAILABLE = True
except ImportError:
    QUALITY_METRICS_AVAILABLE = False

# ---------------------------
# optional: model names (used when inserting samples)
# ---------------------------
try:
    from app.config import OLLAMA_SQL_MODEL, OLLAMA_ANALYTICAL_MODEL, COLLECT_TRAINING_DATA
except Exception:
    OLLAMA_SQL_MODEL = "unknown-sql-model"
    OLLAMA_ANALYTICAL_MODEL = "unknown-summary-model"
    COLLECT_TRAINING_DATA = True

# ---------------------------
# feedback-store helpers (soft import; fallback to no-ops)
# expected signatures:
#   insert_turn(source_db_id, client_ip, user_question, schema_context_text:str|None, schema_context_ids:list[str]|None, meta:dict|None) -> int
#   insert_sql_sample(turn_id:int, model_name:str, prompt_text:str|None, sql_text:str|None, display_mode:str|None=None) -> int
#   update_sql_sample(sql_sample_id:int, **cols)
#   insert_summary_sample(turn_id:int, model_name:str, prompt_text:str|None, data_snapshot:str|None, sql_used:str|None, display_mode:str|None=None) -> int
#   update_summary_sample(summary_sample_id:int, **cols)
#   insert_feedback(...)
# ---------------------------
try:
    # Use the new AI training recorder for feedback storage
    from app.ai_training_data_recorder import ai_training_data_recorder, record_training_query, RecordingContext
    FEEDBACK_STORE_AVAILABLE = True
    
    # Create wrapper functions for the AI training recorder
    def insert_turn(source_db_id, client_ip, user_question, schema_context_text=None, schema_context_ids=None, meta=None):
        """Record a turn in the AI training recorder"""
        try:
            # Extract username from meta if available
            username = meta.get('username') if meta else None
            
            context = RecordingContext(
                session_id=meta.get('session_id') if meta else None,
                client_info=f"{client_ip or ''};{meta.get('user_agent', '') if meta else ''}",
                database_type=source_db_id,
                query_mode=meta.get('processing_mode', 'unknown') if meta else 'unknown',
                username=username
            )
            
            turn_id = ai_training_data_recorder.record_training_query(
                user_query_text=user_question,
                context=context
            )
            return turn_id
        except Exception as e:
            logger.warning(f"Failed to record turn in AI training recorder: {e}")
            return None
    
    def insert_sql_sample(turn_id, model_name, prompt_text=None, sql_text=None, display_mode=None):
        """Record SQL sample in the AI training recorder"""
        try:
            if turn_id:
                model_details = {
                    'model_name': model_name,
                    'response_text': sql_text or '',
                    'prompt_text': prompt_text,
                    'status': 'success',
                    'provider': 'ollama'
                }
                
                sample_id = ai_training_data_recorder.record_model_interaction(
                    query_id=turn_id,
                    model_type='local',
                    model_details=model_details
                )
                return sample_id
        except Exception as e:
            logger.warning(f"Failed to record SQL sample in AI training recorder: {e}")
        return None
    
    def update_sql_sample(sql_sample_id, **cols):
        """Update SQL sample - noop for AI training recorder"""
        # Not implemented for AI training recorder
        return None
    
    def insert_summary_sample(turn_id, model_name, prompt_text=None, data_snapshot=None, sql_used=None, display_mode=None):
        """Record summary sample in the AI training recorder"""
        try:
            if turn_id:
                model_details = {
                    'model_name': model_name,
                    'response_text': data_snapshot or '',
                    'prompt_text': prompt_text,
                    'status': 'success',
                    'provider': 'ollama'
                }
                
                sample_id = ai_training_data_recorder.record_model_interaction(
                    query_id=turn_id,
                    model_type='local',
                    model_details=model_details
                )
                return sample_id
        except Exception as e:
            logger.warning(f"Failed to record summary sample in AI training recorder: {e}")
        return None
    
    def update_summary_sample(summary_sample_id, **cols):
        """Update summary sample - noop for AI training recorder"""
        # Not implemented for AI training recorder
        return None
    
    def insert_feedback(turn_id, task_type, feedback_type, sql_sample_id=None, summary_sample_id=None, improvement_comment=None, labeler_role=None, meta=None):
        """Record feedback in the AI training recorder"""
        try:
            if turn_id:
                # Extract source information from meta if available
                source = meta.get('source', '') if meta else ''
                feedback_details = {
                    'feedback_type': feedback_type,
                    'feedback_score': 5 if feedback_type == 'good' else (1 if feedback_type == 'wrong' else 3),
                    'feedback_comment': improvement_comment,
                    'source': source,
                    'submission_timestamp': _dt.now()
                }
                
                feedback_id = ai_training_data_recorder.record_user_feedback(
                    query_id=turn_id,
                    feedback_details=feedback_details
                )
                return feedback_id
        except Exception as e:
            logger.warning(f"Failed to record feedback in AI training recorder: {e}")
        return None
        
except Exception:
    FEEDBACK_STORE_AVAILABLE = False

    def _noop(*args, **kwargs):
        return None

    insert_turn = _noop
    insert_sql_sample = _noop
    update_sql_sample = _noop
    insert_summary_sample = _noop
    update_summary_sample = _noop
    insert_feedback = _noop

# ---------------------------
# app setup
# ---------------------------
os.environ["ANONYMIZED_TELEMETRY"] = "False"

logger = logging.getLogger(__name__)

def configure_logging():
    level_name = os.getenv("LOG_LEVEL", "INFO")  # Changed default from DEBUG to INFO
    level = getattr(logging, level_name.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    logging.basicConfig(level=level, format=fmt)
    # crank up our package loggers explicitly
    for name in ("app", "app.SOS.rag_engine", "app.SOS.query_engine", "app.ollama_llm", "app.db_connector"):
        logging.getLogger(name).setLevel(level)
    
    # Reduce verbosity of specific modules that generate excessive logs
    logging.getLogger("sentence_transformers.SentenceTransformer").setLevel(logging.WARNING)
    logging.getLogger("tqdm").setLevel(logging.WARNING)
    
    # Adjust logging levels to show important information while reducing noise
    logging.getLogger("app.db_connector").setLevel(logging.WARNING)  # Reduce from INFO to WARNING
    logging.getLogger("app.SOS.hybrid_processor").setLevel(logging.INFO)  # Keep at INFO
    logging.getLogger("app.SOS.deepseek_client").setLevel(logging.INFO)  # Changed from openrouter_client to deepseek_client
    logging.getLogger("app.ERP_R12_Test_DB.deepseek_client").setLevel(logging.INFO)  # Add ERP R12 DeepSeek client logging
    logging.getLogger("app.ai_training_data_recorder").setLevel(logging.WARNING)  # Reduce from INFO to WARNING
    
    # Ensure RAG engine logs are visible
    logging.getLogger("app.SOS.rag_engine").setLevel(logging.INFO)
    logging.getLogger("app.SOS.query_engine").setLevel(logging.INFO)
    
    # Set root logger level to INFO to maintain overall visibility
    logging.getLogger().setLevel(logging.INFO)

# Configure logging
configure_logging()

# File storage configuration
FILE_STORAGE_PATH = Path("uploaded_files")
FILE_STORAGE_PATH.mkdir(exist_ok=True)

# Security configuration
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_FILE_TYPES = {
    'application/pdf': '.pdf',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'text/plain': '.txt',
    'text/csv': '.csv',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif'
}

# Rate limiting configuration
FILE_UPLOAD_LIMIT_PER_USER = 10  # Max uploads per user per hour
PROCESSING_RATE_LIMIT = 5  # Max file processing requests per user per minute
API_QUOTA_LIMIT = 1000  # Max API calls per day

# In-memory storage for rate limiting (in production, use Redis or database)
user_upload_counts = {}  # user_id: count
user_processing_counts = {}  # user_id: count
api_usage_counts = {}  # date: count

def _get_client_identifier(request: Request) -> str:
    """
    Get a unique identifier for the client.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Client identifier string
    """
    # Use client IP and User-Agent for identification
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    return f"{client_ip}:{user_agent}"

def _check_rate_limits(client_id: str) -> Dict[str, bool]:
    """
    Check if client has exceeded rate limits.
    
    Args:
        client_id: Client identifier
        
    Returns:
        Dictionary with rate limit status
    """
    import time
    current_time = time.time()
    
    # Check file upload limit (per hour)
    upload_key = f"{client_id}:{int(current_time // 3600)}"
    upload_count = user_upload_counts.get(upload_key, 0)
    upload_limited = upload_count >= FILE_UPLOAD_LIMIT_PER_USER
    
    # Check processing rate limit (per minute)
    processing_key = f"{client_id}:{int(current_time // 60)}"
    processing_count = user_processing_counts.get(processing_key, 0)
    processing_limited = processing_count >= PROCESSING_RATE_LIMIT
    
    # Check API quota (per day)
    date_key = time.strftime("%Y-%m-%d", time.gmtime(current_time))
    api_count = api_usage_counts.get(date_key, 0)
    api_limited = api_count >= API_QUOTA_LIMIT
    
    return {
        "upload_limited": upload_limited,
        "processing_limited": processing_limited,
        "api_limited": api_limited
    }

def _increment_rate_counters(client_id: str):
    """
    Increment rate limit counters for a client.
    
    Args:
        client_id: Client identifier
    """
    import time
    current_time = time.time()
    
    # Increment upload counter
    upload_key = f"{client_id}:{int(current_time // 3600)}"
    user_upload_counts[upload_key] = user_upload_counts.get(upload_key, 0) + 1
    
    # Increment processing counter
    processing_key = f"{client_id}:{int(current_time // 60)}"
    user_processing_counts[processing_key] = user_processing_counts.get(processing_key, 0) + 1
    
    # Increment API usage counter
    date_key = time.strftime("%Y-%m-%d", time.gmtime(current_time))
    api_usage_counts[date_key] = api_usage_counts.get(date_key, 0) + 1

def _sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    import re
    import os
    # Remove path traversal attempts
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    # Ensure filename doesn't start with dots or slashes
    filename = filename.lstrip('.\\/')
    # Limit filename length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    return filename

def _validate_file_content(file_path: Path) -> bool:
    """
    Validate file content for security purposes.
    
    Args:
        file_path: Path to the file to validate
        
    Returns:
        True if file is safe, False otherwise
    """
    try:
        # Check file size
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
            
        # For text files, check for potentially dangerous content
        text_extensions = {'.txt', '.csv'}
        if file_path.suffix.lower() in text_extensions:
            with open(file_path, 'rb') as f:
                # Read first 4096 bytes to check for dangerous patterns
                content = f.read(4096)
                # Check for common attack patterns
                dangerous_patterns = [
                    b'exec', b'eval', b'import', b'os\\.', b'subprocess', 
                    b'popen', b'system', b'__import__', b'__file__',
                    b'<script', b'javascript:', b'vbscript:', b'onload=',
                    b'onerror=', b'onclick=', b'<iframe', b'<object'
                ]
                content_lower = content.lower()
                for pattern in dangerous_patterns:
                    if pattern in content_lower:
                        logger.warning(f"Dangerous pattern '{pattern}' found in file {file_path}")
                        return False
                        
        # For image files, basic format validation
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif'}
        if file_path.suffix.lower() in image_extensions:
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    img.verify()  # Verify it's a valid image
            except Exception:
                logger.warning(f"Invalid image file: {file_path}")
                return False
                
        # For PDF files, basic validation
        if file_path.suffix.lower() == '.pdf':
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'%PDF':
                        logger.warning(f"Invalid PDF file header: {file_path}")
                        return False
            except Exception:
                logger.warning(f"Cannot read PDF file: {file_path}")
                return False
                
        return True
    except Exception as e:
        logger.error(f"Error validating file content {file_path}: {e}")
        return False

def _cleanup_expired_files():
    """
    Cleanup expired files from storage.
    """
    import time
    try:
        current_time = time.time()
        # Files older than 24 hours will be deleted
        expiry_time = 24 * 60 * 60
        
        for file_path in FILE_STORAGE_PATH.iterdir():
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > expiry_time:
                    file_path.unlink()
                    logger.info(f"Cleaned up expired file: {file_path}")
    except Exception as e:
        logger.error(f"Error during file cleanup: {e}")

def generate_session_id(request: Request) -> Optional[str]:
    """
    Generate a session ID safely without requiring session middleware.
    Uses client IP, user agent, and timestamp to create a unique session identifier.
    """
    try:
        # Try to access session if middleware is available
        if hasattr(request, 'session') and hasattr(request.session, 'get'):
            session_id = request.session.get('id')
            if session_id:
                return session_id
    except (AttributeError, AssertionError):
        # Session middleware not available, generate our own ID
        pass
    
    try:
        # Generate session ID from request characteristics
        client_ip = request.client.host if request and request.client else "unknown"
        user_agent = request.headers.get('user-agent', 'unknown') if request and request.headers else "unknown"
        timestamp = str(int(time.time() / 300))  # 5-minute windows for session grouping
        
        # Create a stable session ID for the same client within a time window
        session_data = f"{client_ip}:{user_agent}:{timestamp}"
        session_hash = hashlib.md5(session_data.encode('utf-8')).hexdigest()[:16]
        return f"sess_{session_hash}"
    except Exception as e:
        logger.warning(f"Failed to generate session ID: {e}")
        # Fallback to a random UUID
        return f"sess_{str(uuid.uuid4())[:16]}"

app = FastAPI(title="Oracle SQL Assistant (RAG-enabled)", version="2.0")

# Add background task to clean up expired tokens periodically
@app.on_event("startup")
async def startup_event():
    """Start background task for cleaning up expired tokens."""
    # In a production system, you would implement a proper background task
    # For now, we'll just log that cleanup is needed
    logger.info("Token cleanup task would start here in production")

# Simple timing middleware to see every request
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger = logging.getLogger("app.http")
    t0 = time.perf_counter()
    logger.debug("→ %s %s", request.method, request.url.path)
    try:
        resp = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        logger.debug("← %s %s %s %.1fms", request.method, request.url.path, resp.status_code, ms)
        return resp
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        logger.exception("✖ %s %s error after %.1fms", request.method, request.url.path, ms)
        raise

# ---------------------------
# CORS
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ quick health
@app.get("/health")
def health():
    """Enhanced health check with quality metrics summary and token usage."""
    health_data = {"ok": True, "timestamp": time.time()}
    
    # Add quality metrics summary if available
    if QUALITY_METRICS_AVAILABLE:
        try:
            # TODO: Implement quality dashboard with new AI training recorder
            quality_summary = {}
            health_data["quality_metrics"] = {
                "system_health": quality_summary.get("system_health", "unknown"),
                "overall_score": quality_summary.get("overall_score", 0.0),
                "total_queries_last_hour": quality_summary.get("performance_indicators", {}).get("total_queries", 0),
                "alerts_count": len(quality_summary.get("alerts", []))
            }
        except Exception as e:
            health_data["quality_metrics"] = {"error": str(e)}
    
    # Add token usage tracking
    try:
        from app.token_tracker import get_token_tracker
        tracker = get_token_tracker()
        usage = tracker.get_current_usage()
        cost = tracker.calculate_cost(usage)
        
        health_data["token_usage"] = {
            "total_prompt_tokens": usage["total"]["prompt_tokens"],
            "total_completion_tokens": usage["total"]["completion_tokens"],
            "total_tokens": usage["total"]["total_tokens"],
            "total_requests": usage["total"]["requests_count"],
            "estimated_cost": round(cost["total_cost"], 6)
        }
    except Exception as e:
        health_data["token_usage"] = {"error": str(e)}
    
    return health_data

@app.get("/token-usage")
def token_usage_report(hours: int = 24):
    """Get detailed token usage report for cost tracking."""
    try:
        from app.token_tracker import get_token_tracker
        tracker = get_token_tracker()
        report = tracker.get_usage_report(hours)
        return {
            "status": "success",
            "report": report,
            "data": tracker.get_usage_since(hours)
        }
    except Exception as e:
        logger.exception("Failed to generate token usage report")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate token usage report: {str(e)}"
        )

@app.get("/token-usage/reset")
def reset_token_usage():
    """Reset token usage tracking."""
    try:
        from app.token_tracker import reset_all_tracking
        reset_all_tracking()
        return {
            "status": "success",
            "message": "Token usage tracking reset successfully"
        }
    except Exception as e:
        logger.exception("Failed to reset token usage tracking")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset token usage tracking: {str(e)}"
        )

@app.get("/token-usage/detailed-logs")
def get_detailed_token_logs():
    """Get detailed token usage logs."""
    try:
        from app.token_logger import get_token_logger
        token_logger = get_token_logger()
        
        # Read the detailed log file
        import json
        from pathlib import Path
        
        log_file = Path("logs") / "token_usage_detailed.log"
        logs = []
        
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            log_entry = json.loads(line.strip())
                            logs.append(log_entry)
                        except json.JSONDecodeError:
                            # Skip invalid lines
                            continue
        
        return {
            "status": "success",
            "logs": logs,
            "count": len(logs)
        }
    except Exception as e:
        logger.exception("Failed to get detailed token logs")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get detailed token logs: {str(e)}"
        )

@app.get("/token-usage/daily-summary")
def get_daily_token_summary(date: Optional[str] = None):
    """Get daily token usage summary."""
    try:
        from app.token_logger import get_token_logger
        token_logger = get_token_logger()
        
        summary = token_logger.get_daily_summary(date) if date is not None else token_logger.get_daily_summary()
        return {
            "status": "success",
            "date": date or "today",
            "summary": summary
        }
    except Exception as e:
        logger.exception("Failed to get daily token summary")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get daily token summary: {str(e)}"
        )

@app.get("/token-usage/daily-cost")
def get_daily_token_cost(date: Optional[str] = None):
    """Get daily token usage cost estimate."""
    try:
        from app.token_logger import get_token_logger
        token_logger = get_token_logger()
        
        cost = token_logger.calculate_daily_cost(date) if date is not None else token_logger.calculate_daily_cost()
        return {
            "status": "success",
            "date": date or "today",
            "cost": cost
        }
    except Exception as e:
        logger.exception("Failed to calculate daily token cost")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate daily token cost: {str(e)}"
        )

# Test endpoint for CORS debugging
@app.get("/test")
def test_endpoint():
    return {"message": "CORS test successful", "timestamp": time.time()}

# General OPTIONS handler for any endpoint
@app.options("/{path:path}")
async def options_handler(request: Request, path: str):
    logger.info(f"OPTIONS request for /{path} from origin: {request.headers.get('origin')}")
    return JSONResponse(
        status_code=200,
        content={"message": "OK"},
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true"
        }
    )

# ---------------------------
# Optional templates
# ---------------------------
templates = None
templates_dir = Path("templates")
if not templates_dir.exists():
    os.makedirs(templates_dir, exist_ok=True)
try:
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
except ImportError:
    templates = None

# ---------------------------
# Models
# ---------------------------
class Question(BaseModel):
    question: str
    # Frontend now sends "" for General, "source_db_1" for SOS.
    # Keep optional & permissive for backward-compatibility with aliases.

# ---------------------------
# Login Endpoint
# ---------------------------
    selected_db: Optional[str] = ""
    # New explicit mode values: "General" | "SOS" (case-insensitive)
    mode: str = "General"
    # Pagination parameters
    page: Optional[int] = 1
    page_size: Optional[int] = 1000

class FeedbackIn(BaseModel):
    turn_id: int
    task_type: str = Field(pattern="^(sql|summary|overall)$")
    feedback_type: str = Field(pattern="^(good|wrong|needs_improvement)$")
    sql_sample_id: Optional[int] = None
    summary_sample_id: Optional[int] = None
    comment: Optional[str] = None
    labeler_role: Optional[str] = "end_user"
    source: Optional[str] = None  # 'api' or 'local'

# File upload models
class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    size: int
    content_type: str

class FileAnalysisRequest(BaseModel):
    file_id: str
    question: str

class FileAnalysisResponse(BaseModel):
    status: str
    summary: str

# ---------------------------
# Helpers
# ---------------------------
def safe_json(obj):
    try:
        import datetime
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
    except Exception:
        pass
    try:
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return str(obj)

def get_valid_columns() -> list:
    """
    Hook for column hints in Oracle errors, if you wire a live validator later.
    """
    return []

def _normalize_mode(mode: Optional[str]) -> str:
    """
    Normalize inbound mode strings to one of: 'General', 'SOS', 'PRAN_ERP', 'RFL_ERP'
    Accepts legacy/loose inputs.
    """
    if not mode:
        return "General"
    m = mode.strip().lower()
    if m in ("general", "gen"):
        return "General"
    if m in ("sos", "source_db_1", "db1"):
        return "SOS"
    if m in ("erp", "source_db_2", "db2", "r12", "test db", "test_db", "pran erp"):
        return "PRAN_ERP"
    if m in ("rfl erp", "source_db_3", "db3"):
        return "RFL_ERP"
    return "General"

def _normalize_selected_db(selected_db: Optional[str], mode: str) -> str:
    """
    Normalize DB aliases to canonical IDs.
    """
    if mode == "General":
        return ""
    if mode == "PRAN_ERP":
        return "source_db_2"
    if mode == "RFL_ERP":
        return "source_db_3"
    # If caller supplied an explicit DB, normalize it; else infer from mode
    if not selected_db or not selected_db.strip():
        return "source_db_1"  # Default to SOS
    s = selected_db.strip().lower()
    if s in ("sos", "source_db_1", "db1"):
        return "source_db_1"
    if s in ("erp", "source_db_2", "db2", "r12", "test db", "test_db", "pran erp"):
        return "source_db_2"
    if s in ("rfl erp", "source_db_3", "db3"):
        return "source_db_3"
    # Allow already-canonical values to pass through
    if selected_db in ("source_db_1", "source_db_2", "source_db_3"):
        return selected_db
    # Unknown → leave empty to force General-like behavior (safe)
    return ""

# ---------------------------
# Oracle exception handler (expanded map)
# ---------------------------
# Handle Oracle database errors with a more generic approach to avoid type issues
@app.exception_handler(Exception)
async def oracle_error_handler(request: Request, exc: Exception):
    # Check if this is an Oracle database error
    if hasattr(exc, 'args') and len(exc.args) > 0:
        text = str(exc)
        m = re.search(r"(ORA-\d{5})", text)
        if m:
            error_code = m.group(1)
            friendly = {
                "ORA-00904": "Invalid column name",
                "ORA-01861": "Use TO_DATE(value, 'DD-MON-YYYY') format",
                "ORA-00942": "Table or view does not exist",
                "ORA-01722": "Invalid number (check numeric comparisons and casts)",
                "ORA-01427": "Single-row subquery returns more than one row",
                "ORA-12899": "Value too large for column",
            }.get(error_code, text)
            return JSONResponse(
                status_code=400,
                content={
                    "error": error_code,
                    "message": friendly,
                    "valid_columns": get_valid_columns(),
                },
            )
    # Re-raise non-Oracle exceptions
    raise exc

# ---------------------------
# Chat -> uses new RAG pipeline, preserves envelope + feedback IDs
# ---------------------------
@app.post("/chat")
async def chat_api(question: Question, request: Request):
    try:
        if not question.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        # Log the user query
        logger.info(f"[MAIN] Received user query: {question.question}")

        # Determine & normalize mode/DB
        mode_in = question.mode
        selected_db_in = question.selected_db
        mode = _normalize_mode(mode_in)  # 'General' | 'SOS' | 'PRAN_ERP' | 'RFL_ERP'
        selected_db = _normalize_selected_db(selected_db_in, mode)  # "" | source_db_1 | source_db_2 | source_db_3

        # Log the processing details
        logger.info(f"[MAIN] Processing query with mode={mode}, db={selected_db}")

        # === Call the appropriate RAG orchestrator based on mode ===
        if mode in ("PRAN_ERP", "RFL_ERP"):
            # For both ERP modes, use the ERP R12 engine but with different databases
            output = await erp_rag_answer(
                question.question, 
                selected_db=selected_db,
                mode=mode,
                # Phase 5: Pass training data collection parameters for hybrid processing
                session_id=generate_session_id(request),
                client_ip=request.client.host if request and request.client else None,
                user_agent=request.headers.get('user-agent') if request and request.headers else None,
                page=question.page or 1,
                page_size=question.page_size or 1000
            )
        else:
            # Use SOS RAG engine for General and SOS modes
            output = await sos_rag_answer(
                question.question, 
                selected_db=selected_db,
                mode=mode,  # Pass the new mode parameter
                # Phase 5: Pass training data collection parameters for hybrid processing
                session_id=generate_session_id(request),
                client_ip=request.client.host if request and request.client else None,
                user_agent=request.headers.get('user-agent') if request and request.headers else None
            )

        # Log the output
        if output:
            if "sql" in output and output["sql"]:
                logger.info(f"[MAIN] Generated SQL: {output['sql'][:500]}...")
            if "summary" in output and output["summary"]:
                logger.info(f"[MAIN] Generated summary: {output['summary'][:200]}...")
            logger.info(f"[MAIN] Query processing completed successfully")

        # Handle case where output is None
        if output is None:
            output = {}

        # Error passthrough (keep legacy shape)
        if isinstance(output, dict) and output.get("status") == "error":
            return {
                "status": "error",
                "message": output.get("message") or output.get("error") or "Request failed.",
                "sql": output.get("sql"),
                "schema_context": output.get("schema_context", []),
                "schema_context_ids": output.get("schema_context_ids", []),
                "suggestions": output.get(
                    "suggestions",
                    [
                        "Try rephrasing your question",
                        "Be specific about the table or field names",
                        "Add a time window (e.g., 'last 30 days', 'May-2025')",
                    ],
                ),
            }

        # Success path (normalize fields exactly like before)
        display_mode = output.get("display_mode", "table") if output else "table"
        results = {
            "columns": (output.get("results") or {}).get("columns", []) if output else [],
            "rows": (output.get("results") or {}).get("rows", []) if output else [],
            "row_count": (output.get("results") or {}).get("row_count", 0) if output else 0,
        }

        # ---------------------------
        # Feedback IDs (same as your legacy code)
        # ---------------------------
        ids = {}
        if FEEDBACK_STORE_AVAILABLE:
            try:
                schema_text = "\n\n".join(output.get("schema_context", [])) if output and output.get("schema_context") else None
                schema_ids = output.get("schema_context_ids") or None if output else None

                # Enhanced feedback recording for hybrid processing
                hybrid_meta = output.get("hybrid_metadata", {}) if output else {}
                
                # Extract username from request
                username = _get_username_from_request(request)
                
                enhanced_meta = {
                    "ui": "web", 
                    "mode": "non_stream", 
                    "display_mode": display_mode,
                    # Phase 4.2: Add hybrid processing metadata to feedback
                    "hybrid_processing": bool(hybrid_meta),
                    "processing_mode": hybrid_meta.get("processing_mode") if hybrid_meta else mode,  # Use mode parameter if hybrid_meta is not available
                    "model_used": hybrid_meta.get("model_used") if hybrid_meta else None,
                    "selection_reasoning": hybrid_meta.get("selection_reasoning") if hybrid_meta else None,
                    "processing_time_ms": (hybrid_meta.get("processing_time", 0.0) * 1000) if hybrid_meta else 0.0,
                    "local_confidence": hybrid_meta.get("local_confidence") if hybrid_meta else None,
                    "api_confidence": hybrid_meta.get("api_confidence") if hybrid_meta else None,
                    # Phase 5: Add training data collection metadata
                    "training_data_recorded": hybrid_meta.get("training_data_recorded", False) if hybrid_meta else False,
                    "classification_time_ms": hybrid_meta.get("classification_time_ms", 0.0) if hybrid_meta else 0.0,
                    "sql_execution_time_ms": hybrid_meta.get("sql_execution_time_ms", 0.0) if hybrid_meta else 0.0,
                    "sql_execution_success": hybrid_meta.get("sql_execution_success", False) if hybrid_meta else False,
                    # Add username to metadata
                    "username": username
                }

                turn_id = insert_turn(
                    source_db_id=selected_db,  # ← use effective DB after normalization
                    client_ip=request.client.host if request and request.client else None,
                    user_question=question.question,
                    schema_context_text=schema_text,
                    schema_context_ids=schema_ids,
                    meta=enhanced_meta,
                )

                # Phase 5: Update hybrid processing call with training data parameters
                if hybrid_meta and hybrid_meta.get("training_data_recorded") and COLLECT_TRAINING_DATA:
                    try:
                        logger.info(f"[MAIN] Updating hybrid training data with turn_id {turn_id}")
                        # future enhancement hook
                    except Exception as e:
                        logger.warning(f"[MAIN] Failed to update hybrid training data: {e}")

                sql_sample_id = None
                if output and output.get("sql"):
                    sql_sample_id = insert_sql_sample(
                        turn_id=turn_id,
                        model_name=OLLAMA_SQL_MODEL,
                        prompt_text=None,
                        sql_text=output["sql"],
                        display_mode=display_mode,
                    )

                summary_sample_id = None
                if output and output.get("summary"):
                    snapshot = {
                        "columns": results["columns"],
                        "row_count": results["row_count"],
                        "rows": results["rows"][:200],
                    }
                    summary_sample_id = insert_summary_sample(
                        turn_id=turn_id,
                        model_name=OLLAMA_ANALYTICAL_MODEL,
                        prompt_text=None,
                        data_snapshot=json.dumps(snapshot, default=safe_json),
                        sql_used=output.get("sql"),
                        display_mode=display_mode,
                    )

                ids = {
                    "turn_id": turn_id,
                    "sql_sample_id": sql_sample_id,
                    "summary_sample_id": summary_sample_id,
                }
            except Exception as fe:
                logging.getLogger(__name__).warning(f"[feedback_store] Could not create feedback IDs: {fe}")
        response_payload = {
            "status": "success",
            "summary": output.get("summary", "") if output else "",
            "sql": output.get("sql") if output else None,
            "display_mode": display_mode,
            "results": results,
            "schema_context": output.get("schema_context", []) if output else [],
            "schema_context_ids": output.get("schema_context_ids", []) if output else [],
        }
        
        # Phase 4.2: Add hybrid processing metadata if available
        if output and output.get("hybrid_metadata"):
            response_payload["hybrid_metadata"] = output.get("hybrid_metadata")
        
        if ids:
            response_payload["ids"] = ids

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Unexpected error: {e}", exc_info=True)
        # Return envelope your frontend can render as an error bubble
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Internal server error",
                "error": str(e),
                "suggestions": [
                    "Rephrase and try again",
                    "If this persists, reload schema embeddings then retry",
                ],
            },
        )

# ---------------------------
# Root
# ---------------------------
@app.get("/", response_class=HTMLResponse if templates else JSONResponse)
async def root(request: Request):
    if templates:
        return templates.TemplateResponse("chat.html", {"request": request})
    return JSONResponse(content={"message": "Oracle SQL Assistant is running (RAG-enabled)."})

# ---------------------------
# POST /feedback
# ---------------------------
@app.post("/feedback")
async def post_feedback(payload: FeedbackIn, request: Request):
    # Log received feedback
    logger.info(f"Feedback received - Type: {payload.feedback_type}, Task: {payload.task_type}, Source: {payload.source or 'unknown'}")
    logger.info(f"Full payload: {payload.dict()}")
    logger.info(f"Source field value: '{payload.source}', Type: {type(payload.source)}")
    if payload.comment:
        logger.info(f"Feedback comment: {payload.comment[:100]}{'...' if len(payload.comment) > 100 else ''}")
    
    # minimal validation (same as before)
    if payload.task_type == "sql" and not payload.sql_sample_id:
        logger.warning("Feedback validation failed: sql_sample_id required for SQL task")
        return JSONResponse(status_code=400, content={"error": "sql_sample_id required"})
    if payload.task_type == "summary" and not payload.summary_sample_id:
        logger.warning("Feedback validation failed: summary_sample_id required for summary task")
        return JSONResponse(status_code=400, content={"error": "summary_sample_id required"})
    if payload.feedback_type == "needs_improvement" and not (payload.comment and payload.comment.strip()):
        logger.warning("Feedback validation failed: comment required for needs_improvement feedback")
        return JSONResponse(status_code=400, content={"error": "comment required for needs_improvement"})

    try:
        # Record feedback in the old system (for backward compatibility)
        fid = insert_feedback(
            turn_id=payload.turn_id,
            task_type=payload.task_type,
            feedback_type=payload.feedback_type,
            sql_sample_id=payload.sql_sample_id,
            summary_sample_id=payload.summary_sample_id,
            improvement_comment=payload.comment,
            labeler_role=payload.labeler_role,
            meta={
                "client_ip": request.client.host if request and request.client else None,
                "ui": "web",
                "source": payload.source or ''  # Add source to meta
            },
        )
        
        # ALSO record feedback in the new AI training system
        if AI_TRAINING_RECORDER_AVAILABLE:
            try:
                from app.ai_training_data_recorder import ai_training_data_recorder
                from app.db_connector import connect_feedback
                
                # Validate that the turn_id corresponds to a valid query in AI_TRAINING_QUERIES
                is_valid_query = False
                try:
                    with connect_feedback() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT COUNT(*) FROM AI_TRAINING_QUERIES WHERE QUERY_ID = :query_id", {"query_id": payload.turn_id})
                        count = cur.fetchone()[0]
                        is_valid_query = count > 0
                except Exception as e:
                    logger.warning(f"Failed to validate query ID {payload.turn_id}: {e}")
                    is_valid_query = True  # Continue anyway to avoid blocking feedback
                
                if not is_valid_query:
                    logger.warning(f"Invalid query ID {payload.turn_id} in feedback, using default query ID 1")
                    query_id = 1
                else:
                    query_id = payload.turn_id
                
                feedback_details = {
                    'feedback_type': payload.feedback_type,
                    'feedback_score': 5 if payload.feedback_type == 'good' else (1 if payload.feedback_type == 'wrong' else 3),
                    'feedback_comment': payload.comment,
                    'source': payload.source or '',  # Fix: Ensure source is properly passed
                    'submission_timestamp': _dt.now()
                }
                logger.info(f"Recording feedback with details: {feedback_details}")
                logger.info(f"Source value for recording: '{feedback_details['source']}'")
                # Record in the new AI_USER_FEEDBACK table
                feedback_id = ai_training_data_recorder.record_user_feedback(
                    query_id=query_id,  # turn_id maps to query_id in new system
                    feedback_details=feedback_details
                )
                logger.info(f"Feedback stored successfully - ID: {feedback_id}, Type: {payload.feedback_type}, Source: {payload.source or 'unknown'}, Query ID: {query_id}")
            except Exception as e:
                logger.warning(f"Failed to record feedback in AI training system: {e}")
                logger.exception("Exception details:")
        
        logger.info(f"Feedback processed successfully - Feedback ID: {fid}")
        return {"feedback_id": fid, "status": "created"}
    except Exception as e:
        logger.exception("Failed to insert feedback")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------------------------
# Quality Metrics Endpoint (Step 5.2)
# ---------------------------
@app.get("/quality-metrics")
async def get_quality_metrics(time_window: int = 24):
    """
    Step 5.2: Get comprehensive quality metrics including success rates and user satisfaction.
    
    Args:
        time_window: Time window in hours for analysis (default: 24)
        
    Returns:
        Quality metrics report
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # Validate time window
        if not (1 <= time_window <= 168):  # 1 hour to 1 week
            return JSONResponse(
                status_code=400,
                content={"error": "Time window must be between 1 and 168 hours"}
            )
        
        # Get comprehensive quality metrics
        # TODO: Implement quality metrics with new AI training recorder
        quality_report = {}
        
        if not quality_report:
            return JSONResponse(
                status_code=404,
                content={"error": "No data available for the specified time window"}
            )
        
        return {
            "status": "success",
            "data": quality_report,
            "metadata": {
                "endpoint": "quality-metrics",
                "version": "1.0",
                "generated_at": quality_report.get("report_timestamp"),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to generate quality metrics")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate quality metrics: {str(e)}"}
        )

@app.get("/quality-metrics/success-rates")
async def get_success_rates(time_window: int = 24):
    """
    Get specific success rate metrics for query understanding and SQL execution.
    
    Args:
        time_window: Time window in hours for analysis
        
    Returns:
        Success rate metrics
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement success metrics with new AI training recorder
        success_metrics = {}
        
        return {
            "status": "success",
            "data": success_metrics,
            "metadata": {
                "endpoint": "success-rates",
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get success rates")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get success rates: {str(e)}"}
        )

@app.get("/quality-metrics/user-satisfaction")
async def get_user_satisfaction(time_window: int = 24):
    """
    Get user satisfaction indicators including acceptance rates and feedback scores.
    
    Args:
        time_window: Time window in hours for analysis
        
    Returns:
        User satisfaction metrics
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement user satisfaction metrics with new AI training recorder
        satisfaction_metrics = {}
        
        return {
            "status": "success",
            "data": satisfaction_metrics,
            "metadata": {
                "endpoint": "user-satisfaction",
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get user satisfaction metrics")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get user satisfaction metrics: {str(e)}"}
        )

@app.get("/quality-metrics/test-system")
async def test_quality_metrics_system_endpoint(time_window: int = 1):
    """
    Test the quality metrics system end-to-end.
    
    Args:
        time_window: Time window in hours for testing (default: 1)
        
    Returns:
        Test results and diagnostics
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement quality metrics testing with new AI training recorder
        test_results = {}
        
        return {
            "status": "success",
            "data": test_results,
            "metadata": {
                "endpoint": "quality-metrics-test-system",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to test quality metrics system")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to test quality metrics system: {str(e)}"}
        )

@app.get("/training-data/test")
async def test_training_data_collection():
    """
    Test the training data collection system.
    
    Returns:
        Test results and system status
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Training data collection system not available"}
        )
    
    try:
        # Test the training data collection system
        # Training data collection system test not implemented
        test_results = {"status": "unavailable", "message": "Training data collection system test not implemented"}
        
        return {
            "status": "success",
            "data": test_results,
            "metadata": {
                "endpoint": "training-data-test",
                "version": "1.0",
                "generated_at": test_results.get("timestamp")
            }
        }
        
    except Exception as e:
        logger.exception("Failed to test training data collection system")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to test training data collection system: {str(e)}"}
        )

@app.get("/training-data/status")
async def get_training_data_status():
    """
    Get current status of the training data collection system.
    
    Returns:
        System status information
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Training data collection system not available"}
        )
    
    try:
        # Get the training data collection system status
        # Training data collection system status not implemented
        status_info = {"status": "unavailable", "message": "Training data collection system status not implemented"}
        
        return {
            "status": "success",
            "data": status_info,
            "metadata": {
                "endpoint": "training-data-status",
                "version": "1.0",
                "generated_at": _dt.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get training data collection status")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get training data collection status: {str(e)}"}
        )

# ------------------------------ Phase 6: Continuous Learning Loop ------------------------------

@app.get("/learning/performance-comparison")
async def get_performance_comparison(time_window: int = 24):
    """
    Phase 6: Get performance comparison between local and API models.
    
    Args:
        time_window: Time window in hours for analysis (default: 24)
        
    Returns:
        Performance comparison metrics by query type
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement performance comparison with new AI training recorder
        performance_comparison = {}
        
        return {
            "status": "success",
            "data": performance_comparison,
            "metadata": {
                "endpoint": "performance-comparison",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get performance comparison")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get performance comparison: {str(e)}"}
        )

@app.get("/learning/model-strengths")
async def get_model_strengths(time_window: int = 24):
    """
    Phase 6: Get model strengths by domain/query type.
    
    Args:
        time_window: Time window in hours for analysis (default: 24)
        
    Returns:
        Model strengths by domain/query type
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement model strengths analysis with new AI training recorder
        model_strengths = {}
        
        return {
            "status": "success",
            "data": model_strengths,
            "metadata": {
                "endpoint": "model-strengths",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get model strengths")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get model strengths: {str(e)}"}
        )

@app.get("/learning/user-preferences")
async def get_user_preferences(time_window: int = 24):
    """
    Phase 6: Get user preference patterns for different models.
    
    Args:
        time_window: Time window in hours for analysis (default: 24)
        
    Returns:
        User preference patterns analysis
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement user preference analysis with new AI training recorder
        preference_patterns = {}
        
        return {
            "status": "success",
            "data": preference_patterns,
            "metadata": {
                "endpoint": "user-preferences",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get user preferences")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get user preferences: {str(e)}"}
        )

@app.get("/learning/insights")
async def get_learning_insights(time_window: int = 24):
    """
    Phase 6: Get comprehensive learning insights from pattern analysis.
    
    Args:
        time_window: Time window in hours for analysis (default: 24)
        
    Returns:
        Comprehensive learning insights
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement learning insights with new AI training recorder
        insights = {}
        
        return {
            "status": "success",
            "data": insights,
            "metadata": {
                "endpoint": "learning-insights",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to get learning insights")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get learning insights: {str(e)}"}
        )

@app.get("/learning/test-system")
async def test_learning_system(time_window: int = 24):
    """
    Phase 6: Test the continuous learning system end-to-end.
    
    Args:
        time_window: Time window in hours for testing (default: 24)
        
    Returns:
        Test results and diagnostics for continuous learning system
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement continuous learning system test with new AI training recorder
        test_results = {}
        
        return {
            "status": "success",
            "data": test_results,
            "metadata": {
                "endpoint": "learning-test-system",
                "version": "1.0",
                "generated_at": test_results.get("timestamp"),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to test continuous learning system")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to test continuous learning system: {str(e)}"}
        )

@app.get("/learning/test-processor")
async def test_learning_processor(time_window: int = 24):
    """
    Phase 6: Test the continuous learning system through the hybrid processor.
    
    Args:
        time_window: Time window in hours for testing (default: 24)
        
    Returns:
        Test results and diagnostics for continuous learning system via processor
    """
    try:
        # Continuous learning system test not implemented
        test_results = {"status": "unavailable", "message": "Continuous learning system test not implemented"}
        
        return {
            "status": "success",
            "data": test_results,
            "metadata": {
                "endpoint": "learning-test-processor",
                "version": "1.0",
                "generated_at": _dt.now().isoformat(),
                "time_window_hours": time_window
            }
        }
        
    except Exception as e:
        logger.exception("Failed to test continuous learning system via processor")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to test continuous learning system via processor: {str(e)}"}
        )

# ------------------------------ Phase 6.2: Training Data Preparation ------------------------------

@app.get("/training-data/high-quality-samples")
async def get_high_quality_samples(time_window: int = 168, min_quality: float = 0.8):
    """
    Step 6.2: Identify high-quality samples for training data preparation.
    
    Args:
        time_window: Time window in hours for analysis (default: 168 hours/1 week)
        min_quality: Minimum quality score threshold for high-quality samples (default: 0.8)
        
    Returns:
        High-quality samples categorized by type
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    try:
        # TODO: Implement high-quality samples identification with new AI training recorder
        samples = {}
        
        return {
            "status": "success",
            "data": samples,
            "metadata": {
                "endpoint": "high-quality-samples",
                "version": "1.0",
                "generated_at": samples.get("timestamp"),
                "time_window_hours": time_window,
                "min_quality_score": min_quality
            }
        }
        
    except Exception as e:
        logger.exception("Failed to identify high-quality samples")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to identify high-quality samples: {str(e)}"}
        )

@app.get("/training-data/datasets/{dataset_type}")
async def get_training_dataset(dataset_type: str, time_window: int = 720):
    """
    Step 6.2: Create training datasets for different domains.
    
    Args:
        dataset_type: Type of dataset to create ('manufacturing', 'oracle_sql', 'business_logic')
        time_window: Time window in hours for analysis (default: 720 hours/30 days)
        
    Returns:
        Training dataset for the specified type
    """
    if not QUALITY_METRICS_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Quality metrics system not available"}
        )
    
    supported_types = ["manufacturing", "oracle_sql", "business_logic"]
    if dataset_type not in supported_types:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unsupported dataset type: {dataset_type}",
                "supported_types": supported_types
            }
        )
    
    try:
        # TODO: Implement training dataset creation with new AI training recorder
        dataset = {}
        
        if "error" in dataset:
            return JSONResponse(
                status_code=400,
                content=dataset
            )
        
        return {
            "status": "success",
            "data": dataset,
            "metadata": {
                "endpoint": f"training-dataset-{dataset_type}",
                "version": "1.0",
                "generated_at": dataset.get("creation_timestamp"),
                "time_window_hours": time_window,
                "dataset_type": dataset_type
            }
        }
        
    except Exception as e:
        logger.exception(f"Failed to create training dataset for {dataset_type}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create training dataset for {dataset_type}: {str(e)}"}
        )

@app.get("/training-data/processor/high-quality-samples")
async def get_processor_high_quality_samples(time_window: int = 168, min_quality: float = 0.8):
    """
    Step 6.2: Identify high-quality samples through the hybrid processor.
    
    Args:
        time_window: Time window in hours for analysis (default: 168 hours/1 week)
        min_quality: Minimum quality score threshold (default: 0.8)
        
    Returns:
        High-quality samples categorized by type
    """
    try:
        # High quality samples not implemented
        samples = {"status": "unavailable", "message": "High quality samples not implemented"}
        
        if samples.get("status") == "unavailable":
            return JSONResponse(
                status_code=503,
                content={"error": "Training data collection system not available"}
            )
        
        return {
            "status": "success",
            "data": samples.get("data", {}),
            "metadata": {
                "endpoint": "processor-high-quality-samples",
                "version": "1.0",
                "time_window_hours": time_window,
                "min_quality_score": min_quality
            }
        }
        
    except Exception as e:
        logger.exception("Failed to identify high-quality samples via processor")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to identify high-quality samples via processor: {str(e)}"}
        )

@app.get("/training-data/processor/datasets/{dataset_type}")
async def get_processor_training_dataset(dataset_type: str, time_window: int = 720):
    """
    Step 6.2: Create training datasets through the hybrid processor.
    
    Args:
        dataset_type: Type of dataset to create ('manufacturing', 'oracle_sql', 'business_logic')
        time_window: Time window in hours for analysis (default: 720 hours/30 days)
        
    Returns:
        Training dataset for the specified type
    """
    supported_types = ["manufacturing", "oracle_sql", "business_logic"]
    if dataset_type not in supported_types:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Unsupported dataset type: {dataset_type}",
                "supported_types": supported_types
            }
        )
    
    try:
        # Training dataset creation not implemented
        dataset = {"status": "unavailable", "message": "Training dataset creation not implemented"}
        
        if dataset.get("status") == "unavailable":
            return JSONResponse(
                status_code=503,
                content={"error": "Training data collection system not available"}
            )
        
        if dataset.get("status") == "error":
            return JSONResponse(
                status_code=500,
                content={"error": dataset.get("message", "Unknown error")}
            )
        
        return {
            "status": "success",
            "data": dataset.get("data", {}),
            "metadata": {
                "endpoint": f"processor-training-dataset-{dataset_type}",
                "version": "1.0",
                "time_window_hours": time_window,
                "dataset_type": dataset_type
            }
        }
        
    except Exception as e:
        logger.exception(f"Failed to create training dataset {dataset_type} via processor")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create training dataset {dataset_type} via processor: {str(e)}"}
        )

# ---------------------------
# GET /export/sql  and  GET /export/summary
# ---------------------------
def _stream_view_as_csv(cur, sql: str):
    """
    Execute a SELECT against a view and stream the result as CSV.
    Converts None -> "" to keep CSV clean.
    """
    cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    # Write header
    yield ",".join(cols) + "\n"

    def _clean(v):
        if v is None:
            return ""
        return str(v)

    import io
    buf = io.StringIO()
    writer = csv.writer(buf)

    while True:
        batch = cur.fetchmany(1000)
        if not batch:
            break
        for r in batch:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([_clean(v) for v in r])
            yield buf.getvalue()

@app.get("/export/sql")
async def export_sql():
    """
    Export rows from V_TRAIN_SQL as CSV.
    """
    try:
        with connect_feedback() as conn:
            cur = conn.cursor()
            gen = _stream_view_as_csv(cur, "SELECT * FROM V_TRAIN_SQL")
            headers = {
                "Content-Disposition": 'attachment; filename="train_sql.csv"',
                "Cache-Control": "no-store",
            }
            return StreamingResponse(gen, media_type="text/csv", headers=headers)
    except Exception as e:
        logging.getLogger(__name__).error(f"/export/sql failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "export failed"})

@app.get("/export/summary")
async def export_summary():
    """
    Export rows from V_TRAIN_SUMMARY as CSV.
    """
    try:
        with connect_feedback() as conn:
            cur = conn.cursor()
            gen = _stream_view_as_csv(cur, "SELECT * FROM V_TRAIN_SUMMARY")
            headers = {
                "Content-Disposition": 'attachment; filename="train_summary.csv"',
                "Cache-Control": "no-store",
            }
            return StreamingResponse(gen, media_type="text/csv", headers=headers)
    except Exception as e:
        logging.getLogger(__name__).error(f"/export/summary failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "export failed"})

# ---------------------------
# File Upload and Analysis Endpoints
# ---------------------------

@app.post("/upload-file", response_model=None)
async def upload_file(request: Request, file: UploadFile = File(...)):
    """
    Upload a file for analysis.
    
    Args:
        request: FastAPI Request object for rate limiting
        file: The file to upload
        
    Returns:
        File upload response with file metadata
    """
    try:
        # Rate limiting check
        if request:
            client_id = _get_client_identifier(request)
            rate_limits = _check_rate_limits(client_id)

            
            if rate_limits["upload_limited"]:
                raise HTTPException(
                    status_code=429,
                    detail="File upload rate limit exceeded. Maximum 10 uploads per hour."
                )
        
        # Validate file size (5MB limit)
        contents = await file.read()
        file_size = len(contents)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400, 
                detail=f"File size exceeds 5MB limit. Current size: {file_size} bytes"
            )
        
        # Validate file type
        if file.content_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=400, 
                detail=f"File type not supported. Supported types: {', '.join(ALLOWED_FILE_TYPES.keys())}"
            )
        
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        file_extension = ALLOWED_FILE_TYPES[file.content_type]
        filename = _sanitize_filename(file.filename or '')
        safe_filename = f"{file_id}{file_extension}"
        file_path = FILE_STORAGE_PATH / safe_filename
        
        # Save file to disk
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Validate file content for security
        if not _validate_file_content(file_path):
            # Remove the file if it's not safe
            file_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400, 
                detail="File content validation failed. File may contain unsafe content."
            )
        
        # Increment rate counter
        if request:
            client_id = _get_client_identifier(request)
            _increment_rate_counters(client_id)
        
        # Cleanup expired files periodically
        import random
        if random.randint(1, 100) <= 5:  # 5% chance to trigger cleanup
            _cleanup_expired_files()
        
        # Return file metadata
        return FileUploadResponse(
            file_id=file_id,
            filename=filename,
            size=file_size,
            content_type=file.content_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to upload file")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to upload file: {str(e)}"
        )

@app.post("/analyze-file", response_model=None)
async def analyze_file(request: FileAnalysisRequest, req: Request):
    """
    Analyze an uploaded file using Google Gemini Flash 1.5.
    
    Args:
        request: File analysis request containing file ID and question
        req: FastAPI Request object for rate limiting
        
    Returns:
        File analysis response with summary from Gemini Flash 1.5
    """
    try:
        # Rate limiting check
        if req:
            client_id = _get_client_identifier(req)
            rate_limits = _check_rate_limits(client_id)
            
            if rate_limits["processing_limited"]:
                raise HTTPException(
                    status_code=429,
                    detail="File processing rate limit exceeded. Maximum 5 processing requests per minute."
                )
            
            # Check API quota
            if rate_limits["api_limited"]:
                raise HTTPException(
                    status_code=429,
                    detail="API quota limit exceeded. Please try again tomorrow."
                )
        
        # Validate file exists
        file_path = FILE_STORAGE_PATH / f"{request.file_id}"
        if not file_path.exists():
            # Try with extensions
            found = False
            for ext in ['.pdf', '.doc', '.docx', '.txt', '.csv', '.xlsx', '.png', '.jpg', '.jpeg', '.gif']:
                file_path = FILE_STORAGE_PATH / f"{request.file_id}{ext}"
                if file_path.exists():
                    found = True
                    break
            
            if not found:
                raise HTTPException(status_code=404, detail="File not found")
        
        # Security check: Validate file content
        if not _validate_file_content(file_path):
            raise HTTPException(
                status_code=400, 
                detail="File content validation failed. File may contain unsafe content."
            )
        
        # Use DeepSeek client to call DeepSeek models
        from .SOS.deepseek_client import DeepSeekClient, DeepSeekError
        try:
            client = DeepSeekClient()
            # Use DeepSeek model for file analysis
            model = "deepseek-chat"
            
            # Encode file for API transmission
            file_data = client.encode_file_for_api(str(file_path))
            if not file_data:
                raise HTTPException(status_code=500, detail="Failed to encode file for analysis")
            
            # Create multimodal message
            messages = client.create_multimodal_message(
                text_content=f"Please analyze the following file and answer the question: {request.question}",
                file_data=file_data
            )
            
            # Add plugins configuration for PDF processing
            plugins = [
                {
                    "id": "file-parser",
                    "pdf": {
                        "engine": "pdf-text"  # Use free text extraction for PDFs
                    }
                }
            ]
            
            # Increment rate counters
            if req:
                client_id = _get_client_identifier(req)
                _increment_rate_counters(client_id)
            
            response = await client.chat_completion(
                messages=messages,
                model=model,
                temperature=0.3,
                max_tokens=1000,
                plugins=plugins
            )
            
            if response.success:
                return {
                    "status": "success",
                    "summary": response.content,
                    "model_used": model
                }
            else:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to analyze file with DeepSeek: {response.error}"
                )
                
        except DeepSeekError as e:
            logger.exception("DeepSeek API error")
            raise HTTPException(
                status_code=500, 
                detail=f"DeepSeek API error: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to analyze file")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to analyze file: {str(e)}"
        )

@app.get("/file-upload-status")
async def get_file_upload_status(request: Request):
    """
    Get current file upload status and rate limits for the user.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        File upload status and rate limit information
    """
    try:
        client_id = _get_client_identifier(request)
        rate_limits = _check_rate_limits(client_id)
        
        import time
        current_time = time.time()
        
        # Get current counts
        upload_key = f"{client_id}:{int(current_time // 3600)}"
        upload_count = user_upload_counts.get(upload_key, 0)
        
        processing_key = f"{client_id}:{int(current_time // 60)}"
        processing_count = user_processing_counts.get(processing_key, 0)
        
        date_key = time.strftime("%Y-%m-%d", time.gmtime(current_time))
        api_count = api_usage_counts.get(date_key, 0)
        
        return {
            "status": "success",
            "rate_limits": {
                "upload": {
                    "current": upload_count,
                    "limit": FILE_UPLOAD_LIMIT_PER_USER,
                    "remaining": max(0, FILE_UPLOAD_LIMIT_PER_USER - upload_count),
                    "reset_time": "Next hour"
                },
                "processing": {
                    "current": processing_count,
                    "limit": PROCESSING_RATE_LIMIT,
                    "remaining": max(0, PROCESSING_RATE_LIMIT - processing_count),
                    "reset_time": "Next minute"
                },
                "api_quota": {
                    "current": api_count,
                    "limit": API_QUOTA_LIMIT,
                    "remaining": max(0, API_QUOTA_LIMIT - api_count),
                    "reset_time": "Tomorrow"
                }
            },
            "limits_exceeded": rate_limits
        }
    except Exception as e:
        logger.exception("Failed to get file upload status")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get file upload status: {str(e)}"
        )

# ---------------------------
# Admin Dashboard Endpoints
# ---------------------------

def _get_username_from_request(request: Request) -> Optional[str]:
    """
    Extract username from the request authentication token.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Username if available, None otherwise
    """
    try:
        # Extract token from Authorization header or custom header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
        else:
            # Check for custom auth token header
            token = request.headers.get("X-Auth-Token") or request.headers.get("authToken")
        
        # Look up username from token-username mapping
        if token:
            with token_username_map_lock:
                username = token_username_map.get(token)
            if username:
                return username
    except Exception as e:
        logger.warning(f"Failed to extract username from request: {e}")
    
    return None

def _is_admin_user(request: Request) -> bool:
    """
    Check if the authenticated user is an admin.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        True if user is admin, False otherwise
    """
    username = _get_username_from_request(request)
    return username == "AdminMIS"

@app.get("/admin/metrics")
async def get_admin_metrics(request: Request):
    """
    Get admin dashboard metrics.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Admin dashboard metrics
    """
    # Check if user is admin
    if not _is_admin_user(request):
        raise HTTPException(status_code=403, detail="Access denied. Admin access required.")
    
    # In a real implementation, these would come from database queries
    metrics = {
        "users": 1250,
        "chats": 3457,
        "active_users": 312,
        "server_status": "Online"
    }
    
    return metrics


@app.get("/admin/recent-activity")
async def get_admin_recent_activity(request: Request):
    """
    Get recent system activity for admin dashboard.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Recent activity logs
    """
    # Check if user is admin
    if not _is_admin_user(request):
        raise HTTPException(status_code=403, detail="Access denied. Admin access required.")
    
    # In a real implementation, these would come from database queries
    activity = [
        {"date": "Apr 20", "action": "User1234 logged in", "time": "2 minutes ago"},
        {"date": "Apr 19", "action": "Server restart completed", "time": "1 hour ago"},
        {"date": "Apr 19", "action": "New user registration", "time": "3 hours ago"},
        {"date": "Apr 18", "action": "System update deployed", "time": "1 day ago"}
    ]
    
    return activity

# ---------------------------
# Login Endpoint
# ---------------------------
@app.post("/login", response_model=dict)
async def login(login_request: dict):
    """
    Authenticate user by calling external HRIS API directly or admin credentials.
    
    Args:
        login_request: Dictionary containing username and password
        
    Returns:
        Authentication result with success status and optional token
    """
    try:
        username = login_request.get("username")
        password = login_request.get("password")
        
        if not username or not password:
            raise HTTPException(
                status_code=400, 
                detail="Username and password are required"
            )
        
        # Check for admin credentials first
        if username == "AdminMIS" and password == "mis123":
            # Generate a simple token for admin (in production, use JWT or similar)
            import uuid
            token = str(uuid.uuid4())
            
            # Store token-username mapping
            with token_username_map_lock:
                token_username_map[token] = username
            
            return {
                "success": True,
                "message": "Admin login successful",
                "token": token,
                "isAdmin": True
            }
        
        # Directly call the external HRIS API for regular users
        import httpx
        import json
        
        url = "http://hrisapi.prangroup.com:8083/v1/Login/UserValidationAp"
        
        # Construct JSON payload
        body = {
            "UserName": username,
            "Password": password
        }
        
        # Set headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Basic YXV0aDoxMlByYW5AMTIzNDU2JA==",
            "S_KEYL": "RxsJ4LQdkVFTv37rYfW9b6"
        }
        
        # Make the REST API POST request
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=body,
                headers=headers,
                timeout=30.0
            )
            
            # Parse JSON to extract "isSuccess" value
            response_data = response.json()
            is_success = response_data.get("isSuccess", False)
            
            if is_success:
                # Generate a simple token (in production, use JWT or similar)
                import uuid
                token = str(uuid.uuid4())
                
                # Store token-username mapping
                with token_username_map_lock:
                    token_username_map[token] = username
                
                return {
                    "success": True,
                    "message": "Login successful",
                    "token": token,
                    "isAdmin": False
                }
            else:
                raise HTTPException(
                    status_code=401, 
                    detail="Invalid username or password"
                )
                
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception("Login error")
        raise HTTPException(
            status_code=500, 
            detail=f"Login failed: {str(e)}"
        )

@app.post("/admin/logout")
async def admin_logout(request: Request):
    """
    Admin logout endpoint to invalidate token.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Logout success message
    """
    try:
        # Extract token from Authorization header or custom header
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
        else:
            # Check for custom auth token header
            token = request.headers.get("X-Auth-Token") or request.headers.get("authToken")
        
        # Remove token from token-username mapping
        if token:
            with token_username_map_lock:
                if token in token_username_map:
                    del token_username_map[token]
        
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.exception("Logout error")
        raise HTTPException(
            status_code=500, 
            detail=f"Logout failed: {str(e)}"
        )


@app.post("/logout")
async def logout(request: Request):
    """
    User logout endpoint to invalidate token.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Logout success message
    """
    try:
        # Extract token from Authorization header or custom header
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
        else:
            # Check for custom auth token header
            token = request.headers.get("X-Auth-Token") or request.headers.get("authToken")
        
        # Remove token from token-username mapping
        if token:
            with token_username_map_lock:
                if token in token_username_map:
                    del token_username_map[token]
        
        return {"success": True, "message": "Logged out successfully"}
    except Exception as e:
        logger.exception("Logout error")
        raise HTTPException(
            status_code=500, 
            detail=f"Logout failed: {str(e)}"
        )


@app.post("/cleanup-expired-files")
async def cleanup_expired_files():
    """
    Cleanup expired files from storage (administrative endpoint).
    
    Returns:
        Cleanup result
    """
    try:
        _cleanup_expired_files()
        return {
            "status": "success",
            "message": "Expired files cleaned up successfully"
        }
    except Exception as e:
        logger.exception("Failed to cleanup expired files")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to cleanup expired files: {str(e)}"
        )
