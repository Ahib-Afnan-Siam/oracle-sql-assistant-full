import re
import numpy as np
from typing import List, Sequence
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ✅ Match Oracle VECTOR(384, FLOAT32, DENSE)
EMBEDDING_DIMENSIONS = 384
MAX_TEXT_LENGTH = 10000
LOCAL_MODEL_NAME = "BAAI/bge-small-en"

_local_model = None

def initialize_local_model():
    global _local_model
    if _local_model is None:
        logger.info(f"[EMBEDDINGS] Initializing model: {LOCAL_MODEL_NAME}")
        # If you have GPU: SentenceTransformer(LOCAL_MODEL_NAME, device="cuda")
        _local_model = SentenceTransformer(LOCAL_MODEL_NAME)
    return _local_model

def _truncate(s: str) -> str:
    return str(s)[:MAX_TEXT_LENGTH]

def normalize_embedding(embedding: List[float]) -> List[float]:
    if len(embedding) < EMBEDDING_DIMENSIONS:
        embedding = embedding + [0.0] * (EMBEDDING_DIMENSIONS - len(embedding))
    else:
        embedding = embedding[:EMBEDDING_DIMENSIONS]
    return np.array(embedding, dtype=np.float32).tolist()

def get_local_embedding(text: str) -> List[float]:
    model = initialize_local_model()
    return model.encode(_truncate(text)).tolist()

def get_embedding(text: str) -> List[float]:
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")
    try:
        return normalize_embedding(get_local_embedding(text))
    except Exception as e:
        logger.warning(f"[EMBEDDINGS] Fallback (single) due to: {e}")
        rng = np.random.default_rng()
        return normalize_embedding(rng.normal(0, 0.5, EMBEDDING_DIMENSIONS).tolist())

# ---------- NEW: batched encoders ----------
def encode_texts_batch(texts: Sequence[str], batch_size: int = 64) -> List[List[float]]:
    """
    Efficiently encode a list of texts using SentenceTransformers batching.
    Always returns float32 lists of length EMBEDDING_DIMENSIONS.
    """
    if not texts:
        return []
    model = initialize_local_model()
    cleaned = [_truncate(t if isinstance(t, str) else str(t)) for t in texts]
    try:
        vectors = model.encode(cleaned, batch_size=batch_size, convert_to_numpy=True, normalize_embeddings=False)
        # Ensure shape/length
        out = []
        for v in vectors:
            v = v.tolist()
            if len(v) != EMBEDDING_DIMENSIONS:
                v = normalize_embedding(v)
            out.append(np.array(v, dtype=np.float32).tolist())
        return out
    except Exception as e:
        logger.warning(f"[EMBEDDINGS] Fallback (batch) due to: {e}")
        rng = np.random.default_rng()
        return [
            normalize_embedding(rng.normal(0, 0.5, EMBEDDING_DIMENSIONS).tolist())
            for _ in cleaned
        ]

class ChromaEmbeddingFunction:
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return encode_texts_batch(texts, batch_size=64)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.__call__(texts)

    def embed_query(self, text: str) -> list[float]:
        return get_embedding(text)

    def name(self) -> str:
        return "custom_embedding"
