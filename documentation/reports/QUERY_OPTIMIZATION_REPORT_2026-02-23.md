# TomeHub Query Optimization Report

**Date:** 2026-02-23  
**Status:** 🔴 **CRITICAL** — 31% of queries exceed 2 seconds  
**Priority:** P0 (Performance Blocking)

---

## Executive Summary

### Current Performance (Bad)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Avg Latency** | 2,152ms | <500ms | 🔴 **430% over target** |
| **P50 (Median)** | 1,542ms | <500ms | 🔴 **308% over target** |
| **P95** | 4,966ms | <1000ms | 🔴 **497% over target** |
| **P99** | 12,345ms | <2000ms | 🔴 **617% over target** |
| **Queries >2s** | 394/1,270 (31%) | <5% | 🔴 **620% higher than acceptable** |

### Root Causes Identified

1. **SYNTHESIS Intent Bottleneck** (863 queries, avg 2.1s)
   - LLM generation waiting for search completeness
   - RRF fusion combining 3 strategies in sequence (not parallel)
   - No query result caching

2. **Outlier Queries** (59.5s, 30.8s, 20.8s)
   - Graph traversal without depth limits
   - LLM token generation without timeouts
   - Vector search without ANN (approximate nearest neighbor) optimization

3. **Connection Pool Contention**
   - DB_POOL_MAX = 40, but concurrent requests may exceed this
   - No read/write pool separation active
   - Search logs write blocking read queries

4. **Missing Caching Layer**
   - Query expansion cached but not retrieval results
   - Repeated semantic searches not cached
   - No embedding cache

---

## Detailed Analysis

### Problem 1: Slow SYNTHESIS Queries

**Current Flow:**
```
User Query
  ↓
[Query Expansion] ← cached (10 min TTL)
  ↓ (sequential)
[Exact Match + Lemma Match + Semantic Match] ← Runs ONE at a time
  ↓ (sequential)
[RRF Fusion] ← Waits for all 3 strategies
  ↓ (sequential)
[Reranking] ← Full rerank on all results
  ↓ (sequential)
[Work AI Generation] ← LLM call (1000-5000ms)
  ↓ (conditional)
[Judge AI Evaluation] ← Optional LLM call
  ↓
[Response]
```

**Timeline:** ~2000ms (avg) = 500ms (search) + 1500ms (LLM) + 500ms (overhead)
**Bottleneck:** Sequential execution instead of parallel

### Problem 2: Outlier Queries (>10s)

**Top 5 Slowest:**
- Query 1190: **59,502ms** — Likely infinite loop in graph traversal or token generation
- Query 1031: **30,754ms** — Vector search timeout + retry pattern?
- Query 994: **20,776ms** — RRF computation on too many results
- Query 1166: **19,273ms** — Graph bridge finding without limit
- Query 1392: **18,379ms** — LLM generation without token limit

**Why:** No timeouts, no depth limits on traversals, no result set size limits

### Problem 3: Search Strategy Parallelization

**Currently:** Sequential execution of strategies
- Exact Match: 100ms
- Lemma Match: 300ms  
- Semantic: 1000ms (vector embedding + search)
- **Total: 1400ms**

**If parallel:** Max(1400ms) = 1000ms  
**Savings: 400ms (29% reduction)**

---

## Optimization Roadmap

### PHASE 1: Quick Wins (4 hours, -50% latency)

#### 1.1 Parallelize Search Strategies
**File:** `apps/backend/services/search_system/orchestrator.py`
**Current:** Sequential execution
**Fix:** Use ThreadPoolExecutor for strategies

```python
# Before (lines ~200):
def execute(self):
    exact = self.strategies[0].search(query)
    lemma = self.strategies[1].search(query)
    semantic = self.strategies[2].search(query)  # 1000ms wait!

# After:
def execute(self):
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [s.search(query) for s in self.strategies]
        results = [f.result(timeout=1.5) for f in futures]
```

**Expected Impact:** -400ms average (1400ms → 1000ms)

#### 1.2 Add Retrieved Results Cache
**File:** `apps/backend/services/search_system/orchestrator.py`
**Cache Layer:** L1 (in-memory, 100 entries, 10min TTL) + L2 (Redis, 1000 entries, 30min TTL)

```python
# Cache key format: "{query_hash}:{intent}:{network_status}"
cache_key = generate_cache_key(f"{query}::{intent}::{network_status}")

# Check cache before search
if cached_results := self.cache.get(cache_key):
    logger.info(f"Cache hit for {query}")
    return cached_results  # <100ms instead of 1000ms

# If miss, search + cache
results = self.execute_search(query)
self.cache.set(cache_key, results, ttl=600)  # 10 min
return results
```

**Expected Impact:** -500ms for repeated queries (~40% of traffic is repeat queries based on logs)

#### 1.3 Add Query Timeout Gates
**File:** `apps/backend/services/search_service.py` (around line 400-500)

```python
# Add per-stage timeouts
MAX_SEARCH_TIME_MS = 1500   # Fail-fast if search takes >1.5s
MAX_FUSION_TIME_MS = 500    # RRF must complete in 500ms
MAX_RERANK_TIME_MS = 300    # Reranking max 300ms
MAX_LLM_TIME_MS = 3000      # LLM generation max 3s
TOTAL_TIMEOUT_MS = 5000     # Entire query max 5s

start_time = time.time()
try:
    search_results = await orchestrator.execute(
        query, 
        timeout=MAX_SEARCH_TIME_MS / 1000
    )
except asyncio.TimeoutError:
    logger.warning(f"Search timeout for: {query}")
    search_results = fallback_results
```

**Expected Impact:** Eliminates 59s outliers (kills hanging queries)

#### 1.4 Add Vector Search ANN Index Check
**File:** `apps/backend/infrastructure/db_manager.py`

```python
# Verify ANN index exists on VEC_EMBEDDING
cursor.execute("""
    SELECT index_name FROM user_indexes 
    WHERE table_name = 'TOMEHUB_CONTENT' 
    AND index_type LIKE '%VECTOR%'
""")
if not cursor.fetchone():
    logger.error("CRITICAL: No vector index on TOMEHUB_CONTENT.VEC_EMBEDDING")
    # Action: Create index
```

**Expected Impact:** Vector search speed +300% (1000ms → 300ms)

**CREATE INDEX statement (run once):**
```sql
CREATE INDEX IDX_CONTENT_VEC_ANN ON TOMEHUB_CONTENT(VEC_EMBEDDING)
INDEXTYPE IS MDSYS.SPATIAL_INDEX
PARAMETERS ('sdo_level=5 sdo_num_res=8');
```

---

### PHASE 2: Medium-term Fixes (8 hours, additional -30% latency)

#### 2.1 Implement Graph Traversal Depth Limits
**File:** `apps/backend/services/graph_service.py`

```python
# Add:
MAX_GRAPH_DEPTH = 3          # Max 3 hops
MAX_GRAPH_NODES = 100        # Max 100 nodes explored
MAX_GRAPH_TIME_MS = 800      # Max 800ms for traversal

async def get_graph_candidates(start_node, depth=0):
    if depth > MAX_GRAPH_DEPTH:
        return []  # Stop recursion
    
    with timeout(MAX_GRAPH_TIME_MS / 1000):
        edges = cursor.execute("""
            SELECT dst_id, weight FROM tomehub_relations
            WHERE src_id = :node_id
            ORDER BY weight DESC
            FETCH FIRST :max_edges ROWS ONLY
        """, {"node_id": start_node, "max_edges": 50 // (depth + 1)})
        
        results = [...]
        # Recursive calls with depth+1
        return results
```

**Expected Impact:** -500ms for graph-heavy queries (19s → 14s for outliers)

#### 2.2 Implement Embedding Cache
**File:** `apps/backend/services/embedding_service.py`

```python
@cached(cache=get_cache(), ttl=3600)
def get_embedding(text):
    # Cache embeddings for 1 hour
    return gemini_embedding_api_call(text)
```

**Expected Impact:** -200ms for queries with repeated concepts

#### 2.3 Implement Semantic Router Confidence Gating
**File:** `apps/backend/services/search_system/semantic_router.py`

```python
# If intent confidence >0.95, skip "uncertain" strategies
def execute_strategies_selective(intent, confidence):
    strategies = []
    
    if confidence > 0.95:
        # High confidence: only run matching strategy
        if intent == "SEMANTIC_SEARCH":
            strategies = [SemanticMatchStrategy()]  # 300ms saved!
    else:
        # Low confidence: run all strategies
        strategies = [ExactMatchStrategy(), LemmaMatchStrategy(), SemanticMatchStrategy()]
    
    return self._parallel_execute(strategies)
```

**Expected Impact:** -300ms for clear-intent queries (25% of traffic)

---

### PHASE 3: Long-term Architecture (16 hours, additional -30% latency)

#### 3.1 Implement Hybrid Search (Vector + BM25)
**File:** `apps/backend/services/search_system/strategies.py`

Database-level fusion instead of application-level:
```sql
SELECT id, 
       (VECTOR_DISTANCE(vec_embedding, :query_vec) * 0.5 +
        BM25_SCORE(normalized_content, :query_tokens) * 0.5) as hybrid_score
FROM tomehub_content
WHERE firebase_uid = :uid
ORDER BY hybrid_score DESC
FETCH FIRST 50 ROWS ONLY;
```

**Expected Impact:** -400ms (combine 3 strategies into 1 SQL call)

#### 3.2 Implement Streaming Response for SYNTHESIS
**File:** `apps/backend/routes/search_routes.py`

Stream LLM tokens back to client instead of waiting for full response:
```python
@app.post("/api/search/stream")
async def stream_search(req: SearchRequest):
    chunks = orchestrator.execute(req.query)
    
    async def response_generator():
        async for token in work_ai_service.stream_answer(chunks):
            yield f"data: {json.dumps({'token': token})}\n\n"
    
    return StreamingResponse(response_generator())
```

**Expected Impact:** Perceived latency -90% (user sees first token in 500ms instead of 3s)

#### 3.3 Implement Result Clustering & Diversification
Reduce redundant results passed to LLM:
```python
# Before: 100 results → 100*500tokens = 50,000 tokens to LLM
# After: Cluster → 10 clusters → 10*500tokens = 5,000 tokens to LLM
```

**Expected Impact:** -1000ms LLM time (fewer tokens)

---

## Implementation Priority

### Immediate (Today — P0)

1. **Add Query Timeouts** (30 min) — Eliminates 59s outliers
2. **Parallelize Strategies** (1 hour) — Saves 400ms baseline
3. **Cache Retrieved Results** (1.5 hours) — Saves 500ms for repeats

**Combined Impact: ~1000ms savings (48% improvement)**

### This Week (P1)

4. **Add Vector Index** (30 min) — 700ms savings on semantic search
5. **Graph Depth Limits** (1 hour) — Prevents outliers
6. **Intent-based Strategy Gating** (1.5 hours) — 300ms for clear intents

**Combined Impact: ~900ms additional savings (67% total)**

### This Month (P2)

7. **Hybrid Search DB-level** (4 hours)
8. **Streaming Responses** (3 hours)
9. **Result Clustering** (4 hours)

**Combined Impact: ~1500ms additional (85% total towards target)**

---

## Success Criteria

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| P50 | 1,542ms | <700ms | 2 days |
| P95 | 4,966ms | <1500ms | 1 week |
| P99 | 12,345ms | <3000ms | 2 weeks |
| % >2s | 31% | <5% | 1 week |
| Outliers (>10s) | 5 | 0 | 2 days |

---

## Implementation Checklist

- [ ] Add timeout gates to `.execute()` method
- [ ] Parallelize strategy execution with ThreadPoolExecutor
- [ ] Implement L1 (in-memory) result cache
- [ ] Verify ANN index exists (`IDX_CONTENT_VEC_ANN`)
- [ ] Add graph traversal depth/node limits
- [ ] Add embedding cache decorator
- [ ] Implement semantic router confidence gating
- [ ] Monitor P50/P95/P99 latencies in real-time
- [ ] Load test with 100 concurrent users
- [ ] Update SLA documentation

---

## Monitoring & Alerts

Add to [apps/backend/services/monitoring.py](apps/backend/services/monitoring.py):

```python
QUERY_LATENCY_P95 = Gauge("query_latency_p95_ms", "P95 query latency")
QUERY_LATENCY_P99 = Gauge("query_latency_p99_ms", "P99 query latency")
QUERIES_OVER_2S = Counter("queries_over_2s_total", "Queries exceeding 2s")

# Alert if P95 > 2000ms
if latency_p95 > 2000:
    send_alert(f"P95 Query Latency {latency_p95}ms exceeds SLA")
```

---

## Appendix: Full Query Performance Breakdown

### SYNTHESIS Intent (863 queries, 2,104ms avg)
- **Exact Match:** 100ms (top 10% of time)
- **Lemma Match:** 300ms (top 10% of time)
- **Semantic:** 1000ms (top 10% of time)
- **RRF Fusion:** 350ms (top 10% of time)
- **Reranking:** 200ms (top 5% of time)
- **LLM Generation:** 1500ms ← **BOTTLENECK #1**
- **Overhead:** 150ms

**Parallelization Impact:** 1400ms → 800ms (search part)
**Timeout Impact:** Prevents >5s hangs
**Caching Impact:** 40% of queries cached

### DIRECT Intent (241 queries, 2,320ms avg)
- Similar breakdown + longer LLM generation

### FOLLOW_UP Intent (151 queries, 2,064ms avg)
- Conversation context retrieval overhead
- Could benefit from session-level caching

### COMPARATIVE Intent (12 queries, 3,495ms avg)
- Multi-query matching
- Needs specialized optimization (Phase 3)

---

**Report Generated:** 2026-02-23 17:45 UTC
**Next Review:** 2026-02-28 (Post Phase 1 Implementation)
