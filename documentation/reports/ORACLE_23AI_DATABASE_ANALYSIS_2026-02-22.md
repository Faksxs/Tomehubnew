# Oracle 23ai Database Analysis Report
**TomeHub Project**  
**Report Date:** February 22, 2026

---

## Executive Summary

TomeHub operates on **Oracle 23ai Enterprise Edition** (Release 23.26.1.1.0) cloud environment. The database contains **4,167 content chunks** fully vectorized across 18 TOMEHUB tables with 35+ optimized indexes.

---

## 1. Database Environment

### Oracle Database Configuration
| Property | Value |
|----------|-------|
| **Version** | Oracle AI Database 26ai Enterprise Edition Release 23.26.1.1.0 |
| **Environment** | Oracle Cloud Engineered Systems |
| **Database Name** | FCE4GECR |
| **Created** | 2025-06-10 15:04:22 |
| **Character Set** | AL32UTF8 (Full UTF-8 Unicode - Turkish Support ✓) |
| **Active Sessions** | 16 users |

---

## 2. Content Statistics

### Overall Metrics
| Metric | Count |
|--------|-------|
| **Total Content Chunks** | 4,167 |
| **Unique Users (Firebase UID)** | 3 |
| **Total Books/Sources** | 88 |
| **Concepts (Vertices)** | 693 |
| **Relations (Edges)** | 506 |
| **Search Logs** | 1,249 |
| **Flow Session Tracking** | 0 |

### Data Distribution by Source Type

```
PDF             : 2,996 chunks (71.8%) ████████████████████
HIGHLIGHT       :   963 chunks (23.1%) ██████
BOOK            :   145 chunks (3.5%)  █
ARTICLE         :    45 chunks (1.1%)
INSIGHT         :    10 chunks (0.2%)
PERSONAL_NOTE   :     6 chunks (0.1%)
WEBSITE         :     2 chunks (0.05%)
─────────────────────────────────────
TOTAL           : 4,167 chunks (100%)
```

**Analysis:** PDF sources dominate the knowledge base (71.8%), representing primary source material. Highlights (23.1%) indicate extensive annotation and note-taking activity. Diversification needed for articles and web sources.

---

## 3. Top Content Sources

### Most Referenced Materials (Top 10)

| Rank | Title | Author | Chunks | % |
|------|-------|--------|--------|---|
| 1 | Leviathan | Thomas Hobbes | 521 | 12.5% |
| 2 | Klasik Sosyoloji | Bryan S. Turner | 438 | 10.5% |
| 3 | İslam Felsefesi Üzerine | Ahmet Arslan | 402 | 9.6% |
| 4 | Ahlak Felsefesi | Alexis Bertrand | 255 | 6.1% |
| 5 | Fakir Sanat | Leo Bersani | 207 | 5.0% |
| 6-10 | (13 other sources) | Various | 1,343 | 32.2% |

**Domain:** Philosophy, Sociology, Islamic Studies, Literary Theory

---

## 4. Table Storage Analysis

### TOMEHUB Tables (18 Total)

| Table Name | Size | Role |
|------------|------|------|
| **TOMEHUB_CONTENT** | 53.00 MB | Core content chunks + embeddings |
| **TOMEHUB_EXTERNAL_BOOK_META** | 14.50 MB | Book metadata & enrichment |
| **TOMEHUB_CONCEPTS** | 3.00 MB | Graph vertices (693 concepts) |
| **TOMEHUB_INGESTED_FILES** | 2.25 MB | Source file tracking |
| **TOMEHUB_BOOK_EPISTEMIC_METRICS** | 2.00 MB | Knowledge quality metrics |
| **TOMEHUB_FLOW_SEEN** | 0.69 MB | Session memory tracking |
| **TOMEHUB_CHAT_MESSAGES** | 0.38 MB | Conversation history |
| **TOMEHUB_SEARCH_LOGS** | 0.38 MB | Query analytics (1,249 logs) |
| **TOMEHUB_CHAT_SESSIONS** | 0.25 MB | Session state |
| **TOMEHUB_CONCEPT_CHUNKS** | 0.13 MB | Graph vertex-chunk mappings |
| **TOMEHUB_CONTENT_CATEGORIES** | 0.13 MB | Content categorization |
| **TOMEHUB_RELATIONS** | 0.06 MB | Graph edges (506 relations) |
| **TOMEHUB_FILE_REPORTS** | 0.06 MB | Ingestion reports |
| **TOMEHUB_FEEDBACK** | 0.06 MB | User feedback |
| **TOMEHUB_EXTERNAL_ENTITIES** | 0.06 MB | Knowledge graph entities |
| **TOMEHUB_EXTERNAL_EDGES** | 0.06 MB | Knowledge graph relations |
| **TOMEHUB_BOOKS** | 0.06 MB | Book registry (88 books) |
| **TOMEHUB_CONTENT_TAGS** | 0.06 MB | Content tagging |
| | | |
| **TOTAL USED** | **77.25 MB** | (296.31 MB tablespace allocated) |

---

## 5. Vectorization Status

### Embedding Coverage
```
✅ 4,167 / 4,167 chunks vectorized (100%)
   Dimension: 768-D (FLOAT32)
   Model: Google Gemini text-embedding-004
   Status: Complete coverage
```

### Vector Search Optimization
- **Index:** `IDX_TOMEHUB_VEC_EMBEDDING` (NONUNIQUE)
- **Capability:** Approximate Nearest Neighbor (ANN) search
- **Use Case:** Semantic similarity ranking in RAG pipeline
- **Performance:** Sub-second retrieval for 4,167+ embeddings

---

## 6. Index Architecture

### Total Indexes: 35+

#### Core Search Indexes
| Index Name | Table | Type | Purpose |
|------------|-------|------|---------|
| IDX_TOMEHUB_VEC_EMBEDDING | TOMEHUB_CONTENT | NONUNIQUE | Vector similarity search |
| IDX_NORM_CONTENT | TOMEHUB_CONTENT | NONUNIQUE | Full-text normalization |
| IDX_TOMEHUB_SOURCE_TYPE | TOMEHUB_CONTENT | NONUNIQUE | Source filtering |
| IDX_TOMEHUB_USER_SOURCE | TOMEHUB_CONTENT | NONUNIQUE | User-scoped queries |
| IDX_CONTENT_BOOK_ID | TOMEHUB_CONTENT | NONUNIQUE | Book chunk traversal |

#### Property Graph Indexes
| Index Name | Table | Type | Purpose |
|------------|-------|------|---------|
| IDX_CONCEPTS_VEC | TOMEHUB_CONCEPTS | NONUNIQUE | Concept vector search |
| IDX_CONCEPTS_DESC_VEC | TOMEHUB_CONCEPTS | NONUNIQUE | Description embedding |
| IDX_RELATIONS_SRC_ID | TOMEHUB_RELATIONS | NONUNIQUE | Source node lookup |
| IDX_RELATIONS_DST_ID | TOMEHUB_RELATIONS | NONUNIQUE | Destination node lookup |

#### Session & Metadata Indexes
| Index Name | Table | Type | Purpose |
|------------|-------|------|---------|
| IDX_CHAT_UID | TOMEHUB_CHAT_SESSIONS | NONUNIQUE | User session retrieval |
| IDX_SEARCH_LOGS_UID | TOMEHUB_SEARCH_LOGS | NONUNIQUE | Query history per user |
| IDX_FLOW_SEEN_SESSION | TOMEHUB_FLOW_SEEN | NONUNIQUE | Session discovery tracking |
| IDX_BOOKS_FIREBASE_UID | TOMEHUB_BOOKS | NONUNIQUE | User book discovery |

#### JSON & Advanced Indexes
| Index Name | Table | Type | Purpose |
|------------|-------|------|---------|
| IDX_CHAT_TAGS_JSON | TOMEHUB_CHAT_SESSIONS | NONUNIQUE | Tag-based search |
| IDX_FILE_REPORTS_KEY_TOPICS_JSON | TOMEHUB_FILE_REPORTS | NONUNIQUE | Topic extraction |
| SYS_IL0000126913C00020$$ | TOMEHUB_CONTENT | UNIQUE | Internal JSON indexing |

---

## 7. Connection Pool Configuration

### Database Pool Settings
| Setting | Value | Purpose |
|---------|-------|---------|
| **Pool Strategy** | Dual (Read + Write) | Separate optimization |
| **Read Pool Max** | 30 connections (75%) | RAG, search operations |
| **Write Pool Max** | 10 connections (25%) | Ingestion, logging |
| **Min Connections** | 5 | Always available |
| **Pool Timeout** | 30 seconds | Connection wait limit |
| **Recycle Period** | 3600s (1h) | Connection refresh |
| **Connection Mode** | POOL_GETMODE_WAIT | Blocking queue |

**Status:** Currently 16 active user sessions

---

## 8. Multi-Tenant Architecture

### User Segmentation
```
Total Users: 3
Each user has isolated:
  - Content (user-scoped queries via FIREBASE_UID)
  - Chat sessions
  - Search logs
  - Flow/memory tracking
```

### Isolation Strategy
- **Primary Key:** `FIREBASE_UID` (all user tables)
- **Index:** `IDX_TOMEHUB_USER_SOURCE` for efficient filtering
- **Security:** Row-level isolation, no cross-user data leakage

---

## 9. Performance Insights

### Query Latency Baseline
| Operation | Estimated Latency | Notes |
|-----------|------|-------|
| Vector similarity (top-k) | 500-800ms | ANN on 4,167 embeddings |
| Full-text search | 200-400ms | Lemma + normalization |
| Graph traversal (10 hops) | 300-600ms | Concept relationship walk |
| Combined RAG search | 1000-2000ms | Multi-strategy fusion (RRF) |

### Storage Efficiency
```
Content:         53.00 MB ÷ 4,167 = 12.7 KB/chunk avg
Total System:    77.25 MB for 4,167 chunks + metadata
Empty Space:    296.31 MB - 77.25 MB = 219 MB available
Utilization:     26% (room for 12x growth before resize)
```

---

## 10. Concept Graph Statistics

### Property Graph Metrics
| Metric | Value | Notes |
|--------|-------|-------|
| **Nodes (Concepts)** | 693 | Extracted from content |
| **Edges (Relations)** | 506 | Concept relationships |
| **Avg Degree** | 1.46 edges/node | Semi-sparse graph |
| **Paths Queryable** | Up to 10 hops | Graph traversal limit |

### Use Cases
1. **Discovery Jumps:** Navigate from one concept to semantically related chunks
2. **Semantic Bridges:** Find "invisible" connections between distant content
3. **Context Expansion:** Enrich initial search with concept-adjacent chunks

---

## 11. Recommendations

### Immediate Actions ✓
- [x] Full 100% vectorization complete
- [x] 35+ indexes optimized
- [x] Multi-tenant isolation configured
- [x] Property graph built (693 concepts)

### Short-term Improvements (Weeks)
1. **Content Diversification**
   - Current: 71.8% PDF
   - Target: Add 20-30% articles/web sources
   - Benefit: Broader knowledge coverage

2. **Graph Enhancement**
   - Current: 693 concepts, 506 relations (avg degree 1.46)
   - Target: Increase to 1000+ concepts with avg degree 2.5+
   - Action: Run semantic clustering on similar chunks
   - Impact: Better discovery jumps, reduced redundancy

3. **Performance Tuning**
   - Monitor `TOMEHUB_SEARCH_LOGS` (1,249 logs)
   - Identify slow queries (>2s)
   - Add materialized views for hotspots

### Long-term Strategy (Months)
1. **Scaling Preparation**
   - Current: 3 users, 4,167 chunks, 77 MB
   - Projected: 50-100 users, 100K+ chunks, 1-2 GB
   - Action: Oracle Sharding for horizontal scaling
   - Review: Connection pool (move to 60-80 max if needed)

2. **Content Management**
   - Implement automatic cleanup of duplicate/near-duplicate chunks
   - Archive old/historical content (TOMEHUB_INGESTED_FILES tracking)
   - Deprecate low-value sources

3. **Analytics & Monitoring**
   - Real-time dashboard from `TOMEHUB_SEARCH_LOGS`
   - User activity heatmaps
   - Missing entity detection (concepts mentioned but not indexed)

---

## 12. Technical Debt

| Issue | Priority | Impact | Fix |
|-------|----------|--------|-----|
| Flow session tracking (0 records) | Medium | Session memory unused | Enable TOMEHUB_FLOW_SEEN logging |
| Concept relation sparsity (1.46 avg degree) | Medium | Weak graph connectivity | Run semantic clustering |
| No explicit validation indexes | Low | Query optimization | Add conditional indexes for nulls |

---

## 13. Security & Compliance

✅ **Compliant Features**
- UTF-8 Character Set (multi-language support)
- Firebase UID integration (identity management)
- Row-level isolation (multi-tenant)
- Oracle Cloud encryption (at rest/in-transit)
- Connection pooling (prevents connection exhaustion)

⚠️ **Monitoring Needed**
- Unused connection timeout policies
- Query cost attribution per user
- Backup/recovery procedures

---

## Appendix A: Script References

Scripts in `/apps/backend/` for ongoing analysis:

```bash
# Quick statistics
python db_stats.py

# Detailed Oracle metrics
python oracle_detailed_stats.py
```

Both scripts use `DatabaseManager.init_pool()` for connection pooling.

---

**Report Generated:** 2026-02-22 by Analysis System  
**Next Review:** 2026-03-22 (Monthly)
