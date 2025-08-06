import cx_Oracle
from app.config import VECTOR_DB
from contextlib import contextmanager
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

@contextmanager
def connect_to_source(cfg: Dict[str, Any]):
    """Connect to source Oracle database"""
    dsn = cx_Oracle.makedsn(cfg["host"], cfg["port"], service_name=cfg["service"])
    conn = None
    try:
        conn = cx_Oracle.connect(
            user=cfg["user"],
            password=cfg["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True
        )
        yield conn
    except cx_Oracle.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()

@contextmanager
def connect_vector():
    """Connect to vector database with PDB support"""
    dsn = cx_Oracle.makedsn(
        VECTOR_DB["host"],
        VECTOR_DB["port"],
        service_name=VECTOR_DB["service_name"]
    )
    conn = None
    try:
        conn = cx_Oracle.connect(
            user=VECTOR_DB["user"],
            password=VECTOR_DB["password"],
            dsn=dsn,
            encoding="UTF-8",
            nencoding="UTF-8",
            threaded=True
        )

        # Switch to PDB if specified
        if "pdb" in VECTOR_DB and VECTOR_DB["pdb"]:
            with conn.cursor() as cur:
                cur.execute(f"ALTER SESSION SET CONTAINER = {VECTOR_DB['pdb']}")

        yield conn
    except cx_Oracle.Error as e:
        logger.error(f"Vector DB connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()
