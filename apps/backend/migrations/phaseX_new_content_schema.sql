-- -----------------------------------------------------------------------------
-- TOMEHUB DATABASE OPTIMIZATION V2 SCHEMA SCRIPT
-- ARCHITECTURE: [Firestore] -> [Oracle Canonical Layer] -> [Oracle Retrieval Layer]
-- -----------------------------------------------------------------------------

-- =============================================================================
-- 1. RETRIEVAL LAYER: TOMEHUB_CONTENT
-- Bu tablo metinleri, chunk'ları, highlight ve insight alt öğelerini tutar.
-- Multi-tenant performans optimizasyonu icin Interval-Hash Partitioning onerilir.
-- Ancak Oracle Autonomous'ta standart List partitioning veya Range daha kolay olabilir.
-- Asagida Range (Tarih) bazli partition ve UID bazli Index kurgusu hazirlanmistir.
-- =============================================================================

CREATE TABLE TOMEHUB_CONTENT_V2 (
    ID NUMBER GENERATED ALWAYS AS IDENTITY,
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    ITEM_ID VARCHAR2(255) NOT NULL, -- = BOOK_ID (References TOMEHUB_LIBRARY_ITEMS)
    CONTENT_TYPE VARCHAR2(50) NOT NULL, -- PDF_CHUNK, HIGHLIGHT, INSIGHT, PERSONAL_NOTE
    
    -- Textual Information
    TITLE VARCHAR2(1000), 
    CONTENT_CHUNK CLOB NOT NULL,
    NORMALIZED_CONTENT CLOB,
    
    -- Metadata (Polymorphic attributes depending on type)
    PAGE_NUMBER NUMBER,
    PARAGRAPH_NUMBER NUMBER,
    CHAPTER_NAME VARCHAR2(500),
    COMMENT_TEXT CLOB,
    TAGS_JSON CLOB CHECK (TAGS_JSON IS JSON),
    NOTE_DATE DATE,
    
    -- AI Visibility Engine (Domain Logic)
    AI_ELIGIBLE NUMBER(1) DEFAULT 1 CHECK (AI_ELIGIBLE IN (0, 1)),
    RAG_WEIGHT NUMBER DEFAULT 1.0, -- Used for penalizing IDEAS vs Boosting exact matches
    
    -- Execution / Vectors
    CHUNK_INDEX NUMBER,
    VEC_EMBEDDING VECTOR(768, FLOAT32),

    
    -- Audit
    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Partition Key
    PARTITION_MONTH DATE GENERATED ALWAYS AS (TRUNC(CREATED_AT, 'MM')) VIRTUAL,
    
    CONSTRAINT pk_tomehub_content_v2 PRIMARY KEY (ID)
)
PARTITION BY RANGE (PARTITION_MONTH) 
INTERVAL(NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_initial VALUES LESS THAN (TO_DATE('2024-01-01', 'YYYY-MM-DD'))
);

-- Foreign Key to Canonical Layer
-- Assuming TOMEHUB_LIBRARY_ITEMS already exists as the master
ALTER TABLE TOMEHUB_CONTENT_V2 
ADD CONSTRAINT fk_content_library_item 
FOREIGN KEY (FIREBASE_UID, ITEM_ID) 
REFERENCES TOMEHUB_LIBRARY_ITEMS (FIREBASE_UID, ITEM_ID) 
DEFERRABLE INITIALLY DEFERRED;

-- =============================================================================
-- 2. HIGH PERFORMANCE INDEXING
-- =============================================================================

-- Firebase UID bazli veri izolasyon hizlandiricisi 
-- (Local index olmasi partition icinde hizli calismasini saglar)
CREATE INDEX idx_cnt_uid_v2 ON TOMEHUB_CONTENT_V2(FIREBASE_UID, ITEM_ID) LOCAL;

-- AI Type filtreleme (VPD uzerine ek filtreleme hizi)
CREATE INDEX idx_cnt_ai_eligible_v2 ON TOMEHUB_CONTENT_V2(FIREBASE_UID, AI_ELIGIBLE) LOCAL;

-- Content Type bazli RAG getirme
CREATE INDEX idx_cnt_type_v2 ON TOMEHUB_CONTENT_V2(CONTENT_TYPE, FIREBASE_UID) LOCAL;

-- Vektorel Arama Indeksi (Vector Search Index) - In-Memory / Cosine
CREATE VECTOR INDEX idx_cnt_vec_v2 ON TOMEHUB_CONTENT_V2(VEC_EMBEDDING) 
ORGANIZATION NEIGHBOR PARTITIONS
DISTANCE COSINE
WITH TARGET ACCURACY 95;

-- =============================================================================
-- 3. VPD (VIRTUAL PRIVATE DATABASE) POLICY SETUP (To be executed by ADMIN/SYS)
-- =============================================================================
-- CREATE OR REPLACE FUNCTION auth_uid_policy (
--   schema_var IN VARCHAR2,
--   table_var  IN VARCHAR2
-- )
-- RETURN VARCHAR2
-- IS
--   v_uid VARCHAR2(255);
-- BEGIN
--   v_uid := SYS_CONTEXT('USERENV', 'CLIENT_INFO');
--   IF v_uid IS NULL THEN
--     RETURN '1=2'; -- Block if no UID set
--   ELSE
--     RETURN 'FIREBASE_UID = ''' || v_uid || '''';
--   END IF;
-- END auth_uid_policy;
-- /
-- /*
-- EXEC DBMS_RLS.ADD_POLICY (
--   object_schema   => 'USER',
--   object_name     => 'TOMEHUB_CONTENT_V2',
--   policy_name     => 'UID_ISOLATION_POLICY',
--   function_schema => 'USER',
--   policy_function => 'auth_uid_policy',
--   statement_types => 'SELECT, INSERT, UPDATE, DELETE'
-- );
-- */
