-- Add unique constraint to prevent duplicate relations

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_constraints
     WHERE constraint_name = 'UQ_RELATION_TRIPLE';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            ALTER TABLE TOMEHUB_RELATIONS
            ADD CONSTRAINT UQ_RELATION_TRIPLE
            UNIQUE (SRC_ID, DST_ID, REL_TYPE)
        ';
    END IF;
END;
/
