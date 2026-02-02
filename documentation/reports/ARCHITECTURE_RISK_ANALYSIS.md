# TomeHub Architecture Risk Analysis
**Date:** February 2, 2026  
**Scope:** FastAPI backend, Oracle database, async orchestration, AI agents  
**Assessment Level:** Production-readiness for scale (100+ concurrent users)

---

## SECTION 1: ARCHITECTURAL STRENGTHS

### 1.1 Dual-AI Orchestration Pattern
**Status: Robust**

The Work AI + Judge AI pattern (`dual_ai_orchestrator.py`) is well-structured:
- Clear separation of concerns: generation vs. evaluation
- Smart activation logic (`should_trigger_audit`) reduces overhead by 40-60% on simple queries
- Automatic retry loop with hint-based feedback enables quality improvement
- Timeout handling for Explorer mode (45s fallback to Standard)

**Why it works:**
- Verdict logic (PASS/REGENERATE/DECLINE) is deterministic
- Failure recovery is explicit (fallback to `_create_fallback_response`)
- Logging at each decision point enables debugging

---

### 1.2 Multi-Layer Caching Architecture
**Status: Robust for L1, Incomplete for L2**

L1 cache (in-memory TTLCache):
- Simple, fast, no external dependencies
- TTL-based eviction prevents stale data
- Query normalization handles whitespace/case sensitivity

L2 cache (Redis):
- Optional degradation (system works without it)
- Proper JSON serialization/deserialization
- Connection pooling pattern prevents resource exhaustion

**Evidence:** Cache service initialized in `app.py` lifespan with proper error handling

---

### 1.3 Database Pool Management
**Status: Well-implemented**

`DatabaseManager` in `infrastructure/db_manager.py`:
- Context manager pattern (`with connection as conn`) enforces cleanup
- Pool size 20 (increased from 10) supports reasonable concurrency
- Wallet-based authentication for Oracle Cloud
- Version-agnostic error handling for timeout exceptions

**Evidence:** All services use pooled connections; no raw `oracledb.connect()` calls in production routes

---

### 1.4 Search Orchestration with RRF Fusion
**Status: Sophisticated, with tuning ability**

SearchOrchestrator (`search_system/orchestrator.py`):
- Parallel strategy execution (ExactMatch, LemmaMatch, SemanticMatch)
- Query variations processed asynchronously (non-blocking expansion)
- Intent-aware weighting (`DIRECT` vs `SYNTHESIS` vs `NARRATIVE`)
- RRF (Reciprocal Rank Fusion) prevents dominance by single strategy
- Graph enrichment adds "semantic bridges" to results

**Performance insight:** 700-3500ms latency is acceptable for RAG (LLM + DB + fusion)

---

### 1.5 Semantic Query Expansion Caching
**Status: Good**

Query expansion cached for 10 minutes per query string:
- Variations stored with `EMBEDDING_MODEL_VERSION` in key
- Prevents redundant LLM calls for repeated questions
- Fallback on timeout: uses original query only

**Evidence:** `services/query_expander.py` integrates with cache service

---

## SECTION 2: ARCHITECTURAL RISKS

### 2.1 🔴 CRITICAL: Embedding API Failures Degrade Silently
**Risk Level: High**  
**Failure Mode: Wrong/Missing Answers**

Location: `services/embedding_service.py:28-102`

**Problem:**
```python
def get_embedding(text: str) -> Optional[array.array]:
    try:
        result = genai.embed_content(
            model="models/text-embedding-004",
            content=text,
            task_type="retrieval_document",
            request_options={'timeout': 20}  # 20s timeout
        )
        # ... extraction code ...
    except Exception as e:
        print(f"[ERROR] Failed to generate embedding: {e}")  # Just prints!
        return None  # Silent failure
```

**Consequences:**
1. **Semantic search completely fails** when `get_embedding()` returns None
   - Query embedding is None → vector search query breaks
   - Orchestrator silently ignores semantic results
   - User gets partial/wrong answers from only ExactMatch + LemmaMatch

2. **Ingestion silently stops creating embeddings**
   - New documents ingest without vectors
   - Graph enrichment (`get_graph_enriched_context`) doesn't populate bridges
   - Users think data is indexed, but semantic search is broken

3. **No circuit breaker or retry logic**
   - Single API error → all future queries degrade
   - No exponential backoff (unlike Work AI which uses `@retry` with tenacity)

**Real-world trigger:**
- Gemini API quota exceeded (rate limit)
- Network timeout during 20s window
- Service degradation at Google

**Evidence of prevalence:**
- Both `get_embedding()` and `get_query_embedding()` have identical fallback
- Flow service calls `get_query_embedding()` in `_resolve_anchor()` → returns None → defaults to `anchor_id` as text
- Search orchestrator tries to run SemanticMatchStrategy, which silently fails

**Impact at scale:**
- 100 concurrent users, 2 queries each = 200 embedding calls
- 1% failure rate = 2 queries with wrong answers (silent)
- Users blame TomeHub, not Gemini API

---

### 2.2 🔴 CRITICAL: Cache Key Collisions on Model Version Changes
**Risk Level: High**  
**Failure Mode: Stale/Wrong Cached Results**

Location: `services/cache_service.py:128-155`, `services/dual_ai_orchestrator.py:40-65`

**Problem:**
```python
# dual_ai_orchestrator.py
cache_key = generate_cache_key(
    service="intent",
    query=question,
    firebase_uid="",
    book_id=None,
    limit=1,
    version=settings.LLM_MODEL_VERSION  # ← Depends on env var
)
```

**Gotcha:** If developer forgets to increment `LLM_MODEL_VERSION` after changing prompt templates:
- Old cached intent classifications are reused
- New reasoning rules are bypassed
- System returns stale decisions

Example timeline:
```
Jan 20: Deploy with new rubric, forget to bump LLM_MODEL_VERSION
Jan 20: Cache hit rate 80% (good!)
Jan 21: Users complain answers are worse
Jan 21: Debug shows rubric change didn't apply
Jan 22: Manual cache flush needed
```

**Additional risk:** Query expansion cache has same issue
- If embedding model updated but `EMBEDDING_MODEL_VERSION` not bumped
- New embeddings conflict with old ones (dimensional mismatch would cause errors, but still)

**No automated enforcement:**
- No version check in `config.py` that forces update on model swap
- No migration script to clear old keys
- Documentation in instructions says "increment these" but no alarm system

---

### 2.3 🔴 CRITICAL: Firebase Authentication is Bypassed
**Risk Level: Critical**  
**Failure Mode: Multi-tenant data leakage**

Location: `middleware/auth_middleware.py`

**Current implementation:**
```python
async def verify_firebase_token(request: Request):
    authorization: str = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        # ...
        # TEMPORARY: Firebase Admin SDK not configured with service account
        # For local development, we'll pass through the token/request
        return None  # Signal to use request body UID  ← !!!
    except Exception as e:
        return None  # Development bypass  ← !!!
```

**Attack surface:**
1. **Client-side UID injection:** User sends `firebase_uid: "other_user_uid"` in request body
   - Middleware returns None
   - Route handler uses request body UID without verification
   - User accesses another user's books/notes

2. **Example exploit:**
   ```bash
   curl -X POST http://localhost:5000/api/search \
     -H "Authorization: Bearer dummy" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "search",
       "firebase_uid": "victim_user_id"  # ← Attacker guesses UID
     }'
   ```
   - If victim UID is predictable (sequential), enumeration is trivial
   - Schema has no per-user encryption on `TOMEHUB_CONTENT`

3. **Session hijacking:** Flow service creates sessions with request body UID
   - No verification that client owns that UID
   - Session tokens could be stolen/guessed

**Why it's critical:**
- Not a "TODO" comment—it's active code
- No feature flag or environment check (e.g., `if ENV != "DEVELOPMENT"`)
- Comment says "signal to use request body UID" — routes ARE using request body

**Check flow_routes.py:**
```python
# Does it verify firebase_uid from JWT?
# Or does it trust request.flow_request.firebase_uid?
```

---

### 2.4 🔴 CRITICAL: Unbounded Vector Distance Query Can Load Entire DB
**Risk Level: High**  
**Failure Mode: Database DoS, out-of-memory**

Location: `services/flow_service.py:1281-1305`

**Problem:**
```python
sql = """
    SELECT id, content_chunk, title, source_type, page_number
    FROM TOMEHUB_CONTENT
    WHERE firebase_uid = :p_uid
    AND VEC_EMBEDDING IS NOT NULL
    AND id NOT IN (
        SELECT chunk_id FROM TOMEHUB_FLOW_SEEN
        WHERE session_id = :p_sid
    )
"""
# ... apply filters ...
sql += " ORDER BY distance FETCH FIRST :p_limit ROWS ONLY "
```

**Risk:** If `distance` calculation is wrong or LIMIT is removed:
- Fetches ALL rows matching UID + filter
- With 2000+ chunks per user, this is megabytes of CLOB data
- Network transfer + memory allocation per chunk

**Compounding factors:**
1. **CLOB reading in loop:** `safe_read_clob(row[1])` per row
2. **No connection timeout per query:** Only 5s pool acquire timeout
3. **User could have 50,000+ chunks** (multiple large books)

Example failure:
```
User1 has 5000 chunks
Flow service fetches all 5000 to build a single "batch"
Each chunk is ~5KB CLOB
Total: 25MB+ transfer
Database cursor stays open, blocking other users
```

---

### 2.5 🟡 HIGH: Graph Query Batching Can Degrade on Large Graphs
**Risk Level: High**  
**Failure Mode: Slow queries, incomplete results**

Location: `services/search_service.py:60-120`

**Problem:**
```python
# Limit to avoiding too massive query if many concepts
if len(related_concept_ids) > 20: 
    related_concept_ids = related_concept_ids[:20]  # Silent truncation!
    
sql_neighbors = f"""
    SELECT c1.name as concept_A, r.rel_type, c2.name as concept_B
    FROM TOMEHUB_RELATIONS r
    ...
    FETCH FIRST 15 ROWS ONLY  # Silent truncation!
"""
```

**Issues:**
1. **Silent truncation:** Top 20 concepts → top 15 relations. Which concepts are excluded?
2. **No logging of what was dropped**
3. **User never knows semantic bridges were pruned**

Real scenario:
- Question about "ethics"
- Found 100 relevant concepts
- Only analyzed top 20
- Missed important "Kant-Hegel relationship" that was concept #25

---

### 2.6 🟡 HIGH: Parallel ThreadPoolExecutor Can Block on DB Pool Exhaustion
**Risk Level: High**  
**Failure Mode: Cascading slowdown**

Location: `services/search_system/orchestrator.py:48-120`

**Problem:**
```python
with ThreadPoolExecutor(max_workers=6) as executor:  # 6 threads
    # ExactMatch strategy
    future_map[executor.submit(strat.search, ...)] = "ExactMatch"
    # LemmaMatch strategy
    future_map[executor.submit(strat.search, ...)] = "LemmaMatch"
    # SemanticMatch on original + N variations
    # Each calls database through same pool (max=20)
```

**Cascade failure:**
1. User makes search query
2. Orchestrator spawns 6 threads (3 original strategies + 3 variations)
3. All 6 threads compete for connections from pool (max=20)
4. 4 concurrent searches = 24 threads competing for 20 connections
5. Threads block on `DatabaseManager.get_connection()`
6. Request latency balloons from 700ms to 30s+ (timeout)

**Why it's subtle:**
- Works fine with 5 concurrent users (5 * 6 = 30 threads, pool absorbs it)
- Breaks visibly at 10+ concurrent users (60 threads for 20 connections)
- No circuit breaker; all requests are treated equally

**Test case:**
```python
# Simulate with ab or locust
ab -n 100 -c 15 http://localhost:5000/api/search
# Expect: ~30s p99 latency instead of 3s
```

---

### 2.7 🟡 HIGH: Dual-AI Retry Loop Can Burn LLM Tokens on Bad Chunks
**Risk Level: High**  
**Failure Mode: Expensive, slow responses**

Location: `services/dual_ai_orchestrator.py:113-145`

**Problem:**
```python
async def _execute_audit_track():
    for attempt in range(1, max_attempts + 1):  # Default max_attempts=2
        try:
            work_result = await generate_work_ai_answer(...)
            eval_result = await evaluate_answer(...)
            
            if verdict == "REGENERATE":
                current_hints = eval_result["hints_for_retry"]
                continue  # ← Loop 2, same chunks, new generation
```

**Cost explosion:**
- Attempt 1: Generate (2000 tokens) + Evaluate (1000 tokens) = 3000
- Attempt 2: Generate (2000 tokens) + Evaluate (1000 tokens) = 3000
- Total: 6000 tokens for one question

**Failure modes:**
1. **Bad source data:** If 30 of 50 chunks are OCR garbage, no amount of hints fixes it
   - Still retries, burns tokens, returns same bad answer
2. **Rubric impossible to satisfy:** Rubric says "cite exact page" but no pages in chunks
   - Verdict always REGENERATE
   - Attempts keep incrementing
3. **No token budget:** Unlike streaming endpoints, no early exit for cost

**Real cost impact:**
- Gemini 2.0 Flash: ~$0.03 per 1M tokens
- 6000 tokens = $0.00018 per request
- 1000 requests/day × poor rubric = $0.18 wasted daily (small, but indicates poor filtering)

---

### 2.8 🟡 HIGH: No Request/Response Logging for Audit Trail
**Risk Level: High**  
**Failure Mode: Debugging impossible, compliance issues**

Location: `app.py` (logging is JSON structured but no request body logging)

**Problem:**
```python
logger = logging.getLogger("tomehub_api")
# Logs are JSON format, but no request middleware that captures:
# - Full question asked
# - firebase_uid involved
# - Response quality metrics
```

**Missing audit trail:**
1. **Compliance:** "What questions did user X ask?" → No log
2. **Debugging:** "This user says we gave wrong answer on date Y" → No trace
3. **Analytics:** "Which topics have low satisfaction?" → No logs linking question → verdict

**TOMEHUB_SEARCH_LOGS table exists** (from `create_analytics_schema.sql`):
```sql
CREATE TABLE TOMEHUB_SEARCH_LOGS (
    QUERY_TEXT CLOB,
    INTENT VARCHAR2(50),
    RRF_WEIGHTS VARCHAR2(100),
    TOP_RESULT_ID NUMBER,
    EXECUTION_TIME_MS NUMBER
)
```

**But it's never populated:**
- No code path inserts into TOMEHUB_SEARCH_LOGS
- Table is orphaned
- Search API returns results but doesn't log them

---

### 2.9 🟡 MEDIUM: Query Expander Timeout Falls Back Silently
**Risk Level: Medium**  
**Failure Mode: Degraded search quality**

Location: `services/search_system/orchestrator.py:83-92`

**Problem:**
```python
try:
    variations = expansion_future.result(timeout=10)  # 10s timeout
    logger.info(f"Variations: {variations}")
except Exception as e:
    logger.warning(f"Query expansion failed or timed out: {e}")
    variations = []  # Fallback: use original query only
```

**Issue:**
- Query expander LLM call times out after 10s
- System continues with single original query
- User gets fewer results, thinks feature "broke"
- No indicator that expansion was skipped

**Real scenario:**
- Gemini API slow (high traffic)
- Expansion times out frequently during peak hours
- Queries during peak return fewer results
- No observability (no metric for "expansion_timeout_count")

---

### 2.10 🟡 MEDIUM: Flow Service Session State Not Validated
**Risk Level: Medium**  
**Failure Mode: Stale/corrupted sessions**

Location: `services/flow_service.py:100-150`

**Problem:**
```python
def start_session(self, request: FlowStartRequest):
    anchor_vector, anchor_label, resolved_id = self._resolve_anchor(
        request.anchor_type, request.anchor_id, effective_uid, ...
    )
    
    state = self.session_manager.create_session(
        firebase_uid=effective_uid,
        anchor_id=resolved_id,
        anchor_vector=anchor_vector,  # ← No validation of dimensions
        horizon_value=request.horizon_value,
    )
```

**Issues:**
1. **No vector dimension check:** If anchor_vector is None, it's stored as None
2. **_resolve_anchor fallback:** Uses text embedding of anchor_id as query
   - If that fails, what's stored? No code path shown
3. **Session state stored in Redis** (presumably)
   - No TTL shown → sessions accumulate indefinitely?
   - Deserializaton of complex objects could fail silently

---

### 2.11 🟡 MEDIUM: No Rate Limiting on Embedding Requests
**Risk Level: Medium**  
**Failure Mode: API quota exhaustion**

Location: `app.py` has `slowapi.Limiter` but it's for HTTP endpoints

**Problem:**
- Search endpoint might be rate-limited (global)
- But embedding calls inside search are not metered
- 1 search query → 3+ embedding calls (original + variations)
- User could trigger 3× quota consumption with simple rate limit bypass

Example:
```
Limit: 100 requests/hour per IP
Search uses 3 embeddings each
User makes 100 search requests → 300 embedding API calls
```

---

## SECTION 3: NON-OBVIOUS FAILURE SCENARIOS

### 3.1 Scenario: Gemini API Degradation During Peak Load
**Trigger:** Evening hours, 50+ concurrent users  
**Cascade:**

1. Query expansion times out (10s limit hit)
2. Fallback to original query only
3. Search results are narrow/poor quality
4. Users issue follow-up questions ("clarify X")
5. Work AI + Judge AI retry on poor input
6. Token burn increases
7. Judge's verdict is still "REGENERATE" (bad input)
8. System keeps retrying
9. Latency grows (400ms → 5000ms)
10. Users hit timeout, re-request
11. More load on already-stressed Gemini API

**Result:** Positive feedback loop degrades system for 30+ minutes

---

### 3.2 Scenario: Oracle Pool Exhaustion Under Spike Load
**Trigger:** Viral content drives 100 concurrent users  
**Cascade:**

1. Search orchestrator spawns 6 threads per query
2. 100 users × 6 threads = 600 logical connections needed
3. Pool max=20; connections queue up
4. ThreadPoolExecutor workers block on `get_connection(timeout=5)`
5. After 5s, worker times out → search fails partially
6. Retry on timeout → more load
7. Database CPU spikes (waiting for available connections)
8. New ingestion pauses (can't acquire connection)
9. UI becomes unresponsive

**Root cause:** No load shedding; all requests treated equally

---

### 3.3 Scenario: Silent Embedding Failure Causes Wrong Answers
**Trigger:** Gemini API returns HTTP 429 (rate limited)  
**Flow:**

1. `get_embedding()` catches exception, prints to stdout (Docker logs)
2. Returns None
3. SemanticMatchStrategy gets None embedding
4. Tries to run vector query with NULL embedding → Oracle error OR silent skip
5. Orchestrator assumes strategy returned empty results
6. Final answer built from only ExactMatch + LemmaMatch
7. User gets wrong answer (based on keyword matching, not semantic similarity)

**Why user doesn't realize:**
- No error shown to client
- Response looks normal
- Sources shown, so it appears authoritative
- User trusts wrong answer

---

### 3.4 Scenario: Graph Enrichment Dominates Latency
**Trigger:** Question about well-connected concept (e.g., "Plato")  
**Flow:**

1. Search returns 10 chunks about Plato
2. Graph enrichment extracts concepts from all 10 chunks
3. Finds 100+ concept IDs
4. Truncates to 20 silently
5. Fetches relations (batched query)
6. Formats bridges: ~2KB text added to context
7. Work AI re-reads 2KB context over prior 50KB chunks
8. Generation becomes slightly slower

**Latency impact:** +200-500ms per search

**With 100 users/hour, this is 100 × 0.2s = 20s lost per hour**

---

### 3.5 Scenario: Cache Invalidation Miss on Prompt Update
**Trigger:** Developer changes rubric in `rubric.py`  
**Flow:**

1. Jan 28: Deploy new rubric (more strict source accuracy checking)
2. Forget to bump `LLM_MODEL_VERSION`
3. Judge AI intent classifications cached with old model version
4. First 30 queries use cached "easy" intent → new strict rubric applied to old intents = mismatch
5. Judge AI feedback misses new requirements
6. Work AI improvements don't apply

**Silent degradation:** Quality metrics show no drop (because cache hit rate is high)

---

### 3.6 Scenario: Multi-User Collision on Same Flow Session
**Trigger:** User A and User B both start Flow with same book  
**Issue:** No isolation shown in code
```python
# flow_routes.py doesn't shown here, but if flow_request.session_id
# is user-supplied, two users could start the same session
```

**Result:** Users see each other's "seen items" and both consume the same feed

---

## SECTION 4: CONCRETE IMPROVEMENT SUGGESTIONS

### Improvement 1: Add Circuit Breaker to Embedding API
**Cost:** ~2 hours  
**Risk reduction:** Critical → High

```python
# services/embedding_service.py

from circuitbreaker import circuit

EMBEDDING_FAILURES = 0
EMBEDDING_FAILURE_THRESHOLD = 5
EMBEDDING_WINDOW_MINUTES = 5

@circuit(failure_threshold=5, recovery_timeout=300)
def get_embedding(text: str) -> Optional[array.array]:
    """
    With @circuit decorator:
    - Tracks failures
    - After 5 consecutive failures, immediately raises CircuitBreakerOpen
    - Clients can catch and handle gracefully (use keyword search fallback)
    - Recovers after 5 minutes
    """
    # existing code
```

**Why this helps:**
- Fast failure (1ms error) instead of 20s timeout
- Clients can implement fallback (use ExactMatch-only)
- Prevents cascading load on already-broken API

---

### Improvement 2: Enforce Model Version Bump on Startup
**Cost:** ~1 hour  
**Risk reduction:** Critical → Medium

```python
# config.py

def validate_model_versions():
    """Verify model versions are semantically newer than last deployment."""
    last_deployed = os.getenv("LAST_DEPLOYED_LLM_VERSION", "v0")
    current = settings.LLM_MODEL_VERSION
    
    # Parse versions (simple semver check)
    last_major = int(last_deployed.split(".")[0][1:])
    curr_major = int(current.split(".")[0][1:])
    
    if curr_major <= last_major and last_deployed != current:
        raise ValueError(
            f"LLM_MODEL_VERSION must be bumped from {last_deployed} to new version. "
            f"Use: LATEST_DEPLOYED=v{curr_major+1}, EMBEDDING_MODEL_VERSION=v{curr_major+1}"
        )

# In app.py lifespan:
validate_model_versions()
```

**Why this helps:**
- Catches cache invalidation mistakes at deploy time
- No need for manual cache flush
- Enforces discipline

---

### Improvement 3: Implement Proper Firebase Auth with Fallback
**Cost:** ~4 hours  
**Risk reduction:** Critical → Low

```python
# middleware/auth_middleware.py

from firebase_admin import auth, exceptions as firebase_exceptions

async def verify_firebase_token(request: Request):
    """Verify Firebase JWT, with development mode fallback."""
    auth_header = request.headers.get("Authorization", "")
    
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid auth scheme")
        
        # Try real Firebase verification
        decoded_token = auth.verify_id_token(token)
        return decoded_token["uid"]  # ← Real UID, not user-supplied
        
    except firebase_exceptions.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except firebase_exceptions.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except ValueError:
        # Firebase not configured (local dev)
        if os.getenv("ENVIRONMENT") == "development":
            logger.warning("Firebase not configured. Using request body UID (DEV MODE ONLY)")
            return None  # Route handler can opt-in to body UID
        raise HTTPException(status_code=401, detail="Auth not configured")
```

**Why this helps:**
- Production is secure (real JWT validation)
- Development can still work (explicit dev mode)
- No silent auth bypass

---

### Improvement 4: Add Embedding Failure Observability
**Cost:** ~1.5 hours  
**Risk reduction:** High → Medium

```python
# services/embedding_service.py & monitoring.py

from prometheus_client import Counter, Histogram

embedding_failures = Counter(
    'embedding_api_failures_total',
    'Total embedding API failures',
    ['error_type']
)

embedding_latency = Histogram(
    'embedding_latency_ms',
    'Embedding API latency in milliseconds'
)

def get_embedding(text: str) -> Optional[array.array]:
    start = time.time()
    try:
        # existing code
        return embedding_array
    except TimeoutError:
        embedding_failures.labels(error_type='timeout').inc()
        logger.error(f"Embedding timeout for text[:50]={text[:50]}")
        return None
    except Exception as e:
        embedding_failures.labels(error_type=type(e).__name__).inc()
        logger.error(f"Embedding error: {e}")
        return None
    finally:
        embedding_latency.observe((time.time() - start) * 1000)
```

**Monitoring added:**
- Prometheus metrics on dashboard
- Alerts: if `embedding_api_failures_total > 5 in 5m`, page on-call
- Alerting condition: "embedding_failures > search_requests * 0.05" (expect <5% failure)

---

### Improvement 5: Bound Query Expansion and Graph Traversal
**Cost:** ~1 hour  
**Risk reduction:** High → Medium

```python
# services/search_service.py & services/search_system/orchestrator.py

MAX_GRAPH_CONCEPTS = 10  # Reduced from 20
MAX_GRAPH_RELATIONS = 5  # Reduced from 15
MAX_QUERY_VARIATIONS = 3  # Hard limit

logger.info(f"Graph enrichment: fetched {len(concepts)} concepts (truncated at {MAX_GRAPH_CONCEPTS})")
logger.info(f"Graph relations: fetched {len(relations)} relations (truncated at {MAX_GRAPH_RELATIONS})")
```

**Why this helps:**
- Prevents runaway queries
- Logging makes truncation visible
- Latency becomes predictable

---

### Improvement 6: Add Request/Response Audit Logging
**Cost:** ~2 hours  
**Risk reduction:** High → Medium

```python
# middleware/audit_middleware.py (new file)

from fastapi import Request
import json

async def audit_log_middleware(request: Request, call_next):
    """Log search/chat requests and responses for audit trail."""
    
    if request.url.path in ["/api/search", "/api/chat"]:
        body = await request.body()
        request_data = json.loads(body) if body else {}
        
        response = await call_next(request)
        
        # Log to database
        firebase_uid = request_data.get("firebase_uid", "UNKNOWN")
        question = request_data.get("question", "")[:500]
        
        # Insert into TOMEHUB_SEARCH_LOGS
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO TOMEHUB_SEARCH_LOGS 
                    (FIREBASE_UID, QUERY_TEXT, TIMESTAMP)
                    VALUES (:uid, :query, CURRENT_TIMESTAMP)
                """, {"uid": firebase_uid, "query": question})
                conn.commit()
        
        return response
```

**Why this helps:**
- Audit trail for compliance
- Debugging: trace "which questions got bad answers"
- Analytics: "what topics have low satisfaction"

---

### Improvement 7: Implement Load Shedding on Pool Exhaustion
**Cost:** ~2 hours  
**Risk reduction:** High → Medium

```python
# infrastructure/db_manager.py

class DatabaseManager:
    _pool_exhaustion_count = 0
    _load_shed_threshold = 15  # If avg wait time > 15 connections, shed
    
    @classmethod
    def get_connection(cls, timeout: int = 5):
        if cls._pool is None:
            raise RuntimeError("Pool not initialized")
        
        # Check pool pressure
        available = cls._pool._available.qsize()  # Pseudo-code
        if available < 2:  # Critical threshold
            cls._load_shed_threshold += 1
            logger.warning(f"Pool pressure high. Available: {available}")
            
            # Shed low-priority requests
            if request.get("is_analytics"):  # Analytics queries are lowest priority
                raise HTTPException(
                    status_code=503, 
                    detail="System overloaded. Try again later."
                )
        
        try:
            return cls._pool.acquire(timeout=timeout)
        except PoolTimeout:
            raise HTTPException(status_code=503, detail="Database unavailable")
```

**Why this helps:**
- Prevents cascading failure
- Analytics queries rejected, search queries still serve
- Honest error (503) instead of timeout

---

### Improvement 8: Add Retry Limit Metric to Dual-AI
**Cost:** ~30 minutes  
**Risk reduction:** High → Medium

```python
# services/dual_ai_orchestrator.py

dual_ai_retries = Counter(
    'dual_ai_retries_total',
    'Total Dual-AI retries',
    ['intent', 'reason']
)

async def generate_evaluated_answer(...):
    # In retry loop:
    if verdict == "REGENERATE":
        dual_ai_retries.labels(intent=intent, reason='regenerate').inc()
        current_hints = eval_result["hints_for_retry"]
        if attempt >= max_attempts:
            logger.warning(f"Max retries exceeded for intent={intent}. Returning attempt {attempt}")
            dual_ai_retries.labels(intent=intent, reason='max_exceeded').inc()
            break  # Exit loop instead of continuing
```

**Why this helps:**
- Tracks which intents/rubrics cause high retry rates
- Prevents token waste on impossible rubrics
- Data-driven rubric tuning

---

### Improvement 9: Validate Vector Dimensions at Insert
**Cost:** ~1 hour  
**Risk reduction:** Medium → Low

```python
# services/embedding_service.py

def validate_embedding(embedding: array.array) -> bool:
    """Ensure embedding is exactly 768 dimensions, FLOAT32."""
    if not isinstance(embedding, array.array):
        logger.error(f"Embedding is {type(embedding)}, not array.array")
        return False
    
    if embedding.typecode != 'f':  # 'f' = float32
        logger.error(f"Embedding has typecode={embedding.typecode}, expected 'f'")
        return False
    
    if len(embedding) != 768:
        logger.error(f"Embedding has {len(embedding)} dimensions, expected 768")
        return False
    
    return True

# In ingestion_service.py:
embedding = get_embedding(chunk_text)
if not validate_embedding(embedding):
    logger.error(f"Skipping chunk: invalid embedding")
    continue  # Don't insert corrupt embedding
```

**Why this helps:**
- Prevents silent data corruption
- Early detection before DB insert fails

---

### Improvement 10: Session State TTL in Flow Service
**Cost:** ~30 minutes  
**Risk reduction:** Medium → Low

```python
# services/flow_service.py

FLOW_SESSION_TTL_MINUTES = 60  # Sessions auto-expire after 1 hour

# In FlowSessionManager:
def create_session(self, ...):
    session_id = str(uuid.uuid4())
    state = FlowSessionState(...)
    
    # Store in Redis with TTL
    self.redis.setex(
        key=f"flow_session:{session_id}",
        time=FLOW_SESSION_TTL_MINUTES * 60,
        value=state.to_json()
    )
    
    return state
```

**Why this helps:**
- Prevents session accumulation
- Automatic cleanup
- Isolated sessions (each TTL is independent)

---

## SUMMARY TABLE

| Risk | Level | Impact | Effort to Fix | Priority |
|------|-------|--------|---------------|----------|
| Embedding API failures silent | Critical | Wrong answers | 2h (circuit breaker) | 1 |
| Firebase auth bypassed | Critical | Data leakage | 4h (proper JWT) | 1 |
| Model version cache miss | Critical | Stale results | 1h (validation) | 2 |
| Pool exhaustion cascade | High | Total outage | 2h (load shedding) | 2 |
| Unbounded graph queries | High | DB DoS | 1h (bounding) | 3 |
| No request audit logging | High | Compliance risk | 2h (middleware) | 3 |
| Embedding quota exhaustion | Medium | API bills | 1h (metering) | 4 |
| Query expander timeout | Medium | Poor search | 30m (observability) | 5 |
| Retry loop token burn | Medium | Costs + latency | 1h (limit) | 5 |
| Session state corruption | Medium | Stale data | 1h (TTL) | 4 |

---

## RISK QUANTIFICATION

**If these risks materialize simultaneously:**
1. Firebase breach: 1 user reads another's data (compliance violation)
2. Embedding failure: 30% of queries return wrong answers
3. Pool exhaustion: System unavailable for 20 minutes
4. No audit trail: Can't determine when/why breach occurred

**Estimated impact:** GDPR fine ($4M max) + customer churn (10-30%)

**Recommended action:** Fix Critical + High risks before production scale.
