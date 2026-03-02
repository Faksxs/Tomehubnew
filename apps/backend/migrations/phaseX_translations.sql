-- =============================================================================
-- TOMEHUB_TRANSLATIONS: Stores multilingual translations for content chunks
-- Separate from CONTENT_V2 to avoid polluting RAG/vector indexes.
-- =============================================================================

BEGIN
    EXECUTE IMMEDIATE '
        CREATE TABLE TOMEHUB_TRANSLATIONS (
            ID            NUMBER GENERATED ALWAYS AS IDENTITY,
            CONTENT_ID    NUMBER NOT NULL,
            FIREBASE_UID  VARCHAR2(255) NOT NULL,
            LANG_EN       CLOB,
            LANG_NL       CLOB,
            ETYMOLOGY_JSON CLOB CHECK (ETYMOLOGY_JSON IS JSON OR ETYMOLOGY_JSON IS NULL),
            CREATED_AT    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT pk_translations PRIMARY KEY (ID),
            CONSTRAINT uq_translation_content UNIQUE (CONTENT_ID)
        )
    ';
    DBMS_OUTPUT.PUT_LINE('✓ TOMEHUB_TRANSLATIONS table created');
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -955 THEN
            DBMS_OUTPUT.PUT_LINE('Table TOMEHUB_TRANSLATIONS already exists — skipped');
        ELSE
            RAISE;
        END IF;
END;
/

-- Indexes for fast lookup
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_trans_content_id ON TOMEHUB_TRANSLATIONS(CONTENT_ID)';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_trans_uid ON TOMEHUB_TRANSLATIONS(FIREBASE_UID)';
EXCEPTION WHEN OTHERS THEN IF SQLCODE != -955 THEN RAISE; END IF;
END;
/
