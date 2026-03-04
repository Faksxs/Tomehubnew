-- Phase Media V1 (idempotent, additive)
-- 1) Extend ITEM_TYPE check constraint with MOVIE/SERIES
-- 2) Add optional CAST_TOP_JSON column
-- 3) Add JSON check constraint for CAST_TOP_JSON
-- 4) Add optional lookup index on (FIREBASE_UID, ISBN)

DECLARE
    v_table_exists NUMBER := 0;
    v_col_exists NUMBER := 0;
    v_cons_exists NUMBER := 0;
    v_idx_exists NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO v_table_exists
      FROM user_tables
     WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS';

    IF v_table_exists = 0 THEN
        DBMS_OUTPUT.PUT_LINE('TOMEHUB_LIBRARY_ITEMS not found. Skipping phase_media_v1.');
    ELSE
        -- Replace ITEM_TYPE IN(...) check constraint with media-capable version.
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

        SELECT COUNT(*)
          INTO v_cons_exists
          FROM user_constraints
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND constraint_name = 'CHK_TH_LIB_ITEM_TYPE_MEDIA';

        IF v_cons_exists = 0 THEN
            EXECUTE IMMEDIATE '
                ALTER TABLE TOMEHUB_LIBRARY_ITEMS
                ADD CONSTRAINT CHK_TH_LIB_ITEM_TYPE_MEDIA
                CHECK (ITEM_TYPE IN (''BOOK'', ''ARTICLE'', ''WEBSITE'', ''PERSONAL_NOTE'', ''MOVIE'', ''SERIES''))
            ';
        END IF;

        -- Add CAST_TOP_JSON if missing.
        SELECT COUNT(*)
          INTO v_col_exists
          FROM user_tab_columns
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND column_name = 'CAST_TOP_JSON';

        IF v_col_exists = 0 THEN
            EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD (CAST_TOP_JSON CLOB)';
        END IF;

        -- Add CAST_TOP_JSON JSON guard (non-blocking for existing data).
        SELECT COUNT(*)
          INTO v_cons_exists
          FROM user_constraints
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND constraint_name = 'CHK_TH_LIB_CAST_TOP_JSON';

        IF v_cons_exists = 0 THEN
            EXECUTE IMMEDIATE '
                ALTER TABLE TOMEHUB_LIBRARY_ITEMS
                ADD CONSTRAINT CHK_TH_LIB_CAST_TOP_JSON
                CHECK (CAST_TOP_JSON IS JSON)
                ENABLE NOVALIDATE
            ';
        END IF;

        -- Optional TMDb token lookup acceleration.
        SELECT COUNT(*)
          INTO v_idx_exists
          FROM user_indexes
         WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'
           AND index_name = 'IDX_TH_LIB_UID_ISBN_MEDIA';

        IF v_idx_exists = 0 THEN
            EXECUTE IMMEDIATE '
                CREATE INDEX IDX_TH_LIB_UID_ISBN_MEDIA
                ON TOMEHUB_LIBRARY_ITEMS (FIREBASE_UID, ISBN)
            ';
        END IF;
    END IF;
END;
/
