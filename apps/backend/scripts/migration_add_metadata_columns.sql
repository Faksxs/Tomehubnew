
-- Migration Script: Add Metadata Columns to TOMEHUB_CONTENT
-- Purpose: Support Phase 3 Data Normalization (moving metadata out of content blobs)

DECLARE
    v_column_exists NUMBER;
BEGIN
    -- 1. Add PERSONAL_NOTE column
    SELECT count(*) INTO v_column_exists FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT' AND column_name = 'PERSONAL_NOTE';
    IF v_column_exists = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT ADD (PERSONAL_NOTE CLOB)';
        DBMS_OUTPUT.PUT_LINE('Added PERSONAL_NOTE column.');
    END IF;

    -- 2. Add TAGS column
    SELECT count(*) INTO v_column_exists FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT' AND column_name = 'TAGS';
    IF v_column_exists = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT ADD (TAGS CLOB)';
        DBMS_OUTPUT.PUT_LINE('Added TAGS column.');
    END IF;
    
    -- 3. Add SUMMARY column
    SELECT count(*) INTO v_column_exists FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT' AND column_name = 'SUMMARY';
    IF v_column_exists = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT ADD (SUMMARY CLOB)';
        DBMS_OUTPUT.PUT_LINE('Added SUMMARY column.');
    END IF;

    -- 4. Add NORMALIZED_STATUS column (to track migration progress)
    SELECT count(*) INTO v_column_exists FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT' AND column_name = 'NORMALIZED_STATUS';
    IF v_column_exists = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT ADD (NORMALIZED_STATUS VARCHAR2(20))';
        DBMS_OUTPUT.PUT_LINE('Added NORMALIZED_STATUS column.');
    END IF;
    
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Error: ' || SQLERRM);
        ROLLBACK;
        RAISE;
END;
/
