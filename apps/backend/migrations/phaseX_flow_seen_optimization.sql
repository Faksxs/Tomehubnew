-- Normalize FLOW_SEEN chunk_id type + add critical index
-- Safe, idempotent blocks

DECLARE
    v_has_new NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_has_new
      FROM user_tab_columns
     WHERE table_name = 'TOMEHUB_FLOW_SEEN'
       AND column_name = 'CHUNK_ID_NUM';

    IF v_has_new = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_FLOW_SEEN ADD (CHUNK_ID_NUM NUMBER)';
        EXECUTE IMMEDIATE 'UPDATE TOMEHUB_FLOW_SEEN SET CHUNK_ID_NUM = TO_NUMBER(CHUNK_ID)';
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_FLOW_SEEN MODIFY (CHUNK_ID_NUM NOT NULL)';
    END IF;
END;
/

DECLARE
    v_has_old NUMBER;
    v_has_new NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_has_old
      FROM user_tab_columns
     WHERE table_name = 'TOMEHUB_FLOW_SEEN'
       AND column_name = 'CHUNK_ID';

    SELECT COUNT(*)
      INTO v_has_new
      FROM user_tab_columns
     WHERE table_name = 'TOMEHUB_FLOW_SEEN'
       AND column_name = 'CHUNK_ID_NUM';

    IF v_has_old = 1 AND v_has_new = 1 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_FLOW_SEEN DROP COLUMN CHUNK_ID';
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_FLOW_SEEN RENAME COLUMN CHUNK_ID_NUM TO CHUNK_ID';
    END IF;
END;
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_indexes
     WHERE index_name = 'IDX_FLOW_SEEN_CHECK';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX IDX_FLOW_SEEN_CHECK ON TOMEHUB_FLOW_SEEN (FIREBASE_UID, CHUNK_ID)';
    END IF;
END;
/
