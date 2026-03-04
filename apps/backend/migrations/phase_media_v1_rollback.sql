-- Phase Media V1 rollback (safe, guarded)
-- Notes:
-- - Does not drop CAST_TOP_JSON column to avoid destructive data loss.
-- - Restores ITEM_TYPE check constraint to legacy values only if no media rows exist.

DECLARE
    v_table_exists NUMBER := 0;
    v_media_rows NUMBER := 0;
    v_cons_exists NUMBER := 0;
    v_idx_exists NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO v_table_exists
      FROM user_tables
     WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS';

    IF v_table_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('TOMEHUB_LIBRARY_ITEMS not found. Skipping rollback.');
    ELSE
        SELECT COUNT(*)
          INTO v_idx_exists
          FROM user_indexes
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND index_name = 'IDX_TH_LIB_UID_ISBN_MEDIA';

        IF v_idx_exists = 1 THEN
            EXECUTE IMMEDIATE 'DROP INDEX IDX_TH_LIB_UID_ISBN_MEDIA';
        END IF;

        SELECT COUNT(*)
          INTO v_cons_exists
          FROM user_constraints
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND constraint_name = 'CHK_TH_LIB_CAST_TOP_JSON';

        IF v_cons_exists = 1 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_LIBRARY_ITEMS DROP CONSTRAINT CHK_TH_LIB_CAST_TOP_JSON';
        END IF;

        SELECT COUNT(*)
          INTO v_media_rows
          FROM TOMEHUB_LIBRARY_ITEMS
         WHERE ITEM_TYPE IN ('MOVIE', 'SERIES');

        IF v_media_rows > 0 THEN
            RAISE_APPLICATION_ERROR(
                -20011,
                'Rollback blocked: MOVIE/SERIES rows exist in TOMEHUB_LIBRARY_ITEMS.'
            );
        END IF;

        FOR rec IN (
            SELECT uc.constraint_name
              FROM user_constraints uc
              JOIN user_cons_columns ucc
                ON uc.constraint_name = ucc.constraint_name
               AND uc.table_name = ucc.table_name
             WHERE uc.table_name = 'TOMEHUB_LIBRARY_ITEMS'
               AND uc.constraint_type = 'C'
               AND ucc.column_name = 'ITEM_TYPE'
               AND REGEXP_LIKE(UPPER(NVL(uc.search_condition_vc, '')), 'ITEM_TYPE.*IN\s*\(')
        ) LOOP
            EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_LIBRARY_ITEMS DROP CONSTRAINT ' || rec.constraint_name;
        END LOOP;

        EXECUTE IMMEDIATE '
            ALTER TABLE TOMEHUB_LIBRARY_ITEMS
            ADD CONSTRAINT CHK_TH_LIB_ITEM_TYPE_MEDIA
            CHECK (ITEM_TYPE IN (''BOOK'', ''ARTICLE'', ''WEBSITE'', ''PERSONAL_NOTE''))
        ';
    END IF;
END;
/
