# app/vector_store_chroma.py
# Vector store helpers for ChromaDB (with query-time synonym expansion)
import logging
import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings
from chromadb.telemetry.posthog import Posthog

from app.embeddings import get_embedding

# ---- Telemetry off / monkey patch ----
def safe_capture(self, *args, **kwargs):
    # Newer Chroma calls capture with variable args; just swallow.
    return None

Posthog.capture = safe_capture
os.environ["ANONYMIZED_TELEMETRY"] = "False"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# Environment switches
# =========================
ENABLE_QUERY_SYNONYMS = os.getenv("ENABLE_QUERY_SYNONYMS", "true").lower() == "true"

# =========================
# Per-DB Chroma client
# =========================
def get_chroma_client(selected_db: str) -> chromadb.Client:
    return chromadb.PersistentClient(
        path=f"chroma_storage/{selected_db}",
        settings=Settings(anonymized_telemetry=False)
    )

# =========================
# Optional synonyms used ONLY at query-time (no indexing cost)
# =========================
COLUMN_SYNONYMS = {
    "DEPTNO": ["department number", "dept no", "dept id"],
    "DNAME": ["department name", "dept name"],
    "LOC": ["department location", "location of department", "location"],
    "EMPNO": ["employee id", "emp id", "employee number"],
    "ENAME": ["employee name", "name", "emp name"],
    "JOB": ["job title", "designation", "role", "position"],
    "MGR": ["manager id", "supervisor id"],
    "HIREDATE": ["hire date", "joining date", "date of hire"],
    "SAL": ["salary", "pay", "monthly salary"],
    "COMM": ["commission", "bonus"],
    "TASK_NAME": ["task name", "full task name"],
    "TASK_SHORT_NAME": ["task short name", "task code"],
    "TASK_TYPE": ["task type", "task category"],
    "STATUS_ACTIVE": ["status", "active flag", "is active"],
    "TASK_GROUP": ["task group", "group name"],
    "TASK_OWNER": ["task owner", "responsible person"],
    "LOCATION_NAME": ["location name"],
    "BU_NAME": ["business unit", "business unit name", "bu"],
    "SECTION_NAME": ["section", "section name"],
    "LINE_NAME": ["line", "production line", "sewing line"],
    "TOTAL_PRESENTS": ["attendance", "presents"],
    "OT_HOUR": ["overtime", "ot hours"],
    "OT_AMOUNT": ["overtime pay", "ot payment"],
    "BUYER_NAME": ["buyer", "customer"],
    "STYLE": ["garment style", "style"],
    "POQTY": ["po quantity", "order quantity", "poqty"],
    "SOUTPUT": ["output", "sewing output", "soutput"],
    "SHIPQTY": ["shipment quantity", "shipped qty", "shipqty"],
    "DEFECT_QTY": ["defects", "defect quantity"],
    "PRODUCTION_QTY": ["produced quantity", "production qty"],
    "FLOOR_EF": ["efficiency", "floor efficiency"],
    "CM": ["cost of manufacturing"],
    "SMV": ["standard minute value", "smv"],
    "FULL_NAME": ["name", "full name"],
    "EMAIL_ADDRESS": ["email", "email address"],
    "IS_ACTIVE": ["status", "active"],
    "PIN": ["pin", "user pin"],
    "LAST_LOGIN": ["last login"]
}

def _contains_phrase(q: str, phrase: str) -> bool:
    return phrase.lower() in q

def expand_query_with_synonyms(query: str) -> str:
    """
    Expand the user query with canonical tokens when a synonym/alias is detected.
    Keeps the index lean and improves recall without reindexing.
    """
    if not ENABLE_QUERY_SYNONYMS or not query:
        return query

    ql = query.lower()
    added = set()
    extras = []

    for canonical, syns in COLUMN_SYNONYMS.items():
        canon_l = canonical.lower()
        if canon_l in ql:
            continue
        if any(_contains_phrase(ql, s.lower()) for s in syns):
            if canonical not in added:
                extras.append(canonical)
                added.add(canonical)

    if not extras:
        return query

    expanded = query + " " + " ".join(extras)
    logger.debug(f"[QuerySynonyms] Expanded query: '{query}' → '{expanded}'")
    return expanded

# =========================
# Core search helpers
# =========================
def search_similar_schema(query: str, selected_db: str, top_k: int = 5) -> List[Dict]:
    client = get_chroma_client(selected_db)
    collection_name = f"schema_docs_{selected_db}"
    collection = client.get_or_create_collection(name=collection_name)

    q_expanded = expand_query_with_synonyms(query)
    query_vector = get_embedding(q_expanded)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas"]  # no "ids" for compatibility
    )

    docs  = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids   = results.get("ids", [[]])[0] if results.get("ids") else [None] * len(docs)

    return [
        {"id": _id, "document": doc, "metadata": meta}
        for _id, doc, meta in zip(ids, docs, metas)
    ]

def search_vector_store_detailed(query: str, selected_db: str, top_k: int = 3) -> List[Dict]:
    client = get_chroma_client(selected_db)
    collection_name = f"schema_docs_{selected_db}"

    # Will create an empty collection if missing (harmless), so queries just return [].
    try:
        collection = client.get_or_create_collection(name=collection_name)
    except Exception as e:
        logger.warning(f"[CHROMA] Could not get/create collection '{collection_name}': {e}")
        return []

    q_expanded = expand_query_with_synonyms(query)
    query_vector = get_embedding(q_expanded)

    try:
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["documents", "distances", "metadatas"]  # ids optional in some versions
        )
    except Exception as e:
        logger.warning(f"[CHROMA] Query failed for '{collection_name}': {e}")
        return []

    docs  = results.get("documents", [[]])[0] if results.get("documents") else []
    dists = results.get("distances", [[]])[0] if results.get("distances") else []
    metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
    ids   = results.get("ids", [[]])[0] if results.get("ids") else [None] * len(docs)

    out: List[Dict] = []
    for doc, dist, meta, _id in zip(docs, dists, metas, ids):
        out.append({
            "id": _id,
            "document": doc,
            "score": dist,
            "metadata": meta
        })
    return out


# ✅ Unified hybrid search used by query_engine.py
def hybrid_schema_value_search(query: str, selected_db: str, top_k: int = 10) -> List[Dict]:
    """
    Simple hybrid: detailed semantic search after query-time expansion.
    If you add keyword/metadata filtering later, integrate here.
    """
    return search_vector_store_detailed(query, selected_db=selected_db, top_k=top_k)

# ✅ Persist to disk (no-op on PersistentClient; keep for compatibility)
def persist_chroma(selected_db: str):
    try:
        client = get_chroma_client(selected_db)
        # Newer Chroma with PersistentClient persists automatically.
        if hasattr(client, "persist"):
            client.persist()  # older versions only
        logger.info(f"[CHROMA] ✅ Changes persisted for DB: {selected_db}")
    except Exception:
        # Swallow quietly; persistence is automatic with PersistentClient
        logger.debug(f"[CHROMA] Persistence handled automatically for {selected_db}")
