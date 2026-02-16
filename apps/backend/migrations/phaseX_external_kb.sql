-- Phase X: External KB storage (Wikidata + OpenAlex)
DECLARE
    v_count NUMBER := 0;
BEGIN
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'TOMEHUB_EXTERNAL_BOOK_META';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE TOMEHUB_EXTERNAL_BOOK_META (
                BOOK_ID VARCHAR2(256) NOT NULL,
                FIREBASE_UID VARCHAR2(128) NOT NULL,
                ACADEMIC_SCOPE NUMBER(1) DEFAULT 0,
                WIKIDATA_QID VARCHAR2(64),
                OPENALEX_ID VARCHAR2(256),
                DOI VARCHAR2(256),
                EXTERNAL_JSON CLOB,
                LAST_SYNC_AT TIMESTAMP,
                SYNC_STATUS VARCHAR2(32),
                WIKIDATA_SYNC_AT TIMESTAMP,
                OPENALEX_SYNC_AT TIMESTAMP,
                WIKIDATA_STATUS VARCHAR2(32),
                OPENALEX_STATUS VARCHAR2(32),
                UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT PK_TOMEHUB_EXTERNAL_BOOK_META PRIMARY KEY (BOOK_ID, FIREBASE_UID)
            )
        ';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'TOMEHUB_EXTERNAL_ENTITIES';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE TOMEHUB_EXTERNAL_ENTITIES (
                ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                PROVIDER VARCHAR2(32) NOT NULL,
                EXTERNAL_ID VARCHAR2(256) NOT NULL,
                ENTITY_TYPE VARCHAR2(64) NOT NULL,
                LABEL VARCHAR2(512),
                PAYLOAD_JSON CLOB,
                UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'TOMEHUB_EXTERNAL_EDGES';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE TOMEHUB_EXTERNAL_EDGES (
                ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                SRC_ENTITY_ID NUMBER NOT NULL,
                DST_ENTITY_ID NUMBER NOT NULL,
                REL_TYPE VARCHAR2(64) NOT NULL,
                WEIGHT NUMBER(6,4) DEFAULT 0.5,
                PROVIDER VARCHAR2(32) NOT NULL,
                BOOK_ID VARCHAR2(256) NOT NULL,
                FIREBASE_UID VARCHAR2(128) NOT NULL,
                UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT FK_EXT_EDGE_SRC FOREIGN KEY (SRC_ENTITY_ID) REFERENCES TOMEHUB_EXTERNAL_ENTITIES(ID) ON DELETE CASCADE,
                CONSTRAINT FK_EXT_EDGE_DST FOREIGN KEY (DST_ENTITY_ID) REFERENCES TOMEHUB_EXTERNAL_ENTITIES(ID) ON DELETE CASCADE
            )
        ';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_EXT_META_BOOK_UID');
    IF v_count = 0 THEN
        BEGIN
            EXECUTE IMMEDIATE 'CREATE INDEX idx_ext_meta_book_uid ON TOMEHUB_EXTERNAL_BOOK_META (BOOK_ID, FIREBASE_UID)';
        EXCEPTION
            WHEN OTHERS THEN
                -- ORA-00955: name already used by existing object
                -- ORA-01408: such column list already indexed (e.g. PK index)
                IF SQLCODE NOT IN (-955, -1408) THEN
                    RAISE;
                END IF;
        END;
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('UIDX_EXT_ENTITY_PROVIDER_ID');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uidx_ext_entity_provider_id ON TOMEHUB_EXTERNAL_ENTITIES (PROVIDER, EXTERNAL_ID)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_EXT_EDGE_BOOK_REL');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_ext_edge_book_rel ON TOMEHUB_EXTERNAL_EDGES (BOOK_ID, REL_TYPE)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_EXT_EDGE_BOOK_UID');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_ext_edge_book_uid ON TOMEHUB_EXTERNAL_EDGES (BOOK_ID, FIREBASE_UID)';
    END IF;
END;
/
