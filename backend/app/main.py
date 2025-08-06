from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os
import logging
import json

from fastapi.middleware.cors import CORSMiddleware
from app.query_engine import process_question, run_sql_streaming, process_question_streaming  # ✅ added new import
from app.summarizer import stream_summary  # ✅ NEW import for summary streaming

app = FastAPI()
logger = logging.getLogger(__name__)

# ---------------------------
# Enable CORS
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Load templates (optional HTML UI)
# ---------------------------
templates_dir = Path("templates")
if not templates_dir.exists():
    os.makedirs(templates_dir, exist_ok=True)

try:
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
except ImportError:
    logger.error("Jinja2 not found. HTML fallback disabled.")
    templates = None

# ---------------------------
# Pydantic request model
# ---------------------------
class Question(BaseModel):
    question: str

# ---------------------------
# Root route for UI
# ---------------------------
@app.get("/", response_class=HTMLResponse if templates else JSONResponse)
async def root(request: Request):
    if templates:
        return templates.TemplateResponse("chat.html", {"request": request})
    return JSONResponse(content={"message": "Oracle SQL Assistant is running."})

# ---------------------------
# Standard POST /chat endpoint
# ---------------------------
@app.post("/chat")
async def chat_api(question: Question):
    try:
        if not question.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        output = process_question(question.question)

        if "error" in output:
            return {
                "status": "error",
                "message": output["error"],
                "sql": output.get("sql"),
                "suggestions": [
                    "Try rephrasing your question",
                    "Be specific about the table or field names",
                    "Use keywords like total, list, show, by"
                ]
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
            "schema_context": output.get("schema_context", [])
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

# ---------------------------
# ✅ Updated: GET /chat/stream — streams live status and results
# ---------------------------
@app.get("/chat/stream")
async def chat_stream_api(request: Request):
    question = request.query_params.get("question", "").strip()
    if not question:
        async def error_gen():
            yield "data: " + json.dumps({"error": "Missing question"}) + "\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    def stream_generator():
        try:
            for chunk in process_question_streaming(question):
                yield f"data: {json.dumps(chunk)}\n\n"

            # ✅ Use a final valid JSON signal
            yield f"data: {json.dumps({'phase': 'Done'})}\n\n"

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'error': f'Streaming failed: {str(e)}'})}\n\n"


    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# ---------------------------
# ✅ NEW: GET /summary/stream — streams summary tokens
# ---------------------------
@app.get("/summary/stream")
async def summary_stream(question: str):
    try:
        return StreamingResponse(stream_summary(question), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Streaming summary error: {e}")
        async def error_gen():
            yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")
