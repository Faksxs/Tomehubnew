-- Add analytics index for TOP_RESULT_SCORE + TIMESTAMP

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_indexes
     WHERE index_name = 'IDX_SEARCH_LOGS_SCORE_TIME';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE INDEX IDX_SEARCH_LOGS_SCORE_TIME
            ON TOMEHUB_SEARCH_LOGS (TOP_RESULT_SCORE, TIMESTAMP)
        ';
    END IF;
END;
/
