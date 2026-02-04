-- Phase X: File reports optimization
DECLARE
    v_count NUMBER := 0;
BEGIN
    -- Drop redundant index if exists
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_REPORT_BOOK');
    IF v_count > 0 THEN
        EXECUTE IMMEDIATE 'DROP INDEX IDX_REPORT_BOOK';
    END IF;

    -- Ensure KEY_TOPICS is JSON for JSON search index (skip if any CHECK constraint exists on KEY_TOPICS)
    SELECT COUNT(*) INTO v_count
    FROM user_constraints c
    JOIN user_cons_columns col ON c.constraint_name = col.constraint_name
    WHERE c.table_name = 'TOMEHUB_FILE_REPORTS'
      AND col.column_name = 'KEY_TOPICS'
      AND c.constraint_type = 'C';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_FILE_REPORTS ADD CONSTRAINT chk_file_reports_key_topics_json CHECK (KEY_TOPICS IS JSON)';
    END IF;

    -- JSON search index on KEY_TOPICS
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_FILE_REPORTS_KEY_TOPICS_JSON');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE SEARCH INDEX idx_file_reports_key_topics_json ON TOMEHUB_FILE_REPORTS (KEY_TOPICS) FOR JSON';
    END IF;
END;
/
