-- Update CHK_SOURCE_TYPE to include new canonical values

DECLARE
    v_exists NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_exists
      FROM user_constraints
     WHERE constraint_name = 'CHK_SOURCE_TYPE'
       AND table_name = 'TOMEHUB_CONTENT';

    IF v_exists = 1 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT DROP CONSTRAINT CHK_SOURCE_TYPE';
    END IF;

    EXECUTE IMMEDIATE '
        ALTER TABLE TOMEHUB_CONTENT
        ADD CONSTRAINT CHK_SOURCE_TYPE
        CHECK (source_type IN (
            ''PDF'', ''EPUB'', ''PDF_CHUNK'',
            ''ARTICLE'', ''WEBSITE'',
            ''PERSONAL_NOTE'',
            ''HIGHLIGHT'', ''INSIGHT'',
            ''BOOK'',
            ''NOTES'', ''NOTE'',
            ''personal''
        ))
    ';
END;
/
