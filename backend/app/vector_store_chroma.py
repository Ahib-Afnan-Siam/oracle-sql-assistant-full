import logging
from typing import List, Dict, Tuple
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION_NAME = "schema_docs"

embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

def get_chroma_client():
    return chromadb.Client()

def search_similar_schema(query: str, top_k: int = 5) -> List[Dict]:
    client = get_chroma_client()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )

    logger.info(f"[CHROMA] Querying for: {query}")
    results = collection.query(query_texts=[query], n_results=top_k)

    if not results.get('documents'):
        logger.warning("[CHROMA] No matches found. Consider improving schema chunk descriptions or user query phrasing.")

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    return [
        {"id": doc_id, "document": doc, "metadata": meta}
        for doc_id, doc, meta in zip(ids, docs, metas)
    ]

def search_vector_store_detailed(query: str, top_k: int = 3):
    from app.embeddings import get_embedding
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(path="chroma_db", settings=Settings(anonymized_telemetry=False))
    collection = client.get_collection("schema_docs")
    query_vector = get_embedding(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "distances", "metadatas"]
    )

    formatted_results = []
    for doc, dist, meta in zip(results['documents'][0], results['distances'][0], results['metadatas'][0]):
        formatted_results.append({
            "document": doc,
            "score": dist,
            "metadata": meta
        })
    return formatted_results
