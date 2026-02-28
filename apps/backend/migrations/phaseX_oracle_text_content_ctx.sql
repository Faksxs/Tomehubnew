-- Oracle Text pilot index for TOMEHUB_CONTENT_V2.CONTENT_CHUNK
-- Safe/idempotent: preference is recreated, index is created only if missing.

BEGIN
    BEGIN
        CTX_DDL.DROP_PREFERENCE('TH_CONTENT_V2_LEXER');
    EXCEPTION
        WHEN OTHERS THEN
            NULL;
    END;
END;
/

BEGIN
    CTX_DDL.CREATE_PREFERENCE('TH_CONTENT_V2_LEXER', 'BASIC_LEXER');
    -- Accent-insensitive matching (s->ş, i->ı variants during lexical matching).
    CTX_DDL.SET_ATTRIBUTE('TH_CONTENT_V2_LEXER', 'BASE_LETTER', 'YES');
END;
/

DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_count
      FROM user_indexes
     WHERE index_name = 'IDX_TH_CONTENT_CTX_V2';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE INDEX IDX_TH_CONTENT_CTX_V2
            ON TOMEHUB_CONTENT_V2 (CONTENT_CHUNK)
            INDEXTYPE IS CTXSYS.CONTEXT
            PARAMETERS ('LEXER TH_CONTENT_V2_LEXER SYNC (MANUAL)')
        ]';
    END IF;
END;
/

