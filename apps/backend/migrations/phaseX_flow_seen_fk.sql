-- Clean orphan FLOW_SEEN rows + add FK + add session index

DELETE FROM TOMEHUB_FLOW_SEEN fs
WHERE NOT EXISTS (
    SELECT 1 FROM TOMEHUB_CONTENT c WHERE c.id = fs.chunk_id
);
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_constraints
     WHERE constraint_name = 'FK_FLOW_CHUNK';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            ALTER TABLE TOMEHUB_FLOW_SEEN
            ADD CONSTRAINT FK_FLOW_CHUNK
            FOREIGN KEY (CHUNK_ID) REFERENCES TOMEHUB_CONTENT(ID)
            ON DELETE CASCADE
        ';
    END IF;
END;
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_indexes
     WHERE index_name = 'IDX_FLOW_SEEN_SESSION';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX IDX_FLOW_SEEN_SESSION ON TOMEHUB_FLOW_SEEN (SESSION_ID)';
    END IF;
END;
/
