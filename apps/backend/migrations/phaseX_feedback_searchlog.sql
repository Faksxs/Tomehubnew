-- Phase X: Feedback/Search log optimizations
DECLARE
    v_count NUMBER := 0;
BEGIN
    -- Add MODEL_NAME to search logs
    SELECT COUNT(*) INTO v_count
    FROM user_tab_cols
    WHERE table_name = 'TOMEHUB_SEARCH_LOGS' AND column_name = 'MODEL_NAME';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_SEARCH_LOGS ADD (MODEL_NAME VARCHAR2(100))';
    END IF;

    -- Search logs indexes
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_SEARCH_LOGS_UID');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_search_logs_uid ON TOMEHUB_SEARCH_LOGS(FIREBASE_UID)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_SEARCH_LOGS_TIME');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_search_logs_time ON TOMEHUB_SEARCH_LOGS(TIMESTAMP)';
    END IF;

    -- Feedback indexes
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_FEEDBACK_RATING_TIME');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_feedback_rating_time ON TOMEHUB_FEEDBACK(RATING, CREATED_AT)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_FEEDBACK_LOG');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_feedback_log ON TOMEHUB_FEEDBACK(SEARCH_LOG_ID)';
    END IF;
END;
/
