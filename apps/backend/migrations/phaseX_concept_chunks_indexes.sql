-- Phase X: Composite indexes for concept-chunk traversal

-- concept -> content
-- If a PK already exists on (CONCEPT_ID, CONTENT_ID), skip creating a duplicate index.

-- content -> concept (create if missing)
DECLARE
    v_count NUMBER := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM USER_INDEXES
    WHERE INDEX_NAME = UPPER('IDX_CONTENT_CONCEPT');

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_content_concept ON TOMEHUB_CONCEPT_CHUNKS(CONTENT_ID, CONCEPT_ID)';
    END IF;
END;
/
