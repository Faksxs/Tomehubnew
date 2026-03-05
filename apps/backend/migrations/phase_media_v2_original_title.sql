-- Phase Media V2: original title support for MOVIE/SERIES items.
-- Adds TOMEHUB_LIBRARY_ITEMS.ORIGINAL_TITLE (idempotent, additive).

DECLARE
    v_table_exists NUMBER := 0;
    v_col_exists NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO v_table_exists
      FROM user_tables
     WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS';

    IF v_table_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('TOMEHUB_LIBRARY_ITEMS not found. Skipping phase_media_v2_original_title.');
    ELSE
        SELECT COUNT(*)
          INTO v_col_exists
          FROM user_tab_columns
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND column_name = 'ORIGINAL_TITLE';

        IF v_col_exists = 0 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD (ORIGINAL_TITLE VARCHAR2(256 CHAR))';
        END IF;
    END IF;
END;
/
