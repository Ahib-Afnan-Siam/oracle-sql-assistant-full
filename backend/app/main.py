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
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
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
from typing import Any, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
from app.config import (
    OLLAMA_SQL_MODEL, 
    OLLAMA_ANALYTICAL_MODEL,
    COLLECT_TRAINING_DATA 
)


# Oracle error type (be tolerant to either driver)
try:
    from oracledb import DatabaseError as OraDatabaseError
except Exception:
    try:
        from cx_Oracle import DatabaseError as OraDatabaseError
    except Exception:
        class OraDatabaseError(Exception):
            pass

# === Use the RAG orchestrator ===
from app.rag_engine import answer as rag_answer

# Optional: vector search utility still useful for debugging endpoints if you add any later
from app.vector_store_chroma import hybrid_schema_value_search  # noqa: F401 (kept for parity)

# Optional feedback DB exports
from app.db_connector import connect_feedback

# Phase 5.2: Import quality metrics system
try:
    from app.hybrid_data_recorder import hybrid_data_recorder
    QUALITY_METRICS_AVAILABLE = True
except ImportError:
    QUALITY_METRICS_AVAILABLE = False

# ---------------------------
# optional: model names (used when inserting samples)
# ---------------------------
try:
    from app.config import OLLAMA_SQL_MODEL, OLLAMA_ANALYTICAL_MODEL
except Exception:
    OLLAMA_SQL_MODEL = "unknown-sql-model"
    OLLAMA_ANALYTICAL_MODEL = "unknown-summary-model"

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
    from app.feedback_store import (
        insert_turn,
        insert_sql_sample,
        update_sql_sample,
        insert_summary_sample,
        update_summary_sample,
        insert_feedback,
    )
    FEEDBACK_STORE_AVAILABLE = True
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
    level_name = os.getenv("LOG_LEVEL", "DEBUG")  # default DEBUG while you’re tuning
    level = getattr(logging, level_name.upper(), logging.INFO)
    fmt = "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s"
    logging.basicConfig(level=level, format=fmt)
    # crank up our package loggers explicitly
    for name in ("app", "app.rag_engine", "app.query_engine", "app.ollama_llm", "app.db_connector"):
        logging.getLogger(name).setLevel(level)

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
    filename = filename.lstrip('.\/')
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
                    b'exec', b'eval', b'import', b'os\.', b'subprocess', 
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

# Simple timing middleware to see every request
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger = logging.getLogger("app.http")
    t0 = time.perf_counter()
    logger.info("→ %s %s", request.method, request.url.path)
    try:
        resp = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        logger.info("← %s %s %s %.1fms", request.method, request.url.path, resp.status_code, ms)
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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ✅ quick health
@app.get("/health")
def health():
    """Enhanced health check with quality metrics summary."""
    health_data = {"ok": True, "timestamp": time.time()}
    
    # Add quality metrics summary if available
    if QUALITY_METRICS_AVAILABLE:
        try:
            from app.hybrid_data_recorder import get_quality_dashboard
            quality_summary = get_quality_dashboard(time_window_hours=1)  # Last hour
            health_data["quality_metrics"] = {
                "system_health": quality_summary.get("system_health", "unknown"),
                "overall_score": quality_summary.get("overall_score", 0.0),
                "total_queries_last_hour": quality_summary.get("performance_indicators", {}).get("total_queries", 0),
                "alerts_count": len(quality_summary.get("alerts", []))
            }
        except Exception as e:
            health_data["quality_metrics"] = {"error": str(e)}
    
    return health_data

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
    # Frontend now sends "" for General, "source_db_1" for SOS, "source_db_2" for Test DB.
    # Keep optional & permissive for backward-compatibility with aliases.
    selected_db: Optional[str] = ""
    # New explicit mode values: "General" | "SOS" | "Test DB" (case-insensitive)
    mode: str = "General"

class FeedbackIn(BaseModel):
    turn_id: int
    task_type: str = Field(pattern="^(sql|summary|overall)$")
    feedback_type: str = Field(pattern="^(good|wrong|needs_improvement)$")
    sql_sample_id: Optional[int] = None
    summary_sample_id: Optional[int] = None
    comment: Optional[str] = None
    labeler_role: Optional[str] = "end_user"

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
    Normalize inbound mode strings to one of: 'General', 'SOS', 'Test DB'
    Accepts legacy/loose inputs like 'database', 'sos', 'test', 'test_db'.
    """
    if not mode:
        return "General"
    m = mode.strip().lower()
    if m in ("general", "gen"):
        return "General"
    if m in ("sos", "source_db_1", "db1"):
        return "SOS"
    if m in ("test db", "test_db", "test", "source_db_2", "db2"):
        return "Test DB"
    if m in ("database", "db"):  # legacy "database" → treat as DB mode but require a db selection
        # fallback: if no DB provided we’ll handle below, else keep selection
        return "SOS" if os.getenv("DEFAULT_DB_MODE", "sos").lower() == "sos" else "Test DB"
    return "General"

def _normalize_selected_db(selected_db: Optional[str], mode: str) -> str:
    """
    Normalize DB aliases to canonical IDs or empty for General.
    """
    if mode == "General":
        return ""
    # If caller supplied an explicit DB, normalize it; else infer from mode
    if not selected_db or not selected_db.strip():
        return "source_db_1" if mode == "SOS" else "source_db_2"
    s = selected_db.strip().lower()
    if s in ("sos", "source_db_1", "db1"):
        return "source_db_1"
    if s in ("test", "test_db", "source_db_2", "db2"):
        return "source_db_2"
    # Allow already-canonical values to pass through
    if selected_db in ("source_db_1", "source_db_2"):
        return selected_db
    # Unknown → leave empty to force General-like behavior (safe)
    return ""

# ---------------------------
# Oracle exception handler (expanded map)
# ---------------------------
@app.exception_handler(OraDatabaseError)
async def oracle_error_handler(request: Request, exc: OraDatabaseError):
    text = str(exc)
    m = re.search(r"(ORA-\d{5})", text)
    error_code = m.group(1) if m else "ORA-00000"
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

# ---------------------------
# Chat -> uses new RAG pipeline, preserves envelope + feedback IDs
# ---------------------------
@app.post("/chat")
async def chat_api(question: Question, request: Request):
    try:
        if not question.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        # Determine & normalize mode/DB
        mode_in = question.mode
        selected_db_in = question.selected_db
        mode = _normalize_mode(mode_in)  # 'General' | 'SOS' | 'Test DB'
        selected_db = _normalize_selected_db(selected_db_in, mode)  # "" | source_db_1 | source_db_2

        # === Call the RAG orchestrator with training data parameters ===
        output = await rag_answer(
            question.question, 
            selected_db=selected_db,
            mode=mode,  # Pass the new mode parameter
            # Phase 5: Pass training data collection parameters for hybrid processing
            session_id=generate_session_id(request),
            client_ip=request.client.host if request and request.client else None,
            user_agent=request.headers.get('user-agent') if request and request.headers else None
        )

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
                enhanced_meta = {
                    "ui": "web", 
                    "mode": "non_stream", 
                    "display_mode": display_mode,
                    # Phase 4.2: Add hybrid processing metadata to feedback
                    "hybrid_processing": bool(hybrid_meta),
                    "processing_mode": hybrid_meta.get("processing_mode") if hybrid_meta else None,
                    "model_used": hybrid_meta.get("model_used") if hybrid_meta else None,
                    "selection_reasoning": hybrid_meta.get("selection_reasoning") if hybrid_meta else None,
                    "processing_time_ms": (hybrid_meta.get("processing_time", 0.0) * 1000) if hybrid_meta else 0.0,
                    "local_confidence": hybrid_meta.get("local_confidence") if hybrid_meta else None,
                    "api_confidence": hybrid_meta.get("api_confidence") if hybrid_meta else None,
                    # Phase 5: Add training data collection metadata
                    "training_data_recorded": hybrid_meta.get("training_data_recorded", False) if hybrid_meta else False,
                    "classification_time_ms": hybrid_meta.get("classification_time_ms", 0.0) if hybrid_meta else 0.0,
                    "sql_execution_time_ms": hybrid_meta.get("sql_execution_time_ms", 0.0) if hybrid_meta else 0.0,
                    "sql_execution_success": hybrid_meta.get("sql_execution_success", False) if hybrid_meta else False
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
    # minimal validation (same as before)
    if payload.task_type == "sql" and not payload.sql_sample_id:
        return JSONResponse(status_code=400, content={"error": "sql_sample_id required"})
    if payload.task_type == "summary" and not payload.summary_sample_id:
        return JSONResponse(status_code=400, content={"error": "summary_sample_id required"})
    if payload.feedback_type == "needs_improvement" and not (payload.comment and payload.comment.strip()):
        return JSONResponse(status_code=400, content={"error": "comment required for needs_improvement"})

    try:
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
            },
        )
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
        quality_report = hybrid_data_recorder.get_quality_metrics(time_window)
        
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
        success_metrics = hybrid_data_recorder.get_success_rates(time_window)
        
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
        satisfaction_metrics = hybrid_data_recorder.get_user_satisfaction_metrics(time_window)
        
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
        # Test with a short time window to minimize load
        test_results = test_quality_metrics_system(time_window)
        
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
        from app.hybrid_processor import HybridProcessor
        processor = HybridProcessor()
        test_results = processor.test_training_data_collection()
        
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
        from app.hybrid_processor import HybridProcessor
        processor = HybridProcessor()
        status_info = processor.get_training_data_status()
        
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        performance_comparison = hybrid_data_recorder.quality_analyzer.analyze_performance_comparison(time_window)
        
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        model_strengths = hybrid_data_recorder.quality_analyzer.identify_model_strengths(time_window)
        
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        preference_patterns = hybrid_data_recorder.quality_analyzer.analyze_user_preference_patterns(time_window)
        
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        insights = hybrid_data_recorder.quality_analyzer.generate_learning_insights(time_window)
        
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
        from app.hybrid_data_recorder import test_continuous_learning_system
        test_results = test_continuous_learning_system(time_window)
        
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
        from app.hybrid_processor import HybridProcessor
        processor = HybridProcessor()
        test_results = processor.test_continuous_learning_system(time_window)
        
        return {
            "status": "success",
            "data": test_results,
            "metadata": {
                "endpoint": "learning-test-processor",
                "version": "1.0",
                "generated_at": test_results.get("data", {}).get("timestamp") if test_results.get("data") else None,
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        samples = hybrid_data_recorder.quality_analyzer.identify_high_quality_samples(time_window, min_quality)
        
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
        from app.hybrid_data_recorder import hybrid_data_recorder
        dataset = hybrid_data_recorder.quality_analyzer.create_training_dataset(dataset_type, time_window)
        
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
        from app.hybrid_processor import HybridProcessor
        processor = HybridProcessor()
        samples = processor.get_high_quality_samples(time_window, min_quality)
        
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
        from app.hybrid_processor import HybridProcessor
        processor = HybridProcessor()
        dataset = processor.create_training_dataset(dataset_type, time_window)
        
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

@app.post("/upload-file", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...), request: Request = None):
    """
    Upload a file for analysis.
    
    Args:
        file: The file to upload
        request: FastAPI Request object for rate limiting
        
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
        filename = _sanitize_filename(file.filename)
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

@app.post("/analyze-file")
async def analyze_file(request: FileAnalysisRequest, req: Request = None):
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
        
        # Use OpenRouter client to call Gemini Flash 1.5
        from app.openrouter_client import OpenRouterClient, OpenRouterError
        try:
            client = OpenRouterClient()
            # Use Gemini Flash 1.5 model specifically for file analysis
            model = "google/gemini-flash-1.5"
            
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
                    detail=f"Failed to analyze file with Gemini Flash 1.5: {response.error}"
                )
                
        except OpenRouterError as e:
            logger.exception("OpenRouter API error")
            raise HTTPException(
                status_code=500, 
                detail=f"OpenRouter API error: {str(e)}"
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
