-- Drop legacy deaccent column now that exact matching uses NORMALIZED_CONTENT.
-- Idempotent and safe for both V2 and legacy table names.

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_tab_cols
     WHERE table_name = 'TOMEHUB_CONTENT_V2'
       AND column_name = 'TEXT_DEACCENTED';

    IF v_count > 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT_V2 DROP COLUMN TEXT_DEACCENTED';
    END IF;
END;
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_tab_cols
     WHERE table_name = 'TOMEHUB_CONTENT'
       AND column_name = 'TEXT_DEACCENTED';

    IF v_count > 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT DROP COLUMN TEXT_DEACCENTED';
    END IF;
END;
/

