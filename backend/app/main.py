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
from typing import Any, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware

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
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ quick health
@app.get("/health")
def health():
    return {"ok": True}

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

        # === Call the RAG orchestrator ===
        output = rag_answer(question.question, selected_db=question.selected_db)

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
        display_mode = output.get("display_mode", "table")
        results = {
            "columns": (output.get("results") or {}).get("columns", []),
            "rows": (output.get("results") or {}).get("rows", []),
            "row_count": (output.get("results") or {}).get("row_count", 0),
        }

        # ---------------------------
        # Feedback IDs (same as your legacy code)
        # ---------------------------
        ids = None
        if FEEDBACK_STORE_AVAILABLE:
            try:
                schema_text = "\n\n".join(output.get("schema_context", [])) if output.get("schema_context") else None
                schema_ids = output.get("schema_context_ids") or None

                turn_id = insert_turn(
                    source_db_id=question.selected_db,
                    client_ip=request.client.host if request and request.client else None,
                    user_question=question.question,
                    schema_context_text=schema_text,
                    schema_context_ids=schema_ids,
                    meta={"ui": "web", "mode": "non_stream", "display_mode": display_mode},
                )

                sql_sample_id = None
                if output.get("sql"):
                    sql_sample_id = insert_sql_sample(
                        turn_id=turn_id,
                        model_name=OLLAMA_SQL_MODEL,
                        prompt_text=None,
                        sql_text=output["sql"],
                        display_mode=display_mode,
                    )

                summary_sample_id = None
                if output.get("summary"):
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
            "summary": output.get("summary", ""),
            "sql": output.get("sql"),
            "display_mode": display_mode,
            "results": results,
            "schema_context": output.get("schema_context", []),
            "schema_context_ids": output.get("schema_context_ids", []),
        }
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
        return {"status": "ok", "feedback_id": fid}
    except Exception as e:
        logging.getLogger(__name__).error(f"[feedback] insert_feedback failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": "failed to store feedback"})

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
