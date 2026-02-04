-- Phase X: Normalize content tags and categories
DECLARE
    v_count NUMBER := 0;
BEGIN
    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'TOMEHUB_CONTENT_TAGS';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE TOMEHUB_CONTENT_TAGS (
                ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                CONTENT_ID NUMBER NOT NULL,
                TAG VARCHAR2(255) NOT NULL,
                TAG_NORM VARCHAR2(255) NOT NULL,
                CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT FK_CONTENT_TAGS_CONTENT
                    FOREIGN KEY (CONTENT_ID) REFERENCES TOMEHUB_CONTENT(ID) ON DELETE CASCADE
            )
        ';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_tables WHERE table_name = 'TOMEHUB_CONTENT_CATEGORIES';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE TABLE TOMEHUB_CONTENT_CATEGORIES (
                ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                CONTENT_ID NUMBER NOT NULL,
                CATEGORY VARCHAR2(255) NOT NULL,
                CATEGORY_NORM VARCHAR2(255) NOT NULL,
                CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT FK_CONTENT_CATS_CONTENT
                    FOREIGN KEY (CONTENT_ID) REFERENCES TOMEHUB_CONTENT(ID) ON DELETE CASCADE
            )
        ';
    END IF;

    -- Indexes for tags
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('UIDX_CONTENT_TAGS');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uidx_content_tags ON TOMEHUB_CONTENT_TAGS (CONTENT_ID, TAG_NORM)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_CONTENT_TAGS_TAGNORM');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_content_tags_tagnorm ON TOMEHUB_CONTENT_TAGS (TAG_NORM)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_CONTENT_TAGS_CONTENT');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_content_tags_content ON TOMEHUB_CONTENT_TAGS (CONTENT_ID)';
    END IF;

    -- Indexes for categories
    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('UIDX_CONTENT_CATEGORIES');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE UNIQUE INDEX uidx_content_categories ON TOMEHUB_CONTENT_CATEGORIES (CONTENT_ID, CATEGORY_NORM)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_CONTENT_CATEGORIES_NORM');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_content_categories_norm ON TOMEHUB_CONTENT_CATEGORIES (CATEGORY_NORM)';
    END IF;

    SELECT COUNT(*) INTO v_count FROM user_indexes WHERE index_name = UPPER('IDX_CONTENT_CATEGORIES_CONTENT');
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE INDEX idx_content_categories_content ON TOMEHUB_CONTENT_CATEGORIES (CONTENT_ID)';
    END IF;
END;
/
