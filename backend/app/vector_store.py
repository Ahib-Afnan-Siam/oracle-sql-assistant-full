# app/vector_store.py

import logging
from typing import List
from app.embeddings import get_embedding, truncate_to_tokens
from app.db_connector import connect_vector

logger = logging.getLogger(__name__)

MAX_TOP_K = 3
SCHEMA_CONTEXT_TOKEN_LIMIT = 3000
EMBEDDING_DIMENSIONS = 384  # ✅ Match VECTOR(384)

def get_rich_schema_context(user_query: str, top_k: int = MAX_TOP_K) -> str:
    embedding = get_embedding(user_query)

    with connect_vector() as conn:
        cur = conn.cursor()

        # Build bind placeholders for 384D
        bind_placeholders = ",".join([f":{i+1}" for i in range(EMBEDDING_DIMENSIONS)])
        query = f"""
            SELECT content
            FROM vector_schema_docs
            WHERE VECTOR_DISTANCE(embedding, TO_VECTOR({bind_placeholders}), COSINE) IS NOT NULL
            ORDER BY VECTOR_DISTANCE(embedding, TO_VECTOR({bind_placeholders}), COSINE) ASC
            FETCH FIRST {top_k} ROWS ONLY
        """
        cur.execute(query, embedding)
        rows = cur.fetchall()
        cur.close()

    if not rows:
        logger.warning("[Vector Search] No relevant schema found")
        return ""

    context_parts = []
    for (content,) in rows:
        if not content:
            continue
        text = str(content)
        if 'SAMPLE DATA' in text:
            text = text.split('SAMPLE DATA')[0].strip()
        text = truncate_to_tokens(text, SCHEMA_CONTEXT_TOKEN_LIMIT)
        context_parts.append(text)

    return "\n\n".join(context_parts)

def get_all_schema_tokens() -> List[str]:
    tokens = set()

    with connect_vector() as conn:
        cur = conn.cursor()
        cur.execute("SELECT content FROM vector_schema_docs")

        for (content,) in cur:
            if not content:
                continue
            text = str(content.read()) if hasattr(content, "read") else str(content)
            for line in text.splitlines():
                line = line.strip()
                if line:
                    tokens.add(line)

        cur.close()

    return list(tokens)
