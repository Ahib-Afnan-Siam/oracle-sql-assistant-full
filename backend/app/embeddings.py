import re
import numpy as np
from typing import List
import logging
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ✅ Match Oracle VECTOR(384, FLOAT32, DENSE)
EMBEDDING_DIMENSIONS = 384
MAX_TEXT_LENGTH = 10000
LOCAL_MODEL_NAME = 'all-MiniLM-L6-v2'

_local_model = None

def initialize_local_model():
    global _local_model
    if _local_model is None:
        logger.info(f"Initializing local embedding model: {LOCAL_MODEL_NAME}")
        _local_model = SentenceTransformer(LOCAL_MODEL_NAME)
    return _local_model

def get_local_embedding(text: str) -> List[float]:
    try:
        model = initialize_local_model()
        text = str(text)[:MAX_TEXT_LENGTH]
        return model.encode(text).tolist()
    except Exception as e:
        logger.error(f"Local embedding failed: {e}")
        raise

def normalize_embedding(embedding: List[float]) -> List[float]:
    """Ensure embedding is padded/truncated to 384 float32 values"""
    if len(embedding) < EMBEDDING_DIMENSIONS:
        embedding.extend([0.0] * (EMBEDDING_DIMENSIONS - len(embedding)))
    else:
        embedding = embedding[:EMBEDDING_DIMENSIONS]
    return np.array(embedding, dtype=np.float32).tolist()

def get_embedding(text: str) -> List[float]:
    if not text or not isinstance(text, str):
        raise ValueError("Input text must be a non-empty string")

    try:
        embedding = get_local_embedding(text)
        return normalize_embedding(embedding)
    except Exception as e:
        logger.warning(f"Local embedding failed, using random fallback: {e}")
        rng = np.random.default_rng()
        random_embedding = rng.normal(0, 0.5, EMBEDDING_DIMENSIONS).tolist()
        return normalize_embedding(random_embedding)

def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if not text:
        return text

    tokens = re.split(r'[\s,.!?;:()\[\]{}<>"\']+', text)
    if len(tokens) <= max_tokens:
        return text

    truncated = []
    count = 0
    for token in tokens:
        if count + 1 > max_tokens:
            break
        if token:
            truncated.append(token)
            count += 1

    return " ".join(truncated)

class ChromaEmbeddingFunction:
    def __call__(self, texts: list[str]) -> list[list[float]]:
        return [get_embedding(text) for text in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.__call__(texts)

    def embed_query(self, text: str) -> list[float]:
        return get_embedding(text)

    def name(self) -> str:
        return "custom_embedding"
