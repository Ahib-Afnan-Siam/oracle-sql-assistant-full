# app/main.py
from fastapi import FastAPI, HTTPException, Request
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

configure_logging()

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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    selected_db: str = "source_db_1"

class FeedbackIn(BaseModel):
    turn_id: int
    task_type: str = Field(pattern="^(sql|summary|overall)$")
    feedback_type: str = Field(pattern="^(good|wrong|needs_improvement)$")
    sql_sample_id: Optional[int] = None
    summary_sample_id: Optional[int] = None
    comment: Optional[str] = None
    labeler_role: Optional[str] = "end_user"

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

        # === Call the RAG orchestrator with training data parameters ===
        output = await rag_answer(
            question.question, 
            selected_db=question.selected_db,
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
                    source_db_id=question.selected_db,
                    client_ip=request.client.host if request and request.client else None,
                    user_question=question.question,
                    schema_context_text=schema_text,
                    schema_context_ids=schema_ids,
                    meta=enhanced_meta,
                )

                # Phase 5: Update hybrid processing call with training data parameters
                if hybrid_meta and hybrid_meta.get("training_data_recorded") and COLLECT_TRAINING_DATA:
                    try:
                        # Re-call hybrid processing with actual turn_id for complete training data collection
                        logger.info(f"[MAIN] Updating hybrid training data with turn_id {turn_id}")
                        # Note: This is for future enhancement where we might want to update training data
                        # with the actual turn_id after it's created
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
