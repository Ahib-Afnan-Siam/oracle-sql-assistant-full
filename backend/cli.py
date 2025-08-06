#!/usr/bin/env python3
import argparse
import logging
import re
from typing import List
from difflib import SequenceMatcher
from app.vector_store import collection, search_vector_store_detailed
from app.embeddings import get_embedding
from app.db_connector import connect_to_source
from app.config import SOURCES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Utility Functions ------------------ #

STOPWORDS = {"information", "details", "data", "record"}

def extract_keywords(query: str) -> List[str]:
    """Extract alphanumeric keywords from the query, excluding common stopwords."""
    return [w for w in re.split(r"[^A-Za-z0-9_]+", query) if w and w.lower() not in STOPWORDS]

def compute_name_score(table_name: str, keywords: List[str]) -> float:
    """Compute name match score using exact, fuzzy, and substring boosting."""
    table_name = table_name.upper()
    max_score = 0.0
    for k in keywords:
        ku = k.upper()
        if ku == table_name:
            return 1.0
        score = SequenceMatcher(None, ku, table_name).ratio()
        if ku in table_name or table_name in ku:
            score = min(1.0, score + 0.1)
        if score > max_score:
            max_score = score
    return max_score

def detect_table_name(query: str, tables: list) -> str:
    """Detect if query mentions a known table name."""
    query_upper = query.upper()
    for table in tables:
        if table in query_upper:
            return table
    return None

def detect_data_search(query: str) -> bool:
    """Detect if query contains potential data search terms."""
    return bool(re.search(r"[A-Za-z0-9]+", query))

# ------------------ Hybrid Vector Search ------------------ #

def search_schema(query: str, top_k: int = 3, threshold: float = 0.5, debug_matching=False) -> List[dict]:
    keywords = extract_keywords(query)
    docs = collection.get()

    if not docs.get('ids'):
        logger.warning("No documents in the Chroma collection.")
        return []

    embedding_results = search_vector_store_detailed(query, top_k=len(docs['ids']))
    embedding_scores = {}
    if isinstance(embedding_results, list):
        for i, result in enumerate(embedding_results):
            embedding_scores[result.get("id", f"doc_{i}")] = 1.0

    scored_docs = []
    for doc_id, doc, meta in zip(docs['ids'], docs['documents'], docs['metadatas']):
        table_name = doc_id.split("::")[-1]
        name_score = compute_name_score(table_name, keywords)
        embedding_score = embedding_scores.get(doc_id, 0.0)
        final_score = 0.7 * name_score + 0.3 * embedding_score
        if debug_matching:
            logger.info(f"[DEBUG] {table_name}: name={name_score:.2f}, embedding={embedding_score:.2f}, final={final_score:.2f}")
        scored_docs.append((final_score, {"id": doc_id, "content": doc, "metadata": meta}))

    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored_docs[:top_k]]

def format_results(results: List[dict]) -> str:
    if not results:
        return "No relevant schema information found."
    output = []
    for idx, result in enumerate(results, 1):
        output.append(
            f"\nMATCH #{idx}\n"
            f"ID: {result['id']}\n"
            f"CONTENT:\n{result['content']}\n"
            f"{'-'*50}"
        )
    return "\n".join(output)

# ------------------ Live Data Fetch ------------------ #

def format_table(columns, rows):
    """Format rows in table form."""
    output = "  |  ".join(columns) + "\n"
    for row in rows:
        output += "  |  ".join(str(v) if v is not None else "NULL" for v in row) + "\n"
    return output

def show_table_sample(table_name: str):
    cfg = SOURCES[0]
    try:
        with connect_to_source(cfg) as conn:
            cur = conn.cursor()
            query = f"SELECT * FROM {table_name} FETCH FIRST 5 ROWS ONLY"
            cur.execute(query)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            print(f"\nSample data from table {table_name}:\n")
            print(format_table(columns, rows))
    except Exception as e:
        logger.error(f"Failed to fetch sample data for {table_name}: {e}")

def search_all_tables_for_data(keywords: List[str]):
    """Search for all keywords across all tables & columns, using AND fallback OR logic."""
    cfg = SOURCES[0]
    docs = collection.get()
    all_tables = [doc_id.split("::")[-1] for doc_id in docs['ids']]
    found_any = False

    with connect_to_source(cfg) as conn:
        cur = conn.cursor()
        for table in all_tables:
            try:
                cur.execute(f"SELECT COLUMN_NAME, DATA_TYPE FROM ALL_TAB_COLUMNS WHERE TABLE_NAME = '{table}'")
                columns_info = cur.fetchall()
                if not columns_info:
                    continue

                # Build AND conditions first
                and_conditions = []
                for token in keywords:
                    token_lower = token.lower()
                    sub_conditions = []
                    for col_name, data_type in columns_info:
                        if token.isdigit() and "NUMBER" in data_type:
                            sub_conditions.append(f"{col_name} = {token}")
                        else:
                            sub_conditions.append(f"LOWER({col_name}) LIKE '%{token_lower}%'")
                    if sub_conditions:
                        and_conditions.append("(" + " OR ".join(sub_conditions) + ")")

                where_clause = " AND ".join(and_conditions)
                query = f"SELECT * FROM {table} WHERE {where_clause} FETCH FIRST 5 ROWS ONLY"
                cur.execute(query)
                rows = cur.fetchall()

                # If no rows, fallback to OR
                if not rows and len(keywords) > 1:
                    or_conditions = []
                    for token in keywords:
                        token_lower = token.lower()
                        for col_name, data_type in columns_info:
                            if token.isdigit() and "NUMBER" in data_type:
                                or_conditions.append(f"{col_name} = {token}")
                            else:
                                or_conditions.append(f"LOWER({col_name}) LIKE '%{token_lower}%'")
                    where_clause = " OR ".join(or_conditions)
                    query = f"SELECT * FROM {table} WHERE {where_clause} FETCH FIRST 5 ROWS ONLY"
                    cur.execute(query)
                    rows = cur.fetchall()

                if rows:
                    found_any = True
                    col_names = [desc[0] for desc in cur.description]
                    print(f"\nFound in table {table}:\n")
                    print(format_table(col_names, rows))
            except Exception:
                continue

    if not found_any:
        print(f"No matching data found for '{' '.join(keywords)}'.")

# ------------------ Main ------------------ #

def main():
    parser = argparse.ArgumentParser(description="Oracle SQL Assistant - Query your database schema and data")
    parser.add_argument("query", type=str, help="Your natural language query")
    parser.add_argument("-k", "--top-k", type=int, default=3, help="Top K results")
    parser.add_argument("--verbose", action="store_true", help="Verbose mode")
    parser.add_argument("--debug-matching", action="store_true", help="Print detailed match scores")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    docs = collection.get()
    all_tables = [doc_id.split("::")[-1].upper() for doc_id in docs['ids']]
    query_upper = args.query.upper()

    try:
        table_name = detect_table_name(query_upper, all_tables)
        if table_name:
            show_table_sample(table_name)
            return

        if detect_data_search(args.query):
            keywords = extract_keywords(args.query)
            if keywords:
                search_all_tables_for_data(keywords)
            else:
                print(f"No valid keywords found in query '{args.query}'.")
            return

        results = search_schema(args.query, top_k=args.top_k, debug_matching=args.debug_matching)
        print(format_results(results))

    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
