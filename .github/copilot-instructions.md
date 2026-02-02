# TomeHub AI Coding Assistant Instructions

## Architecture Overview

**TomeHub** is a personal knowledge management system with semantic search, graph-based concept discovery, and conversational memory. It combines:
- **FastAPI backend** (`apps/backend/app.py`) with async/await patterns
- **Oracle 23ai database** with vector embeddings (768-dimensional, FLOAT32)
- **React + Vite frontend** (`apps/frontend/`) with Firebase Auth
- **Property Graph** for concept relationships and semantic bridges

### Core Data Flow
```
User Query → Query Expansion (LLM) → Multi-Strategy Search (RRF) → Dual-AI Orchestration → Answer
                                  ↓
                            Oracle DB (Vector search)
                            Property Graph (Concept bridges)
```

## Critical Architecture Patterns

### 1. **Dual-AI Orchestration (Work AI + Judge AI)**
Located: `services/dual_ai_orchestrator.py`

Pattern:
- **Work AI** (`work_ai_service.py`) generates answers from chunks
- **Judge AI** (`judge_ai_service.py`) evaluates quality using rubrics
- **Smart activation**: Fast Track (Work AI only) for high-confidence queries; Audit Track for complex questions

Example usage in routes/endpoints:
```python
result = await generate_evaluated_answer(
    question="What is Dasein?",
    chunks=[...],  # From search results
    answer_mode="SYNTHESIS",  # or "EXPLORATION"
    confidence_score=0.85,
    network_status="IN_NETWORK"
)
```

**Key files**: `dual_ai_orchestrator.py`, `work_ai_service.py`, `judge_ai_service.py`, `rubric.py`

### 2. **Search Orchestration (Multi-Strategy)**
Located: `services/search_system/orchestrator.py`

Strategies (executed in parallel):
- **ExactMatchStrategy**: Token-level matching
- **LemmaMatchStrategy**: Normalized lemma matching (Turkish support via zeyrek)
- **SemanticMatchStrategy**: Vector similarity (768-dim embeddings)

Results fused with **RRF (Reciprocal Rank Fusion)** not simple averaging.

**Key challenge**: Query expansion (~500-2000ms) is cached. Cache invalidation on model version changes (`EMBEDDING_MODEL_VERSION`, `LLM_MODEL_VERSION` in env).

### 3. **Caching Architecture (L1 + L2)**
Location: `services/cache_service.py`

- **L1**: In-memory (cachetools), configurable size/TTL
- **L2**: Redis (optional), shared across instances

Cached items:
- Intent classifications (1-hour TTL)
- Query expansions (10-minute TTL)
- Search results (user-specific, 10-minute TTL)

**Important**: Cache keys include `EMBEDDING_MODEL_VERSION`, `LLM_MODEL_VERSION`. On model upgrades, increment these to invalidate cache.

### 4. **Flow Service (Conversational Memory)**
Location: `services/flow_service.py`

Uses property graph + session tracking (`TOMEHUB_FLOW_SEEN` table) to:
- Build semantic feeds through "discovery jumps"
- Track previously seen items (avoid repetition)
- Maintain episodic memory across sessions

Session state includes: global anchor, current page, resource filters, category filters.

## Database Schema Essentials

### Main Tables
- **TOMEHUB_CONTENT**: All ingested chunks (PDF, EPUB, articles, personal notes)
  - Columns: `ID`, `FIREBASE_UID`, `CONTENT_CHUNK` (CLOB), `VEC_EMBEDDING` (768-float vector), `SOURCE_TYPE`, `TITLE`, `PAGE_NUMBER`, `BOOK_ID`
  - Constraint: `SOURCE_TYPE IN ('PDF', 'NOTES', 'EPUB', 'PDF_CHUNK', 'ARTICLE', 'WEBSITE', 'PERSONAL_NOTE')`

- **TOMEHUB_CONCEPTS**: Graph vertices (concepts extracted from content)
- **TOMEHUB_RELATIONS**: Graph edges with `WEIGHT` for importance ranking
- **TOMEHUB_FLOW_SEEN**: Session tracking (chunk_id, session_id, seen_at)
- **TOMEHUB_SEARCH_LOGS**: Analytics (query, intent, strategy weights, execution time)

### Graph Queries
Property graph `TOMEHUB_GRAPH` supports PGQL-like traversal for finding "invisible bridges" between chunks.

## Developer Workflows

### Local Development
```bash
# Backend
cd apps/backend
pip install -r requirements.txt
python app.py  # Runs on http://localhost:5000

# Frontend
cd apps/frontend
npm install
npm run dev  # Runs on http://localhost:5173
```

### Database Connection
Always use `DatabaseManager` pool:
```python
from infrastructure.db_manager import DatabaseManager

# Startup
DatabaseManager.init_pool()  # Called in app.py lifespan

# Usage (context manager recommended)
with DatabaseManager.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT ...", {"p_uid": firebase_uid})
```

**Don't** use raw `oracledb.connect()` in routes—use the pool for concurrency (max=20).

### Common Scripts in `scripts/` and root
- `apply_migration_weight.py`: Update property graph with weight property
- `apply_memory_schema.py`: Initialize flow/memory tables
- `test_all_optimizations.py`: Verify caching, pool size, performance

### Testing
- Unit tests: `apps/backend/test_features.py`
- Integration tests: `tests/integration/`
- Pre-check SQL safety: `scripts/verify_sql_safety.py`

## Critical Conventions & Gotchas

### 1. **Firebase UID Required**
Most search/chat endpoints require `firebase_uid` in request body. Used for multi-tenancy and rate limiting.

### 2. **Vector Embeddings are 768-dimensional**
- Model: Google Gemini `text-embedding-004`
- Dimension: 768 (FLOAT32)
- **Never change without updating all stored vectors** — major data migration

### 3. **Turkish Language Support**
Uses `zeyrek` library for lemmatization. Search patterns handle Turkish characters via `unidecode` normalization.

### 4. **CLOB Handling**
Large content chunks stored as CLOBs. Use helper:
```python
from infrastructure.db_manager import safe_read_clob
content = safe_read_clob(clob_object)
```

### 5. **Streaming Responses**
Some endpoints return `StreamingResponse` (e.g., stream_enrichment, answer generation). Wrap in `fastapi.responses.StreamingResponse`.

### 6. **CORS Configuration**
Allowed origins from env var `ALLOWED_ORIGINS` (comma-separated). Frontend at `http://localhost:5173` in dev, override in production via env.

## Key Files Reference

| Component | File(s) | Purpose |
|-----------|---------|---------|
| Main API | `apps/backend/app.py` | FastAPI app + lifespan, route registration |
| Config | `apps/backend/config.py` | Settings from env variables |
| Search | `services/search_service.py`, `search_system/orchestrator.py` | RAG + multi-strategy search |
| Embeddings | `services/embedding_service.py` | Gemini embedding calls |
| AI Agents | `work_ai_service.py`, `judge_ai_service.py`, `dual_ai_orchestrator.py` | Answer generation & evaluation |
| Graph | `services/graph_service.py` | Property graph traversal |
| Flow/Memory | `services/flow_service.py` | Conversational feeds |
| Models | `models/request_models.py` | Pydantic request/response schemas |
| DB | `infrastructure/db_manager.py` | Connection pooling |

## Performance Insights

- **Search latency**: 700–3500ms (LLM + DB + fusion)
- **Query expansion cached**: 10-min TTL per query string
- **Fast Track saves**: ~40–60% of Dual-AI overhead when audit skipped
- **Graph traversal**: Batched for efficiency, limits ~10 hops
- **Pool size**: 20 concurrent connections (from 10) — increase if hitting timeouts

## Environment Variables (Critical)

```bash
GEMINI_API_KEY=your_api_key              # Required, no fallback
DB_PASSWORD=password                     # Required, OCI wallet auth
DB_DSN=tomehubdb_high                    # DSN name from wallet
REDIS_URL=redis://localhost:6379/0       # Optional, L2 cache
CACHE_ENABLED=true                       # Enable/disable caching
CACHE_L1_MAXSIZE=1000                    # In-memory cache entries
CACHE_L1_TTL=600                         # Seconds
ALLOWED_ORIGINS=http://localhost:5173    # CORS whitelist
EMBEDDING_MODEL_VERSION=v2                # Increment to invalidate embedding cache
LLM_MODEL_VERSION=v1                      # Increment to invalidate LLM cache
```

## Common Tasks

**Add a new API endpoint:**
1. Define Pydantic model in `models/request_models.py`
2. Add route in `app.py` with Firebase auth middleware
3. Call appropriate service (`search_service`, `ai_service`, etc.)
4. Ensure endpoint is documented in `API_GUIDE.md`

**Modify search strategy:**
1. Edit `search_system/orchestrator.py` strategies list
2. Test with `test_features.py`
3. Update cache key if changing LLM/embedding logic

**Debug database queries:**
1. Use `scripts/verify_sql_safety.py` to validate SQL
2. Check `backend_error.log` for errors
3. Inspect with `list_db_books.py`, `check_categories.py`

**Deploy with Docker:**
```bash
docker-compose -f infra/docker-compose.yml up -d
```
Sets env from `.env` file, mounts wallet & OCI key, enables health checks.
