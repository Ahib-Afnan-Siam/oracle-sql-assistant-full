# app/feedback_store.py
import json
import logging
from typing import Optional, Dict, Any

# We don't assume which driver you used in connect_feedback():
# This module will adapt to whichever cursor it receives at runtime.
from app.db_connector import connect_feedback

logger = logging.getLogger(__name__)


def _json_dumps(obj: Any, default_empty="{}") -> str:
    """Compact JSON for CLOB columns. Always returns a string."""
    if obj is None:
        return default_empty
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps(str(obj), ensure_ascii=False)


def _make_number_var(cursor):
    """
    Create an Oracle NUMBER out-bind variable on *this* cursor,
    regardless of whether the driver is `oracledb` or `cx_Oracle`.
    """
    # Try oracledb first
    try:
        import oracledb as _ora
        # Prefer DB_TYPE_NUMBER if available (thin mode)
        typ = getattr(_ora, "DB_TYPE_NUMBER", None) or getattr(_ora, "NUMBER", None)
        if typ is not None:
            return cursor.var(typ)
    except Exception:
        pass

    # Fallback to cx_Oracle
    try:
        import cx_Oracle as _cx
        typ = getattr(_cx, "DB_TYPE_NUMBER", None) or getattr(_cx, "NUMBER", None)
        if typ is not None:
            return cursor.var(typ)
    except Exception:
        pass

    # Last resort (should rarely happen). Some drivers accept Python float for NUMBER.
    # If this still fails, the caller will log the exception.
    logger.warning("[feedback] Could not resolve Oracle NUMBER type; falling back to float.")
    return cursor.var(float)


def _insert_with_returning(cursor, sql: str, binds: Dict[str, Any]) -> int:
    """
    Execute an INSERT ... RETURNING ID INTO :new_id and return the integer id.
    Works with both cx_Oracle and oracledb cursors.
    """
    out_id = _make_number_var(cursor)
    bind_params = dict(binds)
    bind_params["new_id"] = out_id
    cursor.execute(sql, bind_params)

    val = out_id.getvalue()

    # cx_Oracle often returns a 1-element list for RETURNING vars.
    # oracledb may return a scalar. Handle both safely.
    if isinstance(val, (list, tuple)):
        val = val[0] if val else None

    return int(val) if val is not None else 0



# ---------------------------
# TURN
# ---------------------------
def insert_turn(
    source_db_id: str,
    client_ip: Optional[str],
    user_question: str,
    schema_context_text: str = "",
    schema_context_ids: Optional[list] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Create one AI_TURN row and return its ID.
    """
    with connect_feedback() as conn:
        cur = conn.cursor()
        new_id = _insert_with_returning(
            cur,
            """
            INSERT INTO AI_TURN
              (SOURCE_DB_ID, CLIENT_IP, USER_QUESTION, SCHEMA_CONTEXT_TEXT,
               SCHEMA_CONTEXT_IDS_JSON, META_JSON)
            VALUES
              (:db, :ip, :q, :ctx, :ids, :meta)
            RETURNING ID INTO :new_id
            """,
            {
                "db": source_db_id,
                "ip": client_ip,
                "q": user_question,
                "ctx": schema_context_text or "",
                "ids": _json_dumps(schema_context_ids or [], default_empty="[]"),
                "meta": _json_dumps(meta or {}),
            },
        )
        conn.commit()
        return new_id


# ---------------------------
# SQL SAMPLE
# ---------------------------
def insert_sql_sample(
    turn_id: int,
    model_name: Optional[str],
    prompt: str,
    sql_text: str,
    display_mode: Optional[str] = None,
) -> int:
    """
    Create one AI_SQL_SAMPLE row and return its ID.
    """
    with connect_feedback() as conn:
        cur = conn.cursor()
        new_id = _insert_with_returning(
            cur,
            """
            INSERT INTO AI_SQL_SAMPLE
              (TURN_ID, MODEL_NAME, PROMPT_TEXT, SQL_TEXT, DISPLAY_MODE)
            VALUES
              (:tid, :m, :p, :s, :dm)
            RETURNING ID INTO :new_id
            """,
            {"tid": turn_id, "m": model_name, "p": prompt, "s": sql_text, "dm": display_mode},
        )
        conn.commit()
        return new_id


def update_sql_sample(sample_id: int, **kv):
    """
    Update AI_SQL_SAMPLE by ID. Keys are column names; case-insensitive.
    Example:
      update_sql_sample(id, SQL_TEXT_FINAL=..., VALIDATION_OK='Y', EXECUTION_OK='N', ERROR_CODE='ORA-...')
    """
    if not kv:
        return
    sets = ", ".join(f"{k.upper()} = :{k}" for k in kv.keys())
    binds = {**kv, "id": sample_id}
    with connect_feedback() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE AI_SQL_SAMPLE SET {sets} WHERE ID = :id", binds)
        conn.commit()


# ---------------------------
# SUMMARY SAMPLE
# ---------------------------
def insert_summary_sample(
    turn_id: int,
    model_name: Optional[str],
    prompt: str,
    data_snapshot: str,
    sql_used: Optional[str] = None,
    display_mode: Optional[str] = None,
) -> int:
    """
    Create one AI_SUMMARY_SAMPLE row and return its ID.
    """
    with connect_feedback() as conn:
        cur = conn.cursor()
        new_id = _insert_with_returning(
            cur,
            """
            INSERT INTO AI_SUMMARY_SAMPLE
              (TURN_ID, MODEL_NAME, PROMPT_TEXT, DATA_SNAPSHOT, SQL_USED, DISPLAY_MODE)
            VALUES
              (:tid, :m, :p, :ds, :sqlu, :dm)
            RETURNING ID INTO :new_id
            """,
            {
                "tid": turn_id,
                "m": model_name,
                "p": prompt,
                "ds": data_snapshot,
                "sqlu": sql_used,
                "dm": display_mode,
            },
        )
        conn.commit()
        return new_id


def update_summary_sample(sample_id: int, **kv):
    """
    Update AI_SUMMARY_SAMPLE by ID. Keys are column names; case-insensitive.
    Example:
      update_summary_sample(id, SUMMARY_TEXT=..., LATENCY_MS=1234)
    """
    if not kv:
        return
    sets = ", ".join(f"{k.upper()} = :{k}" for k in kv.keys())
    binds = {**kv, "id": sample_id}
    with connect_feedback() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE AI_SUMMARY_SAMPLE SET {sets} WHERE ID = :id", binds)
        conn.commit()


# ---------------------------
# FEEDBACK
# ---------------------------
# ---------------------------
# FEEDBACK
# ---------------------------
def insert_feedback(
    turn_id: int,
    task_type: str,               # 'sql' | 'summary' | 'overall'
    feedback_type: str,           # 'good' | 'wrong' | 'needs_improvement'
    sql_sample_id: Optional[int] = None,
    summary_sample_id: Optional[int] = None,
    improvement_comment: Optional[str] = None,
    labeler_role: str = "end_user",
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Create one AI_FEEDBACK row and return its ID.
    NOTE: avoid Oracle keywords in bind names (e.g., :comment, :role).
    """
    with connect_feedback() as conn:
        cur = conn.cursor()
        new_id = _insert_with_returning(
            cur,
            """
            INSERT INTO AI_FEEDBACK
              (TURN_ID, TASK_TYPE, FEEDBACK_TYPE, SQL_SAMPLE_ID, SUMMARY_SAMPLE_ID,
               IMPROVEMENT_COMMENT, LABELER_ROLE, META_JSON)
            VALUES
              (:b_tid, :b_task, :b_ft, :b_sid, :b_sumid, :b_impr_comment, :b_labeler_role, :b_meta)
            RETURNING ID INTO :new_id
            """,
            {
                "b_tid": turn_id,
                "b_task": task_type,
                "b_ft": feedback_type,
                "b_sid": sql_sample_id,
                "b_sumid": summary_sample_id,
                "b_impr_comment": improvement_comment,
                "b_labeler_role": labeler_role,
                "b_meta": _json_dumps(meta or {}),
            },
        )
        conn.commit()
        return new_id