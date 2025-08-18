# app/main.py
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from pathlib import Path
import traceback
import os
import logging
import json
import asyncio
import time  # ← added
from typing import Any, Dict, Optional
from fastapi.middleware.cors import CORSMiddleware
from oracledb import DatabaseError
from app.query_engine import process_question, process_question_streaming
from app.summarizer import stream_summary
from app.vector_store_chroma import hybrid_schema_value_search
from app.db_connector import connect_feedback
import csv



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
# ---------------------------
# expected signatures (adjust here if yours differ):
#   insert_turn(source_db_id, client_ip, user_question, schema_context_text:str|None, schema_context_ids:list[str]|None, meta:dict|None) -> int
#   insert_sql_sample(turn_id:int, model_name:str, prompt_text:str|None, sql_text:str|None, display_mode:str|None=None) -> int
#   update_sql_sample(sql_sample_id:int, **cols)
#   insert_summary_sample(turn_id:int, model_name:str, prompt_text:str|None, data_snapshot:str|None, sql_used:str|None, display_mode:str|None=None) -> int
#   update_summary_sample(summary_sample_id:int, **cols)
#   insert_feedback(...)

# ---------------------------
# feedback-store helpers (soft import; fallback to no-ops)
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
except Exception as _e:
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

app = FastAPI()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
    TODO: if you have a schema validator, wire it here.
    """
    return []


@app.exception_handler(DatabaseError)
async def oracle_error_handler(request: Request, exc: DatabaseError):
    error_code = str(exc).split(":")[0]
    return JSONResponse(
        status_code=400,
        content={
            "error": error_code,
            "message": {
                "ORA-00904": "Invalid column name",
                "ORA-01861": "Use TO_DATE(value, 'DD-MON-YYYY') format",
                "ORA-00942": "Table does not exist",
            }.get(error_code, str(exc)),
            "valid_columns": get_valid_columns(),
        },
    )


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
# Routes
# ---------------------------
@app.get("/", response_class=HTMLResponse if templates else JSONResponse)
async def root(request: Request):
    if templates:
        return templates.TemplateResponse("chat.html", {"request": request})
    return JSONResponse(content={"message": "Oracle SQL Assistant is running."})


@app.post("/chat")
async def chat_api(question: Question):
    try:
        if not question.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        output = process_question(question.question, selected_db=question.selected_db)

        if "error" in output:
            return {
                "status": "error",
                "message": output["error"],
                "sql": output.get("sql"),
                "suggestions": [
                    "Try rephrasing your question",
                    "Be specific about the table or field names",
                    "Use keywords like total, list, show, by",
                ],
            }

        return {
            "status": "success",
            "summary": output["summary"],
            "sql": output["sql"],
            "results": {
                "columns": output["results"]["columns"] if "results" in output else [],
                "rows": output["results"]["rows"] if "results" in output else [],
                "row_count": output["results"]["row_count"] if "results" in output else 0,
            },
            "schema_context": output.get("schema_context", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/chat/stream")
async def chat_stream_api(request: Request):
    """
    Streaming pipeline with feedback IDs wired in.
    We *forward* all chunks from process_question_streaming unchanged,
    and we *inject* extra events (turn/sql/summary IDs) at the right times.

    This endpoint avoids assumptions: it observes stages and keys present
    in chunks and persists accordingly. If feedback_store is missing,
    it still streams normally.
    """
    try:
        body = await request.json()
        question = (body.get("question") or "").strip()
        selected_db = body.get("selected_db", "source_db_1")

        if not question:
            async def error_gen():
                yield "data: " + json.dumps({"error": "Missing question"}) + "\n\n"
            return StreamingResponse(
                error_gen(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        async def stream_generator():
            # ----- local state we will fill as we go -----
            turn_id: Optional[int] = None
            sql_sample_id: Optional[int] = None
            summary_sample_id: Optional[int] = None

            schema_chunks: list[str] = []
            schema_ids: list[str] = []
            client_ip = request.client.host if request and request.client else None

            # capture SQL phase
            sql_text_generated: Optional[str] = None
            sql_text_final: Optional[str] = None
            sql_prompt: Optional[str] = None
            display_mode: Optional[str] = None
            validation_ok: Optional[str] = None
            execution_ok: Optional[str] = None
            error_code: Optional[str] = None
            row_count: int = 0

            # capture rows/columns so we can build a snapshot if needed
            columns: list[str] = []
            rows: list[list[Any]] = []

            # capture summary
            summary_started = False
            summary_text_buf: list[str] = []
            summary_snapshot: Optional[str] = None
            summary_latency_ms: Optional[int] = None
            summary_prompt: Optional[str] = None

            # track phases for ML/debug  ← NEW
            phase_trace: list[dict] = []

            # handshake so UI shows spinner immediately
            yield f"data: {json.dumps({'phase': 'Connecting...', 'stage': 'handshake'})}\n\n"
            # record handshake in trace  ← NEW
            phase_trace.append({"ts": time.time(), "stage": "handshake"})
            await asyncio.sleep(0)

            # ----- prefetch vector hits for turn context (short + light) -----
            prefetch_schema_chunks: list[str] = []
            prefetch_schema_ids: list[str] = []
            try:
                hits = hybrid_schema_value_search(question, selected_db=selected_db, top_k=5)
                # compact text (docs) and ids (prefer result.id, fallback to metadata.source_table)
                for h in hits:
                    doc = (h.get("document") or "").strip()
                    if doc:
                        prefetch_schema_chunks.append(doc)
                    mid = h.get("id") or (h.get("metadata") or {}).get("source_table") or (h.get("metadata") or {}).get("table")
                    if mid:
                        prefetch_schema_ids.append(str(mid))
            except Exception as e:
                logger.warning(f"[vector] schema hits failed: {e}")

            # caps (keep storage cheap)
            schema_text = "\n\n".join(prefetch_schema_chunks)[:20000]
            schema_id_list = prefetch_schema_ids[:50]

            # Create turn immediately with prefetched context
            try:
                turn_id = insert_turn(
                    selected_db,
                    client_ip,
                    question,
                    schema_text,
                    schema_id_list,
                    meta={"ui": "web"} if FEEDBACK_STORE_AVAILABLE else None,
                )
            except Exception as e:
                logger.warning(f"[feedback] insert_turn failed: {e}")
                turn_id = None

            if turn_id:
                yield f"data: {json.dumps({'stage':'turn_ready','ids':{'turn_id':turn_id}})}\n\n"

            # helper: compact result table snapshot (≤50 rows, ≤~200k chars)
            def tiny_result_table_json(cols: list[str], rs: list[list[Any]], max_rows: int = 50, max_chars: int = 200_000) -> str:
                if not cols:
                    return ""
                payload = {"columns": cols, "rows": rs[:max_rows]}
                s = json.dumps(payload, ensure_ascii=False)
                if len(s) > max_chars:
                    s = s[:max_chars]  # hard cap; optional: add "…"
                return s

            # helper: build snapshot like summarizer._pipe_snapshot expects (simple)
            def build_snapshot(max_rows: int = 50) -> str:
                if not columns:
                    return ""
                head = [" | ".join(columns)]
                sample = rows[:max_rows]
                for r in sample:
                    # convert None to empty + stringify
                    vals = ["" if v is None else str(v) for v in r]
                    head.append(" | ".join(vals))
                return "\n".join(head)

            try:
                async for chunk in process_question_streaming(question, selected_db=selected_db):
                    # -------- observe & persist along the way ----------

                    # record any stage/phase the engine reports  ← NEW
                    if isinstance(chunk, dict):
                        stage = chunk.get("stage")
                        phase = chunk.get("phase")
                        if stage or phase:
                            phase_trace.append({
                                "ts": time.time(),
                                "stage": stage,
                                "phase": phase,
                                "row_count": chunk.get("results", {}).get("row_count")
                                            if isinstance(chunk.get("results"), dict) else None,
                                "error": chunk.get("error")
                            })

                    # pass through display_mode if present
                    if isinstance(chunk, dict) and chunk.get("display_mode"):
                        display_mode = chunk["display_mode"]

                    # collect schema context if present (fallback for later turn creation if prefetch failed)
                    if "schema_context" in chunk and isinstance(chunk["schema_context"], list):
                        # some implementations send plain strings; keep light
                        for s in chunk["schema_context"]:
                            try:
                                if isinstance(s, dict) and "document" in s:
                                    schema_chunks.append(str(s["document"]))
                                else:
                                    schema_chunks.append(str(s))
                            except Exception:
                                continue

                    if "schema_ids" in chunk and isinstance(chunk["schema_ids"], list):
                        schema_ids = [str(x) for x in chunk["schema_ids"]]

                    # Fallback turn creation if prefetch failed
                    if turn_id is None:
                        # Use stream-collected context if available
                        fallback_schema_text = "\n\n".join(schema_chunks)[:20000] if schema_chunks else ""
                        fallback_schema_ids = [str(x) for x in schema_ids][:50] if schema_ids else []
                        
                        try:
                            turn_id = insert_turn(
                                selected_db,
                                client_ip,
                                question,
                                fallback_schema_text,
                                fallback_schema_ids,
                                meta={"ui": "web"} if FEEDBACK_STORE_AVAILABLE else None,
                            )
                        except Exception as e:
                            logger.warning(f"[feedback] insert_turn fallback failed: {e}")
                            turn_id = None
                        if turn_id:
                            yield f"data: {json.dumps({'stage':'turn_ready','ids':{'turn_id':turn_id}})}\n\n"

                    # SQL generation observed
                    if chunk.get("stage") == "sql_ready" or "sql" in chunk:
                        sql_text_generated = chunk.get("sql") or sql_text_generated
                        # try capture any prompt key if you emit it
                        sql_prompt = chunk.get("prompt") or chunk.get("sql_prompt") or sql_prompt
                        if turn_id and sql_sample_id is None:
                            try:
                                sql_sample_id = insert_sql_sample(
                                    turn_id, OLLAMA_SQL_MODEL, sql_prompt, sql_text_generated, display_mode=display_mode
                                )
                                yield f"data: {json.dumps({'stage':'sql_sample_ready','ids':{'turn_id':turn_id,'sql_sample_id':sql_sample_id}})}\n\n"
                            except Exception as e:
                                logger.warning(f"[feedback] insert_sql_sample failed: {e}")

                    # collect columns/rows to compute row_count & snapshot
                    if "columns" in chunk and isinstance(chunk["columns"], list):
                        columns = [str(c) for c in chunk["columns"]]
                    if "rows" in chunk and isinstance(chunk["rows"], list):
                        # append stream rows
                        for r in chunk["rows"]:
                            rows.append([safe_json(v) for v in r])

                    # partial_results / results envelopes
                    if "partial_results" in chunk and isinstance(chunk["partial_results"], dict):
                        pr = chunk["partial_results"]
                        if isinstance(pr.get("rows"), list):
                            for r in pr["rows"]:
                                rows.append([safe_json(v) for v in r])
                    if "results" in chunk and isinstance(chunk["results"], dict):
                        res = chunk["results"]
                        if isinstance(res.get("columns"), list):
                            columns = [str(c) for c in res["columns"]]
                        if isinstance(res.get("rows"), list):
                            for r in res["rows"]:
                                rows.append([safe_json(v) for v in r])

                    # validation / execution status
                    if chunk.get("stage") == "validate_ok":
                        validation_ok = "Y"
                    if chunk.get("error"):
                        # best-effort ORA code extraction
                        msg = str(chunk.get("error"))
                        for part in msg.split():
                            if part.startswith("ORA-"):
                                error_code = part
                                break
                        execution_ok = "N"

                    # parsing means we likely have final SQL (some engines echo it here)
                    if chunk.get("stage") == "parsing" and "sql" in chunk:
                        sql_text_final = chunk["sql"]

                    # if we reach a results object with row_count
                    if "results" in chunk and isinstance(chunk["results"], dict):
                        rc = chunk["results"].get("row_count")
                        if isinstance(rc, int):
                            row_count = rc

                    # When execution is clearly done (stage 'done' or we have rows/columns),
                    # update the SQL sample once (idempotent guard).  ← MODIFIED
                    if sql_sample_id and (chunk.get("stage") in ("done",) or ("results" in chunk)):
                        try:
                            # prefer final, fall back to generated
                            if sql_text_final is None and sql_text_generated is not None:
                                sql_text_final = sql_text_generated

                            # consistent row_count
                            if row_count == 0 and rows:
                                row_count = len(rows)

                            # always produce non-null JSON strings
                            result_json = tiny_result_table_json(columns, rows, max_rows=50, max_chars=200_000)
                            if not result_json:
                                # empty but non-null structure for ML pipelines
                                result_json = json.dumps({"columns": columns or [], "rows": []}, ensure_ascii=False)

                            normalized_sql = sql_text_final or (sql_text_generated or "")

                            # include a compact phase trace for training/debug
                            phase_trace_json = json.dumps(phase_trace, ensure_ascii=False)

                            update_sql_sample(
                                sql_sample_id,
                                SQL_TEXT_FINAL=sql_text_final,
                                VALIDATION_OK=validation_ok or "Y",
                                EXECUTION_OK=execution_ok or "Y",
                                ROW_COUNT=row_count,
                                ERROR_CODE=error_code,
                                NORMALIZED_SQL=normalized_sql,             # ← never NULL
                                RESULT_TABLE_JSON=result_json,             # ← never NULL
                                PHASE_TRACE_JSON=phase_trace_json,         # ← NEW, never NULL
                            )
                        except Exception as e:
                            logger.warning(f"[feedback] update_sql_sample failed: {e}")

                    # summary start → insert summary sample with snapshot
                    if chunk.get("stage") == "summary_start" and not summary_started:
                        summary_started = True
                        # try to use provided snapshot if any; otherwise build from rows/columns
                        summary_snapshot = chunk.get("snapshot") or build_snapshot(max_rows=120)
                        # NEW: capture the prompt if the upstream includes it
                        summary_prompt = chunk.get("prompt") or chunk.get("summary_prompt") or summary_prompt

                        try:
                            if turn_id:
                                summary_sample_id = insert_summary_sample(
                                    turn_id,
                                    OLLAMA_ANALYTICAL_MODEL,
                                    summary_prompt,
                                    summary_snapshot,
                                    sql_text_final or sql_text_generated,
                                    display_mode=display_mode,
                                )
                                yield f"data: {json.dumps({'stage':'summary_sample_ready','ids':{'turn_id':turn_id,'summary_sample_id':summary_sample_id}})}\n\n"
                        except Exception as e:
                            logger.warning(f"[feedback] insert_summary_sample failed: {e}")

                    # stream summary text chunks (standard in your UI: chunk['summary'])
                    if "summary" in chunk and isinstance(chunk["summary"], str):
                        summary_text_buf.append(chunk["summary"])

                    # latencies if your engine emits them
                    if "latency_ms" in chunk and isinstance(chunk["latency_ms"], int):
                        summary_latency_ms = chunk["latency_ms"]

                    # forward the original chunk to the client
                    yield f"data: {json.dumps(chunk, default=safe_json)}\n\n"
                    await asyncio.sleep(0)

                # after loop completes, finalize summary sample (if any)
                final_summary = "\n\n".join(summary_text_buf).strip() if summary_text_buf else None
                if summary_sample_id and (final_summary or summary_latency_ms is not None):
                    try:
                        update_summary_sample(
                            summary_sample_id,
                            SUMMARY_TEXT=final_summary,
                            LATENCY_MS=summary_latency_ms,
                        )
                    except Exception as e:
                        logger.warning(f"[feedback] update_summary_sample failed: {e}")

                # -------- Final safety update to ensure non-null fields for ML  ← NEW --------
                if sql_sample_id:
                    try:
                        # prefer final, fall back to generated
                        final_sql = sql_text_final or (sql_text_generated or "")
                        # ensure row_count if still 0 and we buffered rows
                        final_row_count = row_count or (len(rows) if rows else 0)

                        # always non-null result json
                        result_json = tiny_result_table_json(columns, rows, max_rows=50, max_chars=200_000)
                        if not result_json:
                            result_json = json.dumps({"columns": columns or [], "rows": []}, ensure_ascii=False)

                        phase_trace_json = json.dumps(phase_trace, ensure_ascii=False)

                        update_sql_sample(
                            sql_sample_id,
                            SQL_TEXT_FINAL=final_sql or None,
                            NORMALIZED_SQL=final_sql,
                            RESULT_TABLE_JSON=result_json,
                            ROW_COUNT=final_row_count,
                            PHASE_TRACE_JSON=phase_trace_json,
                            VALIDATION_OK=validation_ok or "Y",
                            EXECUTION_OK=execution_ok or ("N" if error_code else "Y"),
                            ERROR_CODE=error_code,
                        )
                    except Exception as e:
                        logger.warning(f"[feedback] final update_sql_sample failed: {e}")
                # -----------------------------------------------------------------------------

                # finally, announce IDs so the UI can attach feedback
                if turn_id:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "stage": "feedback_ids",
                                "ids": {
                                    "turn_id": turn_id,
                                    "sql_sample_id": sql_sample_id,
                                    "summary_sample_id": summary_sample_id,
                                },
                            },
                            default=safe_json,
                        )
                        + "\n\n"
                    )

            except Exception as e:
                logger.error(f"Streaming error: {e}", exc_info=True)
                error_data = {
                    "error": f"Streaming failed: {str(e)}",
                    "detail": traceback.format_exc(),
                }
                yield f"data: {json.dumps(error_data, default=safe_json)}\n\n"

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Streaming endpoint failed: {e}", exc_info=True)

        async def error_gen():
            yield "data: " + json.dumps({"error": "Internal server error", "detail": str(e)}) + "\n\n"

        return StreamingResponse(
            error_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

@app.get("/summary/stream")
async def summary_stream(question: str):
    try:
        return StreamingResponse(stream_summary(question), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Streaming summary error: {e}")

        async def error_gen():
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"

        return StreamingResponse(error_gen(), media_type="text/event-stream")


# ---------------------------
# POST /feedback
# ---------------------------
@app.post("/feedback")
async def post_feedback(payload: FeedbackIn, request: Request):
    # minimal validation
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
        logger.error(f"[feedback] insert_feedback failed: {e}", exc_info=True)
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
        # simple stringify; avoid commas/newlines surprises by using csv module
        return str(v)

    # Use csv module to quote safely
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)

    rows_fetched = 0
    while True:
        batch = cur.fetchmany(1000)
        if not batch:
            break
        for r in batch:
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([_clean(v) for v in r])
            yield buf.getvalue()
            rows_fetched += 1

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
