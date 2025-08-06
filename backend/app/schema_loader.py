import logging
from app.db_connector import connect_to_source, connect_vector
from app.embeddings import get_embedding
from app.config import SOURCES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VECTOR_TYPE_NAME = "APPS.VECTOR"  # 🔁 Change "APPS" to the schema name that owns the VECTOR type

def load_schema_to_oracle_vector():
    source_db = SOURCES[0]

    with connect_to_source(source_db) as source_conn, connect_vector() as vector_conn:
        source_cur = source_conn.cursor()
        vector_cur = vector_conn.cursor()

        # ✅ Resolve the VECTOR object type
        try:
            vec_type = vector_conn.gettype(VECTOR_TYPE_NAME)
            vector_cur.setinputsizes(None, None, vec_type)
        except Exception as e:
            logger.error(f"Failed to resolve VECTOR type '{VECTOR_TYPE_NAME}': {e}")
            return

        # ✅ Get list of tables
        source_cur.execute("SELECT table_name FROM user_tables")
        tables = [row[0] for row in source_cur.fetchall()]

        inserted = 0
        for table in tables:
            logger.info(f"Processing table: {table}")

            # Get schema info
            source_cur.execute("""
                SELECT column_name, data_type 
                FROM user_tab_columns 
                WHERE table_name = :1
            """, (table,))
            columns = source_cur.fetchall()

            if not columns:
                continue

            # Describe the schema
            content = f"TABLE: {table}\nCOLUMNS:\n"
            content += "\n".join([f"  - {col} ({dtype})" for col, dtype in columns])

            try:
                embedding = get_embedding(content)

                if not isinstance(embedding, list) or len(embedding) != 384:
                    raise ValueError("Embedding must be a list of exactly 384 floats.")

                # ✅ Wrap in Oracle VECTOR object
                vector_obj = vec_type.newobject()
                vector_obj.extend(embedding)

                vector_cur.execute("""
                    INSERT INTO VECTOR_SCHEMA_DOCS (DOC_ID, CONTENT, EMBEDDING)
                    VALUES (:1, :2, :3)
                """, (f"{source_db['service']}::{table}", content, vector_obj))
                inserted += 1

            except Exception as e:
                logger.warning(f"Insert failed for {table}: {e}")

        vector_conn.commit()
        logger.info(f"✅ Inserted {inserted} schemas into VECTOR_SCHEMA_DOCS.")

if __name__ == "__main__":
    load_schema_to_oracle_vector()
