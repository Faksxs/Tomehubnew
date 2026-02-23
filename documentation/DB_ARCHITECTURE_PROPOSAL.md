# TomeHub Veritabanı Mimarisi Önerisi (Taslak)

**Tarih:** 22 Şubat 2026  
**Hedef:** Oracle 23ai optimizasyonu, RAG/Search performance, Books management, Dual-AI support  
**Kapsam:** Schema redesign, indexing strategy, partitioning, caching, analytics

---

## 📋 İçindekiler

1. [Mevcut Durum](#mevcut-durum)
2. [Sorunlar ve Kısıtlamalar](#sorunlar-ve-kısıtlamalar)
3. [Mimarî Prensipleri](#mimarî-prensipleri)
4. [Önerilen Şema Yapısı](#önerilen-şema-yapısı)
5. [Indexing Stratejisi](#indexing-stratejisi)
6. [Partitioning Planı](#partitioning-planı)
7. [Caching Layer](#caching-layer)
8. [Performance Optimizations](#performance-optimizations)
9. [Migration Roadmap](#migration-roadmap)

---

## Mevcut Durum

### Mevcut Tablolar

```
TOMEHUB_CONTENT
├── ID (VARCHAR2, PRIMARY KEY)
├── FIREBASE_UID (VARCHAR2, Index)
├── CONTENT_CHUNK (CLOB) ← Semantic search source
├── VEC_EMBEDDING (VECTOR(768, FLOAT32)) ← Embedding
├── SOURCE_TYPE (VARCHAR2) ← 7 types (PDF, HIGHLIGHT, BOOK, etc.)
├── TITLE (VARCHAR2) ← Books match target
├── PAGE_NUMBER (NUMBER)
└── ... (20+ columns)

TOMEHUB_BOOKS
├── ID (VARCHAR2, PRIMARY KEY)
├── TITLE (VARCHAR2) ← Content.TITLE match point
├── AUTHOR (VARCHAR2) ← 98.9% NULL!
├── FIREBASE_UID (VARCHAR2)
├── CREATED_AT (TIMESTAMP)
├── TOTAL_CHUNKS (NUMBER) ← Declared vs actual mismatch
└── LAST_UPDATED (TIMESTAMP)

TOMEHUB_CONCEPTS
├── ID (VARCHAR2, PRIMARY KEY)
├── NAME (VARCHAR2)
├── DESCRIPTION (CLOB, optional)
└── VEC_EMBEDDING (VECTOR(768, FLOAT32))

TOMEHUB_RELATIONS
├── SRC_ID (VARCHAR2, FK → CONCEPTS.ID)
├── DST_ID (VARCHAR2, FK → CONCEPTS.ID)
├── WEIGHT (NUMBER) ← Importance ranking
└── RELATION_TYPE (VARCHAR2)

TOMEHUB_SEARCH_LOGS
├── ID (VARCHAR2, PRIMARY KEY)
├── FIREBASE_UID (VARCHAR2)
├── QUERY (VARCHAR2)
├── INTENT (VARCHAR2) ← 5 types
├── EXECUTION_TIME_MS (NUMBER)
├── TOP_RESULT_SCORE (NUMBER) ← 52% NULL!
├── TIMESTAMP (TIMESTAMP)
└── ... (10+ columns)

TOMEHUB_FLOW_SEEN
├── CHUNK_ID (VARCHAR2, FK)
├── FIREBASE_UID (VARCHAR2)
├── SESSION_ID (VARCHAR2)
├── SEEN_AT (TIMESTAMP)
└── PRIMARY KEY (CHUNK_ID, SESSION_ID)
```

### Mevcut Sorunlar

| Problem | Impact | Root Cause |
|---------|--------|-----------|
| **Yavaş Queries (31% >2s)** | UX latency | Semantic searches CPU-intensive, index eksikliği |
| **TOP_RESULT_SCORE NULL (52%)** | Analytics eksikliği | Judge AI integration eksik |
| **Books-Content STRING MATCH** | Veri bütünlüğü riski | FK yok, yazım hatası riski |
| **AUTHOR NULL (98.9%)** | Metadata eksikliği | Manual entry, API enrichment yok |
| **TOTAL_CHUNKS Mismatch** | Denormalizasyon riski | Trigger yok, manuel sync yok |
| **Search Pool Contention** | Connection limit | Read/write pool ayrımı eksik |
| **CLOB GROUP BY Limit** | Query complexity | Oracle CLOB işlevi limitation |
| **Cache Invalidation** | Stale data risk | Model version increment manual |

---

## Mimarî Prensipleri

### 1. **RAG-First Design**
- Content retrieval için optimized
- Vector search + semantic ranking
- Dual-AI judge loops destekleyen schema

### 2. **Multi-Tenancy by Design**
- Firebase UID tüm tablolarda
- Row-level security via scope
- User-scoped analytics

### 3. **Performance-Centric**
- Denormalizing where needed (TOTAL_CHUNKS, AVG_SCORE)
- Indexing for search, analytics, joins
- Partitioning for large tables

### 4. **Data Integrity**
- Foreign keys for relational data
- Triggers for denormalization consistency
- Check constraints for domain values

### 5. **Observability**
- Comprehensive logging (search_logs, ingestion_logs)
- Metrics (query latency, judge scores, cache hits)
- Audit trails for sensitive operations

---

## Önerilen Şema Yapısı

### Tier 1: Core Content (Search Foundation)

```sql
-- 1. TOMEHUB_CONTENT (Enhanced)
CREATE TABLE TOMEHUB_CONTENT (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Content
    CONTENT_CHUNK CLOB NOT NULL,        -- Search source
    VEC_EMBEDDING VECTOR(768, FLOAT32) NOT NULL,  -- Semantic
    
    -- Metadata
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    TITLE VARCHAR2(500) NOT NULL,       -- Book reference
    SOURCE_TYPE VARCHAR2(50) NOT NULL,  -- PDF|HIGHLIGHT|BOOK|ARTICLE|PERSONAL_NOTE|INSIGHT|WEBSITE
    PAGE_NUMBER NUMBER,
    CHAPTER_TITLE VARCHAR2(500),        -- ← NEW
    SECTION_TITLE VARCHAR2(500),        -- ← NEW
    
    -- Relationships
    BOOK_ID VARCHAR2(36),               -- ← NEW: FK to TOMEHUB_BOOKS
    ORIGINAL_FILE_ID VARCHAR2(36),      -- ← NEW: PDF/EPUB source
    HIGHLIGHTED_BY VARCHAR2(255),       -- ← NEW: Highlight author
    
    -- Quality Metrics
    CONTENT_LENGTH NUMBER,              -- Chunk size
    LANGUAGE_CODE VARCHAR2(5) DEFAULT 'tr',
    FRESHNESS_SCORE NUMBER(3,2),        -- 0.0-1.0 (obsolete content detection)
    QUALITY_FLAGS VARCHAR2(100),        -- Sparse: "INCOMPLETE|CORRUPTED|DUPLICATE"
    
    -- Timestamps
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_UPDATED TIMESTAMP DEFAULT SYSDATE,
    INGESTED_AT TIMESTAMP NOT NULL,     -- ← Partition key
    
    -- Versioning
    CONTENT_VERSION NUMBER DEFAULT 1,   -- For updates
    EMBEDDING_MODEL_VERSION VARCHAR2(20), -- Track embedding lineage
    
    CONSTRAINT fk_content_books FOREIGN KEY (BOOK_ID) 
        REFERENCES TOMEHUB_BOOKS(ID),
    
    CONSTRAINT chk_source_type CHECK (
        SOURCE_TYPE IN ('PDF', 'HIGHLIGHT', 'BOOK', 'ARTICLE', 
                       'PERSONAL_NOTE', 'INSIGHT', 'WEBSITE')
    ),
    
    CONSTRAINT chk_language_code CHECK (
        REGEXP_LIKE(LANGUAGE_CODE, '^[a-z]{2}(-[a-z]{2})?$', 'i')
    )
);

-- Partitioning for TOMEHUB_CONTENT
ALTER TABLE TOMEHUB_CONTENT
PARTITION BY RANGE (INGESTED_AT) (
    PARTITION p_2025_10 VALUES LESS THAN (TO_DATE('2025-11-01', 'YYYY-MM-DD')),
    PARTITION p_2025_11 VALUES LESS THAN (TO_DATE('2025-12-01', 'YYYY-MM-DD')),
    PARTITION p_2025_12 VALUES LESS THAN (TO_DATE('2026-01-01', 'YYYY-MM-DD')),
    PARTITION p_2026_01 VALUES LESS THAN (TO_DATE('2026-02-01', 'YYYY-MM-DD')),
    PARTITION p_2026_02 VALUES LESS THAN (TO_DATE('2026-03-01', 'YYYY-MM-DD')),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

-- 2. TOMEHUB_BOOKS (Enhanced)
CREATE TABLE TOMEHUB_BOOKS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Core Metadata
    TITLE VARCHAR2(500) NOT NULL,
    AUTHOR VARCHAR2(255),               -- ← Enrichment target
    PUBLISHER VARCHAR2(255),            -- ← NEW
    ISBN VARCHAR2(20) UNIQUE,           -- ← NEW
    PUBLICATION_DATE DATE,              -- ← NEW
    
    -- Classification
    SOURCE_TYPE VARCHAR2(50) NOT NULL,  -- Library source (PDF|BOUGHT|PROVIDED|WEB)
    LANGUAGE_CODE VARCHAR2(5) DEFAULT 'tr',
    CATEGORY VARCHAR2(100),             -- Subject classification
    TAGS VARCHAR2(500),                 -- Comma-separated
    SUMMARY CLOB,                       -- ← NEW: Book summary
    
    -- Owner & Access
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    COVER_IMAGE_ID VARCHAR2(36),        -- ← NEW: Image reference
    
    -- Denormalized Content Stats
    TOTAL_CHUNKS NUMBER,                -- ← AUTO from trigger
    TOTAL_PDF_CHUNKS NUMBER DEFAULT 0,
    TOTAL_HIGHLIGHT_CHUNKS NUMBER DEFAULT 0,
    AVERAGE_CHUNK_LENGTH NUMBER,        -- ← Performance metric
    INDEXED_PERCENTAGE NUMBER(3,1) DEFAULT 100,  -- % of chunks indexed
    
    -- Quality Scores
    METADATA_COMPLETENESS NUMBER(3,2) DEFAULT 0,  -- 0-1.0
    CONTENT_QUALITY_SCORE NUMBER(3,2),  -- Avg chunk quality
    SEARCH_RELEVANCE_SCORE NUMBER(3,2), -- From search logs
    
    -- Author Enrichment Tracking
    AUTHOR_SOURCE VARCHAR2(50),         -- 'MANUAL|API|INFERENCE'
    AUTHOR_VERIFIED CHAR(1) DEFAULT 'N',
    AUTHOR_UPDATED_AT TIMESTAMP,
    
    -- Timestamps
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_UPDATED TIMESTAMP DEFAULT SYSDATE,
    LAST_ACCESSED_AT TIMESTAMP,         -- ← NEW: Access tracking
    
    -- Status
    IS_DELETED CHAR(1) DEFAULT 'N' CHECK (IS_DELETED IN ('Y', 'N')),
    DELETION_REASON VARCHAR2(255),      -- Audit trail
    
    CONSTRAINT chk_source_type CHECK (
        SOURCE_TYPE IN ('PDF', 'BOUGHT', 'PROVIDED', 'WEB')
    ),
    
    CONSTRAINT chk_metadata_completeness CHECK (
        METADATA_COMPLETENESS BETWEEN 0 AND 1
    )
);

-- Index for Books
CREATE INDEX idx_books_firebase_uid ON TOMEHUB_BOOKS(FIREBASE_UID);
CREATE INDEX idx_books_author ON TOMEHUB_BOOKS(AUTHOR) WHERE AUTHOR IS NOT NULL;
CREATE INDEX idx_books_isbn ON TOMEHUB_BOOKS(ISBN) WHERE ISBN IS NOT NULL;
CREATE INDEX idx_books_created_at ON TOMEHUB_BOOKS(FIREBASE_UID, CREATED_AT DESC);
```

### Tier 2: Search & Analytics

```sql
-- 3. TOMEHUB_SEARCH_LOGS (Enhanced for Dual-AI)
CREATE TABLE TOMEHUB_SEARCH_LOGS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Query Context
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    QUERY VARCHAR2(2000) NOT NULL,
    INTENT VARCHAR2(50) NOT NULL,       -- SYNTHESIS|DIRECT|FOLLOW_UP|COMPARE|EXPLORE
    LANGUAGE VARCHAR2(5) DEFAULT 'tr',
    
    -- Search Strategy
    SCOPE_MODE VARCHAR2(50),            -- AUTO|SCOPED|UNSCOPED
    TARGET_BOOK_IDS CLOB,               -- JSON array of book IDs
    
    -- Execution Details
    EXECUTION_TIME_MS NUMBER NOT NULL,  -- Total latency
    EXPANSION_TIME_MS NUMBER,           -- Query expansion time
    SEARCH_TIME_MS NUMBER,              -- Retrieval time
    FUSION_TIME_MS NUMBER,              -- RRF fusion time
    JUDGE_TIME_MS NUMBER,               -- Judge AI time
    
    -- Search Strategy Weights (for RRF tuning)
    EXACT_MATCH_WEIGHT NUMBER(3,2),
    LEMMA_MATCH_WEIGHT NUMBER(3,2),
    SEMANTIC_MATCH_WEIGHT NUMBER(3,2),
    GRAPH_MATCH_WEIGHT NUMBER(3,2),     -- ← NEW
    
    -- Results Quality
    RETRIEVED_COUNT NUMBER,             -- Top-K results
    TOP_RESULT_SCORE NUMBER(3,2),       -- Judge AI score ← CRITICAL
    AVERAGE_RESULT_SCORE NUMBER(3,2),   -- ← NEW
    MIN_RESULT_SCORE NUMBER(3,2),
    MAX_RESULT_SCORE NUMBER(3,2),
    
    -- Dual-AI Orchestration
    WORK_AI_MODEL VARCHAR2(100),
    JUDGE_AI_MODEL VARCHAR2(100),
    AUDIT_TRACK_USED CHAR(1) DEFAULT 'N',  -- Fast track vs Audit track
    JUDGE_CONFIDENCE NUMBER(3,2),       -- ← NEW: Judge confidence score
    JUDGE_RECOMMENDATION VARCHAR2(50),  -- ACCEPT|REVISE|REJECT
    
    -- Result Details
    TOP_CONTENT_ID VARCHAR2(36),        -- Best match
    TOP_BOOK_ID VARCHAR2(36),           -- ← NEW
    RESULT_COUNT NUMBER,                -- How many results returned
    
    -- Cache Status
    CACHE_HIT CHAR(1) DEFAULT 'N',
    CACHE_LEVEL VARCHAR2(20),           -- L1|L2|MISS
    
    -- Feedback Loop
    USER_FEEDBACK VARCHAR2(20),         -- HELPFUL|NOT_HELPFUL|NULL
    FEEDBACK_AT TIMESTAMP,
    
    -- Timestamps
    TIMESTAMP TIMESTAMP NOT NULL,       -- ← Partition key
    
    CONSTRAINT chk_intent CHECK (
        INTENT IN ('SYNTHESIS', 'DIRECT', 'FOLLOW_UP', 'COMPARE', 'EXPLORE')
    ),
    
    CONSTRAINT chk_top_result_score CHECK (
        TOP_RESULT_SCORE IS NULL OR (TOP_RESULT_SCORE BETWEEN 0 AND 1)
    )
);

-- Partitioning TOMEHUB_SEARCH_LOGS
ALTER TABLE TOMEHUB_SEARCH_LOGS
PARTITION BY RANGE (TIMESTAMP) (
    PARTITION p_2026_01 VALUES LESS THAN (TO_DATE('2026-02-01', 'YYYY-MM-DD')),
    PARTITION p_2026_02 VALUES LESS THAN (TO_DATE('2026-03-01', 'YYYY-MM-DD')),
    PARTITION p_2026_03 VALUES LESS THAN (TO_DATE('2026-04-01', 'YYYY-MM-DD')),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);

-- 4. TOMEHUB_JUDGE_EVALUATIONS (NEW - Audit Trail)
CREATE TABLE TOMEHUB_JUDGE_EVALUATIONS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Reference
    SEARCH_LOG_ID VARCHAR2(36) NOT NULL,
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    
    -- Evaluation Details
    QUESTION VARCHAR2(2000) NOT NULL,
    CONTENT_CHUNK CLOB,
    GENERATED_ANSWER CLOB,
    
    -- Rubric Scores
    SCORE_GROUNDEDNESS NUMBER(3,2),     -- Is it fact-based? (0-1)
    SCORE_RELEVANCE NUMBER(3,2),        -- Does it answer question? (0-1)
    SCORE_COMPLETENESS NUMBER(3,2),     -- Does it cover all aspects? (0-1)
    SCORE_COHERENCE NUMBER(3,2),        -- Is it readable? (0-1)
    SCORE_CITATION_ACCURACY NUMBER(3,2), -- Are sources correct? (0-1)
    
    -- Final Assessment
    OVERALL_SCORE NUMBER(3,2),          -- Average of rubric scores
    DECISION VARCHAR2(50),              -- ACCEPT|REVISE|REJECT
    REVISION_REASON VARCHAR2(1000),     -- Why rejected or revised
    
    -- Timestamp
    EVALUATED_AT TIMESTAMP DEFAULT SYSDATE,
    
    CONSTRAINT fk_judge_eval_logs FOREIGN KEY (SEARCH_LOG_ID)
        REFERENCES TOMEHUB_SEARCH_LOGS(ID)
);

-- 5. TOMEHUB_INGESTION_LOGS (NEW - Audit)
CREATE TABLE TOMEHUB_INGESTION_LOGS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Task Details
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    BOOK_ID VARCHAR2(36),
    SOURCE_FILE_NAME VARCHAR2(500),
    SOURCE_TYPE VARCHAR2(50),          -- PDF|EPUB|ARTICLE|HIGHLIGHT
    
    -- Processing
    STATUS VARCHAR2(50),               -- STARTED|PROCESSING|COMPLETED|FAILED|PARTIAL
    TOTAL_CHUNKS NUMBER,
    SUCCESSFUL_CHUNKS NUMBER,
    FAILED_CHUNKS NUMBER,
    SKIPPED_CHUNKS NUMBER,
    
    -- Errors
    ERROR_DETAILS CLOB,
    RETRY_COUNT NUMBER DEFAULT 0,
    
    -- Timing
    STARTED_AT TIMESTAMP NOT NULL,
    COMPLETED_AT TIMESTAMP,
    DURATION_SECONDS NUMBER,           -- computed
    
    -- Embeddings
    EMBEDDING_MODEL VARCHAR2(100),
    EMBEDDING_TIME_MS NUMBER,
    
    CONSTRAINT chk_status CHECK (
        STATUS IN ('STARTED', 'PROCESSING', 'COMPLETED', 'FAILED', 'PARTIAL')
    )
);

-- 6. TOMEHUB_CACHE_METADATA (NEW - Cache Invalidation)
CREATE TABLE TOMEHUB_CACHE_METADATA (
    CACHE_KEY VARCHAR2(500) PRIMARY KEY,
    
    -- Content
    CONTENT_TYPE VARCHAR2(50),         -- query_expansion|search_result|intent
    FIREBASE_UID VARCHAR2(255),
    
    -- Models
    EMBEDDING_MODEL_VERSION VARCHAR2(20),
    LLM_MODEL_VERSION VARCHAR2(20),
    
    -- TTL
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    EXPIRES_AT TIMESTAMP,
    
    -- Stats
    HIT_COUNT NUMBER DEFAULT 0,
    LAST_ACCESSED_AT TIMESTAMP,
    
    CONSTRAINT chk_content_type CHECK (
        CONTENT_TYPE IN ('query_expansion', 'search_result', 'intent', 'embedding')
    )
);
```

### Tier 3: Graph & Relationships

```sql
-- 7. TOMEHUB_CONCEPTS (Enhanced)
CREATE TABLE TOMEHUB_CONCEPTS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Definition
    NAME VARCHAR2(500) NOT NULL,
    DESCRIPTION CLOB,
    ALIASES VARCHAR2(1000),            -- ← NEW: Synonym support
    
    -- Embedding
    VEC_EMBEDDING VECTOR(768, FLOAT32),
    
    -- Classification
    CONCEPT_TYPE VARCHAR2(100),        -- IDEA|PERSON|PLACE|EVENT|BOOK|AUTHOR
    CONFIDENCE NUMBER(3,2),            -- Extraction confidence
    LANGUAGE VARCHAR2(5) DEFAULT 'tr',
    
    -- Origin
    SOURCE_CONTENT_ID VARCHAR2(36),
    EXTRACTED_BY VARCHAR2(100),        -- Which service?
    
    -- Timestamps
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_UPDATED TIMESTAMP DEFAULT SYSDATE,
    
    CONSTRAINT chk_concept_type CHECK (
        CONCEPT_TYPE IN ('IDEA', 'PERSON', 'PLACE', 'EVENT', 'BOOK', 'AUTHOR')
    )
);

-- 8. TOMEHUB_RELATIONS (Enhanced)
CREATE TABLE TOMEHUB_RELATIONS (
    ID VARCHAR2(36) PRIMARY KEY,
    
    -- Graph Edge
    SRC_ID VARCHAR2(36) NOT NULL,
    DST_ID VARCHAR2(36) NOT NULL,
    RELATION_TYPE VARCHAR2(100) NOT NULL,  -- MENTIONS|CITES|CONTRASTS|EXPLAINS|SIMILAR
    WEIGHT NUMBER(3,2) DEFAULT 0.5,   -- Importance: 0-1
    
    -- Evidence
    EVIDENCE_COUNT NUMBER,             -- How many chunks mention this relation?
    CONFIDENCE NUMBER(3,2),            -- How confident?
    
    -- Timestamp
    DISCOVERED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_UPDATED TIMESTAMP DEFAULT SYSDATE,
    
    CONSTRAINT fk_rel_src FOREIGN KEY (SRC_ID) 
        REFERENCES TOMEHUB_CONCEPTS(ID),
    CONSTRAINT fk_rel_dst FOREIGN KEY (DST_ID) 
        REFERENCES TOMEHUB_CONCEPTS(ID),
    
    CONSTRAINT chk_relation_type CHECK (
        RELATION_TYPE IN ('MENTIONS', 'CITES', 'CONTRASTS', 'EXPLAINS', 'SIMILAR', 'PRECEDES')
    ),
    
    CONSTRAINT chk_weight CHECK (WEIGHT BETWEEN 0 AND 1),
    
    UNIQUE (SRC_ID, DST_ID, RELATION_TYPE)
);

-- 9. TOMEHUB_FLOW_SEEN (Enhanced)
CREATE TABLE TOMEHUB_FLOW_SEEN (
    CHUNK_ID VARCHAR2(36) NOT NULL,
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    SESSION_ID VARCHAR2(255) NOT NULL,
    DISCOVERY_DEPTH NUMBER DEFAULT 0,   -- ← How deep was discovery?
    SEEN_AT TIMESTAMP NOT NULL,
    ENGAGEMENT_LEVEL VARCHAR2(50),     -- GLANCED|READ|SAVED|CITED
    
    CONSTRAINT pk_flow_seen PRIMARY KEY (CHUNK_ID, FIREBASE_UID, SESSION_ID),
    CONSTRAINT fk_flow_chunk FOREIGN KEY (CHUNK_ID) 
        REFERENCES TOMEHUB_CONTENT(ID)
);

-- 10. TOMEHUB_FLOW_ANCHORS (NEW - Session State)
CREATE TABLE TOMEHUB_FLOW_ANCHORS (
    SESSION_ID VARCHAR2(255) PRIMARY KEY,
    FIREBASE_UID VARCHAR2(255) NOT NULL,
    
    -- Current State
    ANCHOR_CONCEPT_ID VARCHAR2(36),
    CURRENT_PAGE NUMBER,
    TOTAL_PAGES NUMBER,
    
    -- Filters
    RESOURCE_TYPE_FILTER VARCHAR2(500), -- JSON array
    CATEGORY_FILTER VARCHAR2(500),      -- JSON array
    DATE_RANGE_START DATE,
    DATE_RANGE_END DATE,
    
    -- History
    JUMP_HISTORY CLOB,                 -- JSON array of (from_concept, to_concept)
    
    -- Timestamps
    CREATED_AT TIMESTAMP DEFAULT SYSDATE,
    LAST_ACTIVITY_AT TIMESTAMP,
    
    CONSTRAINT fk_anchor_concept FOREIGN KEY (ANCHOR_CONCEPT_ID) 
        REFERENCES TOMEHUB_CONCEPTS(ID)
);
```

---

## Indexing Stratejisi

### Search Performance Indexes

```sql
-- TOMEHUB_CONTENT Indexes
CREATE INDEX idx_content_firebase_uid ON TOMEHUB_CONTENT(FIREBASE_UID);
CREATE INDEX idx_content_title ON TOMEHUB_CONTENT(TITLE);
CREATE INDEX idx_content_book_id ON TOMEHUB_CONTENT(BOOK_ID);
CREATE INDEX idx_content_source_type ON TOMEHUB_CONTENT(SOURCE_TYPE);
CREATE INDEX idx_content_language ON TOMEHUB_CONTENT(LANGUAGE_CODE);

-- Composite for common queries
CREATE INDEX idx_content_uid_type ON TOMEHUB_CONTENT(FIREBASE_UID, SOURCE_TYPE);
CREATE INDEX idx_content_uid_updated ON TOMEHUB_CONTENT(FIREBASE_UID, LAST_UPDATED DESC);
CREATE INDEX idx_content_uid_book ON TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID);

-- Vector Index (Oracle 23ai specific)
CREATE VECTOR INDEX idx_content_embedding 
ON TOMEHUB_CONTENT(VEC_EMBEDDING)
PARAMETERS ('DISTANCE=COSINE');

-- TOMEHUB_SEARCH_LOGS Indexes
CREATE INDEX idx_search_logs_uid ON TOMEHUB_SEARCH_LOGS(FIREBASE_UID);
CREATE INDEX idx_search_logs_timestamp ON TOMEHUB_SEARCH_LOGS(TIMESTAMP DESC);
CREATE INDEX idx_search_logs_intent ON TOMEHUB_SEARCH_LOGS(INTENT);
CREATE INDEX idx_search_logs_execution_time ON TOMEHUB_SEARCH_LOGS(EXECUTION_TIME_MS DESC);

-- Composite for analytics
CREATE INDEX idx_search_logs_uid_date ON TOMEHUB_SEARCH_LOGS(FIREBASE_UID, TIMESTAMP DESC);
CREATE INDEX idx_search_logs_top_score ON TOMEHUB_SEARCH_LOGS(FIREBASE_UID, TOP_RESULT_SCORE DESC) 
WHERE TOP_RESULT_SCORE IS NOT NULL;

-- TOMEHUB_CONCEPTS Indexes
CREATE VECTOR INDEX idx_concept_embedding 
ON TOMEHUB_CONCEPTS(VEC_EMBEDDING)
PARAMETERS ('DISTANCE=COSINE');

CREATE INDEX idx_concept_name ON TOMEHUB_CONCEPTS(NAME);
CREATE INDEX idx_concept_type ON TOMEHUB_CONCEPTS(CONCEPT_TYPE);

-- TOMEHUB_RELATIONS Indexes
CREATE INDEX idx_relations_src_dst ON TOMEHUB_RELATIONS(SRC_ID, DST_ID);
CREATE INDEX idx_relations_type ON TOMEHUB_RELATIONS(RELATION_TYPE);
CREATE INDEX idx_relations_weight ON TOMEHUB_RELATIONS(WEIGHT DESC);

-- Foreign Key Indexes (auto in Oracle, but explicit)
CREATE INDEX idx_content_fk_book ON TOMEHUB_CONTENT(BOOK_ID);
CREATE INDEX idx_rel_fk_src ON TOMEHUB_RELATIONS(SRC_ID);
CREATE INDEX idx_rel_fk_dst ON TOMEHUB_RELATIONS(DST_ID);
```

### Bitmap Indexes for Analytics

```sql
-- Low-cardinality columns
CREATE BITMAP INDEX idx_content_source_bitmap ON TOMEHUB_CONTENT(SOURCE_TYPE);
CREATE BITMAP INDEX idx_content_deleted_bitmap ON TOMEHUB_BOOKS(IS_DELETED);
CREATE BITMAP INDEX idx_search_audit_bitmap ON TOMEHUB_SEARCH_LOGS(AUDIT_TRACK_USED);
CREATE BITMAP INDEX idx_search_feedback_bitmap ON TOMEHUB_SEARCH_LOGS(USER_FEEDBACK);
```

---

## Partitioning Planı

### Stratejisi

**RANGE partitioning by date** (INGESTED_AT / TIMESTAMP):
- Monthly partitions for content & logs
- Enables partition pruning for date-range queries
- Manages table growth (1000+ new rows/day)
- Enables faster archive/purge of old data

### İmplementasyon

```sql
-- TOMEHUB_CONTENT: Monthly by INGESTED_AT (Already shown above)

-- TOMEHUB_SEARCH_LOGS: Monthly by TIMESTAMP (Already shown above)

-- Archive partition for logs older than 6 months
CREATE TABLE TOMEHUB_SEARCH_LOGS_ARCHIVE AS
SELECT * FROM TOMEHUB_SEARCH_LOGS
WHERE TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE), -6);

-- Cleanup job
BEGIN
  DBMS_SCHEDULER.CREATE_JOB (
    job_name => 'archive_old_search_logs',
    job_type => 'PLSQL_BLOCK',
    job_action => 'BEGIN
      DELETE FROM TOMEHUB_SEARCH_LOGS 
      WHERE TIMESTAMP < ADD_MONTHS(TRUNC(SYSDATE), -12);
      COMMIT;
    END;',
    repeat_interval => 'FREQ=MONTHLY;BYMONTHDAY=1',
    enabled => TRUE
  );
END;
/
```

---

## Caching Layer

### L1 Cache (In-Memory)

```python
# From config.py - Enhanced

class CacheConfig:
    # Query Expansions
    QUERY_EXPANSION_TTL = 600  # 10 minutes
    QUERY_EXPANSION_MAXSIZE = 1000
    
    # Search Results (user-specific)
    SEARCH_RESULT_TTL = 600  # 10 minutes
    SEARCH_RESULT_MAXSIZE = 500
    SEARCH_RESULT_KEY_PATTERN = f"search:{firebase_uid}:{query_hash}"
    
    # Intent Classifications
    INTENT_TTL = 3600  # 1 hour
    INTENT_MAXSIZE = 500
    
    # Embeddings (ephemeral)
    EMBEDDING_CACHE_TTL = 300  # 5 minutes
    EMBEDDING_CACHE_MAXSIZE = 100
    
    # Concept Cache
    CONCEPT_TTL = 3600  # 1 hour
    CONCEPT_MAXSIZE = 2000

# Cache Key Strategy
def generate_cache_key(cache_type: str, **params) -> str:
    """
    Format: cache_type:model_v:uid_context:params
    Includes model versions for auto-invalidation
    """
    version_hash = hashlib.md5(
        f"{EMBEDDING_MODEL_VERSION}:{LLM_MODEL_VERSION}".encode()
    ).hexdigest()[:8]
    
    # Example: search_result:em4f2b1c:uid123:q_hash_abc
    return f"{cache_type}:{version_hash}:{params.get('firebase_uid', 'global')}:{hash_params(params)}"
```

### L2 Cache (Redis Optional)

```python
# redis_service.py (Optional)

class RedisCache:
    """Shared cache across instances"""
    
    # Longer TTLs for shared data
    SHARED_SEARCH_RESULT_TTL = 1800  # 30 minutes
    SHARED_QUERY_EXPANSION_TTL = 3600  # 1 hour
    SHARED_CONCEPT_TTL = 7200  # 2 hours
    
    async def get(self, key: str) -> Optional[Any]:
        """Get from Redis with automatic JSON deserialization"""
        try:
            value = await self.redis.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None
    
    async def set(self, key: str, value: Any, ttl: int) -> bool:
        """Set in Redis with TTL"""
        try:
            await self.redis.setex(key, ttl, json.dumps(value))
            return True
        except Exception:
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache by pattern (e.g., 'search_result:*:uid123:*')"""
        # Used when user updates book metadata
        return await self.redis.delete_match(pattern)
```

### Cache Invalidation Strategy

```python
# From services/cache_service.py - Enhanced

class CacheInvalidationManager:
    
    async def invalidate_on_model_upgrade(self):
        """Called when EMBEDDING_MODEL_VERSION or LLM_MODEL_VERSION changes"""
        # All old cache keys become invalid (version hash won't match)
        # No manual deletion needed - natural expiration
        logger.info("Model upgrade detected - old cache keys auto-invalidated")
    
    async def invalidate_on_content_change(self, firebase_uid: str, book_id: str):
        """When content is ingested/updated"""
        patterns = [
            f"search_result:*:{firebase_uid}:*",  # User's search cache
            f"query_expansion:*:{firebase_uid}:*",
            f"concept:*"  # Concepts may have changed
        ]
        for pattern in patterns:
            await redis_cache.invalidate_pattern(pattern)
    
    async def invalidate_on_book_metadata_change(self, book_id: str):
        """When book metadata (author, title) changes"""
        # Flow/feed recommendations affected
        await redis_cache.invalidate_pattern("flow_*")
    
    async def invalidate_on_judge_loop_change(self):
        """When rubric or judge AI model changes"""
        # All search result scores potentially invalid
        await redis_cache.invalidate_pattern("search_result:*")
```

---

## Performance Optimizations

### 1. Read/Write Pool Separation

```python
# config.py - Enhanced

class Settings:
    # Total pool
    DB_POOL_MAX = 40
    
    # Separate sizing: 75% reads, 25% writes
    DB_READ_POOL_MAX = 30   # For SELECT, search, analytics
    DB_WRITE_POOL_MAX = 10  # For INSERT/UPDATE/DELETE, ingestion
    
    # Separate timeouts
    DB_READ_TIMEOUT = 30  # Longer for complex queries
    DB_WRITE_TIMEOUT = 15  # Shorter for transactional consistency
```

```python
# infrastructure/db_manager.py - Enhanced

class DatabaseManager:
    
    @staticmethod
    def get_read_connection():
        """Borrow from read pool - for SELECT, analytics queries"""
        return READ_POOL.acquire()
    
    @staticmethod
    def get_write_connection():
        """Borrow from write pool - for INSERT/UPDATE/DELETE, ingestion"""
        return WRITE_POOL.acquire()
    
    @staticmethod
    def get_connection():
        """Default - intelligent selection based on query type"""
        # For backward compatibility, detect query type
        # or let caller choose explicitly
        return READ_POOL.acquire()  # Default to reads
```

### 2. Query Plan Optimization

```sql
-- Star Schema for Analytics (Optional)
CREATE TABLE DIM_BOOKS AS
SELECT 
    BOOK_ID, TITLE, AUTHOR, FIREBASE_UID,
    SOURCE_TYPE, LANGUAGE_CODE, CATEGORY,
    CREATED_AT
FROM TOMEHUB_BOOKS;

CREATE TABLE FACT_SEARCHES AS
SELECT 
    SEARCH_LOG_ID, FIREBASE_UID, BOOK_ID,
    EXECUTION_TIME_MS, TOP_RESULT_SCORE,
    JUDGMENT_SCORE, TIMESTAMP
FROM TOMEHUB_SEARCH_LOGS;

-- Analytics queries now much faster
SELECT 
    b.AUTHOR,
    AVG(f.EXECUTION_TIME_MS) as avg_latency,
    COUNT(*) as query_count
FROM FACT_SEARCHES f
JOIN DIM_BOOKS b ON f.BOOK_ID = b.BOOK_ID
WHERE f.TIMESTAMP >= SYSDATE - 7
GROUP BY b.AUTHOR;
```

### 3. Denormalization for Speed

```sql
-- TOMEHUB_BOOKS denormalized fields
ALTER TABLE TOMEHUB_BOOKS ADD (
    TOTAL_CHUNKS NUMBER,                -- Trigger-maintained
    TOTAL_PDF_CHUNKS NUMBER,            -- Cached count
    AVG_CHUNK_LENGTH NUMBER,            -- For relevance
    SEARCH_RELEVANCE_SCORE NUMBER(3,2)  -- From analytics
);

-- Trigger to sync TOTAL_CHUNKS
CREATE OR REPLACE TRIGGER tr_content_chunks_sync
AFTER INSERT OR DELETE ON TOMEHUB_CONTENT
FOR EACH ROW
DECLARE
    v_book_id VARCHAR2(36);
    v_count NUMBER;
BEGIN
    v_book_id := :NEW.BOOK_ID || :OLD.BOOK_ID;  -- Handle both INSERT/DELETE
    
    SELECT COUNT(*) INTO v_count
    FROM TOMEHUB_CONTENT
    WHERE BOOK_ID = v_book_id;
    
    UPDATE TOMEHUB_BOOKS
    SET TOTAL_CHUNKS = v_count,
        LAST_UPDATED = SYSDATE
    WHERE ID = v_book_id;
END;
/
```

### 4. Semantic Search Optimization

```python
# services/search_service.py - Optimized for VECTOR INDEX

async def semantic_search_optimized(
    query_embedding: List[float],
    firebase_uid: str,
    limit: int = 20,
    book_ids: Optional[List[str]] = None
) -> List[Dict]:
    """
    Optimized semantic search using:
    1. Filtering (WHERE) before vector search
    2. Vector index on VEC_EMBEDDING
    3. Batch fetching of CLOB content (avoid SELECT CONTENT_CHUNK in loop)
    4. Compression of metadata
    """
    
    # Build filtering conditions
    where_clauses = [
        "FIREBASE_UID = :uid",
        "CONTENT_LENGTH > 100",  # Skip tiny chunks
    ]
    
    if book_ids:
        where_clauses.append(f"BOOK_ID IN ({','.join(['?' for _ in book_ids])})")
    
    where_sql = " AND ".join(where_clauses)
    
    # Vector search with filters!
    query = f"""
    SELECT 
        ID, TITLE, BOOK_ID, SOURCE_TYPE, PAGE_NUMBER,
        VECTOR_DISTANCE(VEC_EMBEDDING, :vec_embedding) as distance,
        RANKING() OVER (
            ORDER BY VECTOR_DISTANCE(VEC_EMBEDDING, :vec_embedding)
        ) as rank
    FROM TOMEHUB_CONTENT
    WHERE {where_sql}
    ORDER BY distance
    LIMIT :limit
    """
    
    # Fetch using vector index
    results = await db.fetch_all(query, {
        'uid': firebase_uid,
        'vec_embedding': query_embedding,
        'limit': limit,
        'book_ids': book_ids or []
    })
    
    # Batch load content chunks (avoid N+1)
    chunk_ids = [r['ID'] for r in results]
    contents = await db.fetch_all(
        "SELECT ID, CONTENT_CHUNK FROM TOMEHUB_CONTENT WHERE ID IN (:ids)",
        {'ids': chunk_ids}
    )
    content_map = {c['ID']: c['CONTENT_CHUNK'] for c in contents}
    
    # Assemble response
    return [
        {
            **r,
            'content': content_map[r['ID']],
            'distance': r['distance']
        }
        for r in results
    ]
```

### 5. Aggregation Query Optimization

```sql
-- Pre-aggregated metrics table
CREATE TABLE TOMEHUB_SEARCH_METRICS_DAILY AS
SELECT
    TRUNC(TIMESTAMP) as search_date,
    FIREBASE_UID,
    INTENT,
    COUNT(*) as query_count,
    AVG(EXECUTION_TIME_MS) as avg_latency,
    MAX(EXECUTION_TIME_MS) as max_latency,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME_MS) as p95_latency,
    AVG(TOP_RESULT_SCORE) as avg_quality_score,
    SUM(CASE WHEN AUDIT_TRACK_USED = 'Y' THEN 1 ELSE 0 END) as audit_count
FROM TOMEHUB_SEARCH_LOGS
GROUP BY TRUNC(TIMESTAMP), FIREBASE_UID, INTENT;

-- Refresh daily via job
BEGIN
  DBMS_SCHEDULER.CREATE_JOB (
    job_name => 'refresh_search_metrics',
    job_type => 'PLSQL_BLOCK',
    job_action => 'BEGIN
      DELETE FROM TOMEHUB_SEARCH_METRICS_DAILY 
      WHERE search_date = TRUNC(SYSDATE - 1);
      
      INSERT INTO TOMEHUB_SEARCH_METRICS_DAILY 
      SELECT ... FROM TOMEHUB_SEARCH_LOGS WHERE TRUNC(TIMESTAMP) = TRUNC(SYSDATE - 1);
      COMMIT;
    END;',
    repeat_interval => 'FREQ=DAILY;BYHOUR=2',
    enabled => TRUE
  );
END;
/
```

---

## Migration Roadmap

### Phase 1: Preparation (Week 1)

**Tasks:**
1. ✅ Create new tables (TOMEHUB_JUDGE_EVALUATIONS, TOMEHUB_INGESTION_LOGS, TOMEHUB_CACHE_METADATA, TOMEHUB_FLOW_ANCHORS)
2. ✅ Add new nullable columns to existing tables (BOOK_ID to CONTENT, AUTHOR_SOURCE to BOOKS)
3. ✅ Create indexes
4. ✅ Create triggers for denormalization

**Validations:**
- Zero data loss
- Backward compatibility with existing queries

### Phase 2: Data Migration (Week 2)

**Tasks:**
1. Populate BOOK_ID in TOMEHUB_CONTENT via STRING MATCH (TITLE)
   ```sql
   UPDATE TOMEHUB_CONTENT c
   SET BOOK_ID = (SELECT ID FROM TOMEHUB_BOOKS b 
                  WHERE TRIM(b.TITLE) = TRIM(c.TITLE) 
                  AND b.FIREBASE_UID = c.FIREBASE_UID
                  AND ROWNUM = 1)
   WHERE BOOK_ID IS NULL;
   ```

2. Populate TOTAL_CHUNKS, AVERAGE_CHUNK_LENGTH in TOMEHUB_BOOKS
   ```sql
   UPDATE TOMEHUB_BOOKS b
   SET TOTAL_CHUNKS = (SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                       WHERE BOOK_ID = b.ID),
       AVERAGE_CHUNK_LENGTH = (SELECT AVG(CONTENT_LENGTH) FROM TOMEHUB_CONTENT 
                               WHERE BOOK_ID = b.ID)
   WHERE TOTAL_CHUNKS IS NULL;
   ```

3. Backfill AUTHOR_SOURCE = 'INFERENCE' for non-NULL authors

4. Enrich author metadata via OpenLibrary API
   ```python
   async def enrich_authors():
       for book in session.query(Book).filter(Book.author.is_(None)):
           author = await openlibrary_api.search_by_title(book.title)
           if author:
               book.author = author
               book.author_source = 'API'
               book.author_verified = 'Y'
   ```

**Validations:**
- 100% BOOK_ID population
- TOTAL_CHUNKS accuracy (cross-check with SELECT COUNT)
- No NULL authors (or track source)

### Phase 3: Index & Partition Activation (Week 2-3)

**Tasks:**
1. Apply partitioning to TOMEHUB_CONTENT, TOMEHUB_SEARCH_LOGS
2. Enable vector indexes
3. Collect table statistics for optimizer

```sql
EXEC DBMS_STATS.GATHER_TABLE_STATS('ADMIN', 'TOMEHUB_CONTENT');
EXEC DBMS_STATS.GATHER_TABLE_STATS('ADMIN', 'TOMEHUB_BOOKS');
EXEC DBMS_STATS.GATHER_TABLE_STATS('ADMIN', 'TOMEHUB_SEARCH_LOGS');
```

### Phase 4: Application Code Updates (Week 3)

**Tasks:**
1. Update search queries to use VECTOR INDEX
2. Implement cache invalidation patterns
3. Add Judge AI evaluation logging
4. Add read/write pool selection logic

```python
# search_service.py
async def search():
    # Use read pool
    async with DatabaseManager.get_read_connection() as conn:
        results = await conn.fetch(semantic_search_query)
    return results

# ingestion_service.py
async def ingest():
    # Use write pool
    async with DatabaseManager.get_write_connection() as conn:
        await conn.execute(insert_content_query)
        # Log ingestion
        await write_pool.execute(insert_ingestion_log)
```

5. Populate TOP_RESULT_SCORE for past searches
   ```python
   async def backfill_judge_scores():
       # For each NULL TOP_RESULT_SCORE in search logs
       # Re-run through Judge AI to score
       # Update TOMEHUB_SEARCH_LOGS.TOP_RESULT_SCORE
   ```

### Phase 5: Testing & Validation (Week 4)

**Tasks:**
1. Performance regression testing (latency benchmarks)
2. Data integrity validation
3. Cache hit rate monitoring

### Phase 6: Production Rollout (Week 5)

**Tasks:**
1. Gradual traffic shift (10% → 50% → 100%)
2. Monitor metrics (latency, quality scores, cache stats)
3. Rollback plan ready

---

## Implementation Summary by Component

### Code Changes Required

#### 1. Database Module (`infrastructure/db_manager.py`)

```python
class DatabaseManager:
    """Enhanced with read/write pool separation"""
    
    _read_pool = None
    _write_pool = None
    
    @staticmethod
    def init_pools():
        _read_pool = oracledb.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=settings.DB_DSN,
            min=5,
            max=settings.DB_READ_POOL_MAX,
            increment=2
        )
        _write_pool = oracledb.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=settings.DB_DSN,
            min=2,
            max=settings.DB_WRITE_POOL_MAX,
            increment=1
        )
    
    @staticmethod
    def get_read_connection():
        return _read_pool.acquire()
    
    @staticmethod
    def get_write_connection():
        return _write_pool.acquire()
```

#### 2. Search Service (`services/search_service.py`)

- Use VECTOR INDEX via `VECTOR_DISTANCE()` function
- Implement semantic search filtering before vector search
- Add execution time tracking for all phases
- Log to TOMEHUB_JUDGE_EVALUATIONS after judge AI

#### 3. Ingestion Service (`services/ingestion_service.py`)

- Wrap INSERT/UPDATE in write pool
- Log to TOMEHUB_INGESTION_LOGS
- Trigger author enrichment for new books
- Populate BOOK_ID from TITLE match

#### 4. Cache Service (`services/cache_service.py`)

- Implement cache key generation with model versions
- Add cache invalidation patterns
- Monitor cache hit rates
- Log cache usage to TOMEHUB_CACHE_METADATA

#### 5. Judge AI (`services/judge_ai_service.py`)

- Log all evaluations to TOMEHUB_JUDGE_EVALUATIONS
- Populate rubric scores
- Track overall scores in TOMEHUB_SEARCH_LOGS.TOP_RESULT_SCORE

---

## Monitoring & KPIs

### Query Performance

```sql
-- Dashboard Query 1: Avg latency by intent
SELECT 
    INTENT,
    ROUND(AVG(EXECUTION_TIME_MS)) as avg_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME_MS) as p95_ms,
    COUNT(*) as queries
FROM TOMEHUB_SEARCH_LOGS
WHERE TIMESTAMP > SYSDATE - 7
GROUP BY INTENT
ORDER BY avg_ms DESC;
```

### Data Quality

```sql
-- Dashboard Query 2: Author metadata completeness
SELECT 
    FIREBASE_UID,
    ROUND(100 * SUM(CASE WHEN AUTHOR IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as author_pct,
    ROUND(AVG(TOTAL_CHUNKS)) as avg_chunks_per_book,
    COUNT(*) as total_books
FROM TOMEHUB_BOOKS
WHERE IS_DELETED = 'N'
GROUP BY FIREBASE_UID;
```

### Cache Effectiveness

```python
# From monitoring service
cache_hit_rate = cache_hits / (cache_hits + cache_misses)
cache_eviction_rate = cache_evictions / cache_writes

# Target: >70% hit rate, <5% eviction rate
```

### Judge AI Quality

```sql
-- Avg quality score by model
SELECT 
    WORK_AI_MODEL,
    JUDGE_AI_MODEL,
    ROUND(AVG(TOP_RESULT_SCORE), 3) as avg_score,
    ROUND(AVG(JUDGE_CONFIDENCE), 3) as avg_confidence,
    COUNT(*) as evaluations
FROM TOMEHUB_SEARCH_LOGS
WHERE TOP_RESULT_SCORE IS NOT NULL
AND TIMESTAMP > SYSDATE - 30
GROUP BY WORK_AI_MODEL, JUDGE_AI_MODEL;
```

---

## Configuration Example

```ini
# .env.production

# Database
DB_POOL_MIN=5
DB_POOL_MAX=40
DB_READ_POOL_MAX=30
DB_WRITE_POOL_MAX=10

# Cache
CACHE_ENABLED=true
CACHE_L1_MAXSIZE=1000
CACHE_L1_TTL=600
REDIS_URL=redis://cache-cluster:6379/0

# Models (versioning for cache invalidation)
EMBEDDING_MODEL_VERSION=v2
LLM_MODEL_VERSION=v1
JUDGE_MODEL_VERSION=v1

# Partitioning & Archival
ARCHIVE_LOGS_OLDER_THAN_MONTHS=6
PURGE_LOGS_OLDER_THAN_MONTHS=12
MONTHLY_PARTITION_ENABLED=true

# Monitoring
QUERY_LATENCY_SLO_MS=2000
JUDGE_SCORE_TARGET=0.75
CACHE_HIT_RATE_TARGET=0.70
```

---

## Next Steps

1. **Review & Approval** - Stakeholder review of proposed schema
2. **POC** - Test vector index performance on TOMEHUB_CONTENT
3. **Backup Strategy** - Plan full backup before Phase 1 migration
4. **Communication** - Notify dependent teams of API changes
5. **Rollback Plan** - Document revert procedures for each phase

---

**Taslak Durum:** ✅ Hazır tasarım ve implementasyon rehberi  
**Sonraki:** Hangi faz üzerinde başlamak istersiniz?

