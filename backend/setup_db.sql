-- Connect to the PDB
ALTER SESSION SET CONTAINER = AIPDB;

-- Drop old table if exists (safe cleanup)
BEGIN
    EXECUTE IMMEDIATE 'DROP TABLE vector_schema_docs CASCADE CONSTRAINTS';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -942 THEN -- ORA-00942: table or view does not exist
            RAISE;
        END IF;
END;
/

-- Create vector table with fixed dimension
CREATE TABLE vector_schema_docs (
    doc_id VARCHAR2(256) PRIMARY KEY,
    content CLOB,
    embedding VECTOR(FLOAT32, 3) -- ✅ Explicit dimension and type
);

-- Create optimized vector index
CREATE VECTOR INDEX vec_schema_index ON vector_schema_docs(embedding)
ORGANIZATION NEIGHBOR PARTITIONS
DISTANCE COSINE
WITH TARGET ACCURACY 95;

-- Create supporting index for doc_id (for lookup)
CREATE INDEX idx_doc_id ON vector_schema_docs(doc_id);

-- Optional: verify
SELECT object_name, object_type 
FROM user_objects 
WHERE object_name IN (
    'VECTOR_SCHEMA_DOCS', 
    'VEC_SCHEMA_INDEX', 
    'IDX_DOC_ID'
);
