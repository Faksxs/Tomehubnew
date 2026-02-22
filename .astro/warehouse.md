# TomeHub Oracle 23ai Schema Reference

**Generated:** 2026-02-22  
**Database:** FCE4GECR (Oracle 23ai Enterprise)  
**Location:** O̧Azure Cloud Engineered Systems  
**Character Set:** AL32UTF8 (UTF-8 Unicode, Turkish support ✓)

---

## Quick Table Lookup

| Table | Rows | Size | Purpose |
|-------|------|------|---------|
| TOMEHUB_CONTENT | 4,167 | 53MB | Core chunks + vector embeddings |
| TOMEHUB_EXTERNAL_BOOK_META | ~100 | 14.5MB | Book metadata & enrichment |
| TOMEHUB_CONCEPTS | 693 | 3MB | Graph vertices (knowledge entities) |
| TOMEHUB_SEARCH_LOGS | 1,249 | 0.38MB | Query analytics & performance |
| TOMEHUB_RELATIONS | 506 | 0.06MB | Graph edges (concept relationships) |
| TOMEHUB_INGESTED_FILES | ~50 | 2.25MB | Source file tracking |
| TOMEHUB_CHAT_SESSIONS | ~15 | 0.25MB | User conversation sessions |
| TOMEHUB_CHAT_MESSAGES | ~200 | 0.38MB | Chat message history |
| TOMEHUB_FLOW_SEEN | 0 | 0.69MB | Session memory tracking (empty) |
| TOMEHUB_BOOK_EPISTEMIC_METRICS | ~88 | 2MB | Knowledge quality metrics per book |
| TOMEHUB_CONTENT_CATEGORIES | ~100 | 0.13MB | Content category mappings |
| TOMEHUB_CONTENT_TAGS | ~150 | 0.06MB | Content tags |
| TOMEHUB_FEEDBACK | ~20 | 0.06MB | User feedback |
| TOMEHUB_BOOKS | 88 | 0.06MB | Book registry |
| TOMEHUB_FILE_REPORTS | ~50 | 0.06MB | Ingestion reports |
| TOMEHUB_EXTERNAL_ENTITIES | ~30 | 0.06MB | Knowledge graph entities |
| TOMEHUB_EXTERNAL_EDGES | ~50 | 0.06MB | Knowledge graph relations |
| TOMEHUB_CONCEPT_CHUNKS | ~1000 | 0.13MB | Concept-chunk mappings |

**Total Tables:** 18  
**Total Storage:** 77.25 MB  
**Utilization:** 26% (296.31 MB allocated)

---

## Core Tables

### 📦 TOMEHUB_CONTENT

**Purpose:** Core knowledge base - stores all content chunks from ingested sources  
**Rows:** 4,167  
**Size:** 53.00 MB  
**Primary Key:** ID (UUID)

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| ID | VARCHAR2(36) | Unique chunk identifier | ✓ PK |
| FIREBASE_UID | VARCHAR2(255) | User identifier for multi-tenancy | ✓ |
| CONTENT_CHUNK | CLOB | Text content (may be very large) | |
| VEC_EMBEDDING | VECTOR(768, FLOAT32) | 768-dimensional embedding (Gemini) | ✓ IDX_TOMEHUB_VEC_EMBEDDING |
| SOURCE_TYPE | VARCHAR2(50) | PDF, HIGHLIGHT, BOOK, ARTICLE, INSIGHT, PERSONAL_NOTE, WEBSITE | ✓ IDX_TOMEHUB_SOURCE_TYPE |
| TITLE | VARCHAR2(500) | Content title/book name | |
| AUTHOR | VARCHAR2(255) | Author name | |
| PAGE_NUMBER | NUMBER | Page reference | |
| BOOK_ID | NUMBER | Reference to TOMEHUB_BOOKS | ✓ IDX_CONTENT_BOOK_ID |
| CREATED_AT | TIMESTAMP | Ingestion time | |
| UPDATED_AT | TIMESTAMP | Last update time | |
| NORMALIZED_CONTENT | VARCHAR2(4000) | Lemmatized/normalized for full-text search | ✓ IDX_NORM_CONTENT |

**Key Constraints:**
- Foreign Key: BOOK_ID → TOMEHUB_BOOKS(BOOK_ID)
- Constraint: SOURCE_TYPE IN ('PDF', 'NOTES', 'EPUB', 'PDF_CHUNK', 'ARTICLE', 'WEBSITE', 'PERSONAL_NOTE')

**Sample Query - Find content by user:**
```sql
SELECT TITLE, SOURCE_TYPE, CREATED_AT
FROM TOMEHUB_CONTENT
WHERE FIREBASE_UID = 'your-uid'
ORDER BY CREATED_AT DESC;
```

---

### 📚 TOMEHUB_BOOKS

**Purpose:** Book/source registry  
**Rows:** 88  
**Size:** 0.06 MB  
**Primary Key:** BOOK_ID

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| BOOK_ID | NUMBER | Auto-increment ID | ✓ PK |
| FIREBASE_UID | VARCHAR2(255) | Owner user | ✓ IDX_BOOKS_FIREBASE_UID |
| TITLE | VARCHAR2(500) | Book title | |
| AUTHOR | VARCHAR2(255) | Author name | |
| ISBN | VARCHAR2(20) | International Standard Book Number | |
| SOURCE_URL | VARCHAR2(2000) | Link to source | |
| CREATED_AT | TIMESTAMP | Metadata creation time | |
| UPDATED_AT | TIMESTAMP | Last update | |

**Key Concepts:**
- Multi-tenant: Each user has own books
- Top books: Leviathan (521 chunks), Klasik Sosyoloji (438), İslam Felsefesi (402)

---

### 🔍 TOMEHUB_SEARCH_LOGS

**Purpose:** Track all search queries for analytics  
**Rows:** 1,249  
**Size:** 0.38 MB  
**Primary Key:** ID

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| ID | NUMBER | Auto-increment | ✓ PK |
| FIREBASE_UID | VARCHAR2(255) | User who searched | ✓ IDX_SEARCH_LOGS_UID |
| QUERY_TEXT | CLOB | Search query | |
| INTENT | VARCHAR2(50) | SEMANTIC_SEARCH, EXACT_MATCH, LEMMA_MATCH, HYBRID | |
| STRATEGY_WEIGHTS | CLOB/JSON | Fusion strategy weights (RRF) | |
| EXECUTION_TIME_MS | NUMBER | Query latency in milliseconds | |
| RRF_SCORE | FLOAT | Reciprocal Rank Fusion result score (0-1) | |
| RESULT_COUNT | NUMBER | Number of results returned | |
| CREATED_AT | TIMESTAMP | Query timestamp | ✓ IDX_SEARCH_LOGS_TIME |

**Indexes:**
- IDX_SEARCH_LOGS_UID: User-based query history
- IDX_SEARCH_LOGS_TIME: Time-series analysis
- IDX_SEARCH_LOGS_SCORE_TIME: Combined time + quality analysis

**Key Metrics:**
- Total logs: 1,249
- Avg execution time: 956ms
- P95 latency: 1,823ms
- Slow queries (>2s): 4.6%
- Most common intent: SEMANTIC_SEARCH (52%)

**Sample Query - Daily analytics:**
```sql
SELECT 
  TRUNC(CREATED_AT) as date,
  INTENT,
  COUNT(*) as query_count,
  AVG(EXECUTION_TIME_MS) as avg_latency,
  PERCENTILE_CONT(0.95) WITHIN GROUP(ORDER BY EXECUTION_TIME_MS) as p95
FROM TOMEHUB_SEARCH_LOGS
GROUP BY TRUNC(CREATED_AT), INTENT
ORDER BY date DESC;
```

---

### 💡 TOMEHUB_CONCEPTS

**Purpose:** Knowledge graph vertices - entities and concepts extracted from content  
**Rows:** 693  
**Size:** 3.00 MB  
**Primary Key:** CONCEPT_ID

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| CONCEPT_ID | NUMBER | Auto-increment | ✓ PK |
| FIREBASE_UID | VARCHAR2(255) | Owner | |
| NAME | VARCHAR2(255) | Concept name | ✓ UIDX_CONCEPTS_NAME_LOWER |
| DESCRIPTION | CLOB | Definition/explanation | |
| DESCRIPTION_VECTOR | VECTOR(768, FLOAT32) | Embedding of description | ✓ IDX_CONCEPTS_DESC_VEC |
| VECTOR | VECTOR(768, FLOAT32) | Concept embedding | ✓ IDX_CONCEPTS_VEC |
| CREATED_AT | TIMESTAMP | Creation time | |
| UPDATED_AT | TIMESTAMP | Last update | |

**Key Features:**
- Dual vectors: name + description embeddings for flexible search
- 693 concepts extracted from 4,167 content chunks
- Supports semantic concept discovery

**Sample Query - Find related concepts:**
```sql
SELECT c1.NAME, c2.NAME, VECTOR_DISTANCE(c1.VECTOR, c2.VECTOR) as similarity
FROM TOMEHUB_CONCEPTS c1
JOIN TOMEHUB_CONCEPTS c2 ON c1.FIREBASE_UID = c2.FIREBASE_UID
WHERE VECTOR_DISTANCE(c1.VECTOR, c2.VECTOR) < 0.3
AND c1.CONCEPT_ID < c2.CONCEPT_ID;
```

---

### 🔗 TOMEHUB_RELATIONS

**Purpose:** Knowledge graph edges - relationships between concepts  
**Rows:** 506  
**Size:** 0.06 MB  
**Primary Key:** RELATION_ID

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| RELATION_ID | NUMBER | Auto-increment | ✓ PK, UIDX_RELATION_TRIPLE |
| SOURCE_CONCEPT_ID | NUMBER | Origin concept | ✓ IDX_RELATIONS_SRC_ID |
| DEST_CONCEPT_ID | NUMBER | Target concept | ✓ IDX_RELATIONS_DST_ID |
| RELATION_TYPE | VARCHAR2(100) | "related_to", "parent_of", "contradicts", etc | |
| WEIGHT | FLOAT | Importance score (0-1) | |
| CREATED_AT | TIMESTAMP | | |

**Key Properties:**
- 506 edges connecting 693 nodes
- Average graph degree: 1.46 (sparse, connectivity improvable)
- Supports multi-hop traversal for discovery

**Traversal Example:**
```sql
-- Find all concepts within 2 hops of "Dasein"
WITH RECURSIVE concept_path AS (
  SELECT DEST_CONCEPT_ID as concept_id, 1 as depth
  FROM TOMEHUB_RELATIONS
  WHERE SOURCE_CONCEPT_ID = (SELECT CONCEPT_ID FROM TOMEHUB_CONCEPTS WHERE NAME = 'Dasein')
  
  UNION ALL
  
  SELECT r.DEST_CONCEPT_ID, cp.depth + 1
  FROM concept_path cp
  JOIN TOMEHUB_RELATIONS r ON cp.concept_id = r.SOURCE_CONCEPT_ID
  WHERE cp.depth < 2
)
SELECT c.NAME, cp.depth
FROM concept_path cp
JOIN TOMEHUB_CONCEPTS c ON cp.concept_id = c.CONCEPT_ID;
```

---

### 💬 TOMEHUB_CHAT_SESSIONS

**Purpose:** Conversation session tracking  
**Rows:** ~15  
**Size:** 0.25 MB  

| Column | Type | Description | Indexed |
|--------|------|-------------|---------|
| SESSION_ID | VARCHAR2(36) | UUID | ✓ PK |
| FIREBASE_UID | VARCHAR2(255) | User | ✓ IDX_CHAT_UID |
| TITLE | VARCHAR2(500) | Session title | ✓ IDX_CHAT_TITLE_LOCKED |
| CREATED_AT | TIMESTAMP | Session start | |
| UPDATED_AT | TIMESTAMP | Last activity | |
| IS_LOCKED | BOOLEAN | Archived/read-only | |
| TAGS | JSON | User-defined tags | ✓ IDX_CHAT_TAGS_JSON |

---

### 📊 TOMEHUB_SEARCH_LOGS (Analytics)

Used by `/data:analyzing-data` and `tomehub_search_analytics` DAG for daily analytics

**Concept Pattern:**
- Question: "How many searches per intent?"
- Table: TOMEHUB_SEARCH_LOGS
- Key Column: INTENT, CREATED_AT

---

## Schema Patterns

### Multi-Tenancy
**Pattern:** FIREBASE_UID on every user-scoped table  
**Tables:** TOMEHUB_CONTENT, TOMEHUB_BOOKS, TOMEHUB_CONCEPTS, TOMEHUB_SEARCH_LOGS

**Example - Isolate user data:**
```sql
SELECT * FROM TOMEHUB_CONTENT
WHERE FIREBASE_UID = 'user-123'
AND SOURCE_TYPE = 'PDF';
```

### Vector Search
**Pattern:** VECTOR columns with ANN indexing  
**Tables:** TOMEHUB_CONTENT (VEC_EMBEDDING), TOMEHUB_CONCEPTS (VECTOR, DESCRIPTION_VECTOR)

**Example - Find similar content:**
```sql
SELECT TITLE, VECTOR_DISTANCE(VEC_EMBEDDING, (SELECT VEC_EMBEDDING FROM TOMEHUB_CONTENT LIMIT 1)) as distance
FROM TOMEHUB_CONTENT
ORDER BY distance
FETCH FIRST 10 ROWS ONLY;
```

### Knowledge Graph
**Pattern:** Concept + Relation tables for property graph traversal  
**Tables:** TOMEHUB_CONCEPTS, TOMEHUB_RELATIONS

**Degree Distribution:**
- Min degree: 0 (isolated concepts)
- Max degree: ~5-10 (hub concepts)
- Avg degree: 1.46 (sparse - room for improvement)

---

## Performance Indexes

**Total Indexes:** 35+

### Critical for RAG/Search
- `IDX_TOMEHUB_VEC_EMBEDDING`: Vector similarity (ANN)
- `IDX_NORM_CONTENT`: Full-text search (lemmatized)
- `IDX_TOMEHUB_SOURCE_TYPE`: Source filtering
- `IDX_TOMEHUB_USER_SOURCE`: User + source combo

### Critical for Analytics
- `IDX_SEARCH_LOGS_UID`: User query history
- `IDX_SEARCH_LOGS_TIME`: Time-series trending
- `IDX_SEARCH_LOGS_SCORE_TIME`: Joined analytics

### Graph-Specific
- `IDX_RELATIONS_SRC_ID`: Forward traversal
- `IDX_RELATIONS_DST_ID`: Reverse traversal
- `IDX_CONCEPTS_VEC`: Concept similarity

---

## Tablespace Info

| Tablespace | Used | Allocated |
|------------|------|-----------|
| DATA | 77.25 MB | 296.31 MB |
| **Utilization** | **26%** | 219 MB free |

**Growth Estimate:**
- Current: 4,167 chunks = 77 MB
- 12x growth possible before resize
- Equivalent to: ~50,000 chunks ≈ 1 GB

---

## Data Freshness

| Source | Last Update | Freshness |
|--------|-------------|-----------|
| TOMEHUB_CONTENT | 2026-02-22 (ingestion ongoing) | Real-time |
| TOMEHUB_SEARCH_LOGS | 2026-02-22 (continuous) | Real-time |
| TOMEHUB_CONCEPTS | 2026-02-XX (graph build) | ~Daily |
| TOMEHUB_SEARCH_LOGS | 2026-02-22 (continuous) | Real-time |

**Freshness Check:**
```sql
SELECT TABLE_NAME, MAX(UPDATED_AT) as last_update
FROM TOMEHUB_CONTENT
GROUP BY TABLE_NAME;
```

---

## How to Use This File

### Pattern Lookup - Question to Table Mapping

| Business Question | Table | Key Columns |
|-------------------|-------|-------------|
| "How many searches per day?" | TOMEHUB_SEARCH_LOGS | CREATED_AT, COUNT(*) |
| "What is the most common search intent?" | TOMEHUB_SEARCH_LOGS | INTENT, MODE() |
| "Show me book titles from user X" | TOMEHUB_CONTENT + TOMEHUB_BOOKS | FIREBASE_UID, TITLE |
| "Find concepts related to Dasein" | TOMEHUB_CONCEPTS + TOMEHUB_RELATIONS | NAME, graph traversal |
| "What's the avg query latency?" | TOMEHUB_SEARCH_LOGS | EXECUTION_TIME_MS, AVG() |
| "Show slow queries (>2s)" | TOMEHUB_SEARCH_LOGS | EXECUTION_TIME_MS > 2000 |
| "Which sources are most used?" | TOMEHUB_CONTENT | SOURCE_TYPE, COUNT(*) |

### Concept → Table Mapping (for /data:analyzing-data)

```yaml
analytics:
  - concept: search_queries
    table: TOMEHUB_SEARCH_LOGS
    key_column: ID
    grouping: INTENT, FIREBASE_UID, CREATED_AT

  - concept: content_chunks
    table: TOMEHUB_CONTENT
    key_column: ID
    grouping: SOURCE_TYPE, FIREBASE_UID, CREATED_AT

  - concept: concepts  
    table: TOMEHUB_CONCEPTS
    key_column: CONCEPT_ID
    description: Knowledge graph nodes

  - concept: relationships
    table: TOMEHUB_RELATIONS
    key_column: RELATION_ID
    description: Graph edges (concept connections)

  - concept: books
    table: TOMEHUB_BOOKS
    key_column: BOOK_ID
    parent_table: TOMEHUB_CONTENT (BOOK_ID foreign key)
```

---

## Recent Analyses

### 📊 Oracle 23ai Database Analysis (2026-02-22)
- **Report:** `/documentation/reports/ORACLE_23AI_DATABASE_ANALYSIS_2026-02-22.md`
- **Summary:** 4,167 chunks, 100% vectorized (768-D), 693 concepts, 506 relations

### 📈 Search Analytics DAG (2026-02-22)
- **DAG:** `/dags/tomehub_search_analytics.py`
- **Schedule:** Daily 02:00 UTC
- **Output:** Intent distribution, strategy effectiveness, performance metrics

### 📊 Database Statistics
- **Scripts:** `/apps/backend/db_stats.py`, `oracle_detailed_stats.py`

---

## Maintenance & Refresh

**To refresh this metadata:**

1. Update table row counts:
   ```sql
   SELECT TABLE_NAME, NUM_ROWS
   FROM DBA_TABLES
   WHERE OWNER = 'YOUR_USER'
   ORDER BY NUM_ROWS DESC;
   ```

2. Check for new columns:
   ```sql
   SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
   FROM USER_TAB_COLUMNS
   ORDER BY TABLE_NAME, COLUMN_ID;
   ```

3. Review index performance:
   ```sql
   SELECT INDEX_NAME, TABLE_NAME, UNIQUENESS
   FROM USER_INDEXES
   WHERE TABLE_NAME LIKE 'TOMEHUB%';
   ```

---

**Last Updated:** 2026-02-22  
**Generated By:** warehouse-init skill (v1.0)  
**Version:** 1.0
