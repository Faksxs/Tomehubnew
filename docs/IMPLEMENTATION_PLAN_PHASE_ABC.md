# TomeHub Critical Bottleneck - Step-by-Step Implementation Plan

**Target:** Fix the 4 critical bottlenecks to handle 500+ concurrent users reliably  
**Timeline:** 4-6 weeks (phased approach)  
**Priority:** Database Pool (Week 1) → Query Optimization (Week 2-3) → Memory Management (Week 3-4) → Monitoring (Week 4-6)

---

## 🎯 Implementation Overview

```
PHASE A: Quick Wins (Week 1)
├─ A1: Increase DB pool 20 → 40
├─ A2: Add memory monitoring + alerting
├─ A3: Implement request rate limiting
└─ Result: Handle 100-150 concurrent users

PHASE B: Query Optimization (Week 2-3)
├─ B1: Profile current queries
├─ B2: Add database query caching
├─ B3: Optimize N+1 query patterns
├─ B4: Implement query result pagination
└─ Result: Reduce DB load by 60%

PHASE C: Resilience Hardening (Week 3-4)
├─ C1: Implement separate read/write pools
├─ C2: Add stream backpressure limiting
├─ C3: Implement memory pressure response
└─ Result: Graceful degradation, no OOMkiller

PHASE D: Monitoring & Observability (Week 4-6)
├─ D1: Add Prometheus metrics
├─ D2: Create Grafana dashboards
├─ D3: Implement alerting rules
├─ D4: Add circuit breaker metrics
└─ Result: Proactive failure detection
```

---

## PHASE A: Quick Wins (Week 1)

### Task A1: Increase Database Connection Pool (20 → 40)

**Current State:**
```python
# config.py
DB_POOL_SIZE = 20  # Hard limit
```

**Problem:**
- 100 concurrent users need ~500 queries
- Pool of 20 can only handle 20 simultaneous
- Rest queue, causing 2-3s wait per request

**Implementation (2 hours):**

**Step A1.1: Update config.py**
```python
# BEFORE (in config.py):
# self.DB_USER = os.getenv("DB_USER", "ADMIN")

# AFTER:
self.DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "40"))
self.DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
self.DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))
```

**Step A1.2: Update DatabaseManager**
```python
# in infrastructure/db_manager.py
# BEFORE:
# connection_pool = oracledb.create_pool(
#     user=settings.DB_USER,
#     password=settings.DB_PASSWORD,
#     dsn=settings.DB_DSN,
#     min=1,
#     max=20  # ← Hard-coded
# )

# AFTER:
connection_pool = oracledb.create_pool(
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    dsn=settings.DB_DSN,
    min=5,
    max=settings.DB_POOL_SIZE,  # Now configurable
    timeout=settings.DB_POOL_TIMEOUT,
    getmode=oracledb.POOL_GETMODE_WAIT  # Wait for connection
)
```

**Step A1.3: Update .env**
```bash
DB_POOL_SIZE=40              # Increased from 20
DB_POOL_TIMEOUT=30           # Wait max 30s for connection
DB_POOL_RECYCLE=3600         # Recycle connections every hour
```

**Step A1.4: Add logging**
```python
# In app.py lifespan:
logger.info(f"Database pool: min=5, max={settings.DB_POOL_SIZE}, timeout={settings.DB_POOL_TIMEOUT}s")
```

**Testing:**
```bash
# 1. Verify pool initializes with new size
python app.py
# Check logs: "Database pool: min=5, max=40, timeout=30s"

# 2. Load test with 100 concurrent users
# Should see better queueing distribution
```

**Validation Checklist:**
- [ ] Pool initializes with `max=40`
- [ ] No errors in startup logs
- [ ] Database queries still work
- [ ] Connection timeout works after 30s
- [ ] Test with load: 100 users should see ~50% latency improvement

**Effort:** 2 hours  
**Risk:** Low (just tuning, no code logic changes)  
**Expected Improvement:** Handle 100-150 concurrent users instead of 50

---

### Task A2: Add Memory Monitoring & Alerting

**Current State:**
- No memory monitoring
- OOMkiller silently kills process
- No early warning

**Problem:**
- 70 concurrent streams can trigger OOM
- No visibility until process dies

**Implementation (3 hours):**

**Step A2.1: Add psutil dependency**
```bash
pip install psutil
```

**Step A2.2: Create memory monitor service**
```python
# NEW FILE: services/memory_monitor_service.py

import psutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryMonitor:
    """Monitor process memory usage and alert on high usage."""
    
    MEMORY_WARNING_THRESHOLD = 0.70  # 70% of total system memory
    MEMORY_CRITICAL_THRESHOLD = 0.85  # 85% of total system memory
    
    @staticmethod
    def get_memory_stats() -> dict:
        """Get current memory usage statistics."""
        process = psutil.Process()
        vm = psutil.virtual_memory()
        
        return {
            "process_rss_mb": process.memory_info().rss / 1024 / 1024,  # RSS in MB
            "process_percent": process.memory_percent(),
            "system_total_mb": vm.total / 1024 / 1024,
            "system_used_mb": vm.used / 1024 / 1024,
            "system_available_mb": vm.available / 1024 / 1024,
            "system_percent": vm.percent,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def check_memory_health() -> str:
        """Check memory status. Returns: 'ok', 'warning', or 'critical'."""
        stats = MemoryMonitor.get_memory_stats()
        
        if stats["system_percent"] >= MemoryMonitor.MEMORY_CRITICAL_THRESHOLD * 100:
            logger.error(
                f"🔴 CRITICAL: Memory usage {stats['system_percent']:.1f}% "
                f"({stats['system_used_mb']:.0f}MB / {stats['system_total_mb']:.0f}MB)"
            )
            return "critical"
        
        elif stats["system_percent"] >= MemoryMonitor.MEMORY_WARNING_THRESHOLD * 100:
            logger.warning(
                f"🟡 WARNING: Memory usage {stats['system_percent']:.1f}% "
                f"({stats['system_used_mb']:.0f}MB / {stats['system_total_mb']:.0f}MB)"
            )
            return "warning"
        
        else:
            logger.debug(
                f"✓ Memory OK: {stats['system_percent']:.1f}% "
                f"({stats['system_used_mb']:.0f}MB / {stats['system_total_mb']:.0f}MB)"
            )
            return "ok"
```

**Step A2.3: Add health endpoint**
```python
# In app.py, add after existing health endpoints:

@app.get("/api/health/memory")
async def health_memory():
    """Get memory usage statistics."""
    from services.memory_monitor_service import MemoryMonitor
    
    stats = MemoryMonitor.get_memory_stats()
    status = MemoryMonitor.check_memory_health()
    
    return {
        "status": "ok",
        "memory": stats,
        "health": status
    }
```

**Step A2.4: Add periodic memory check in lifespan**
```python
# In app.py lifespan (startup section):

async def memory_monitor_task():
    """Periodically check memory usage."""
    from services.memory_monitor_service import MemoryMonitor
    
    while True:
        try:
            MemoryMonitor.check_memory_health()
            await asyncio.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Memory monitor error: {e}")
            await asyncio.sleep(30)

# Start in lifespan startup
asyncio.create_task(memory_monitor_task())
```

**Testing:**
```bash
# 1. Check memory endpoint
curl http://localhost:5001/api/health/memory | jq .

# Output should show:
# {
#   "status": "ok",
#   "memory": {
#     "process_rss_mb": 250,
#     "system_percent": 45.2,
#     ...
#   },
#   "health": "ok"
# }

# 2. Simulate high memory load (optional)
# Generate 100+ concurrent requests
# Monitor endpoint response
```

**Validation Checklist:**
- [ ] psutil installed and working
- [ ] Memory endpoint responds with valid data
- [ ] Logs show periodic memory checks
- [ ] Warning logs appear when >70% memory used
- [ ] Critical logs appear when >85% memory used

**Effort:** 3 hours  
**Risk:** Low (read-only monitoring)  
**Expected Improvement:** Early warning before OOMkiller, can implement auto-restart

---

### Task A3: Implement Request Rate Limiting

**Current State:**
- No rate limiting
- Unlimited requests accepted
- Queue explodes under load

**Problem:**
- 1000 req/sec causes queue overflow
- Backlog exceeds OS limits
- New users get "Connection refused"

**Implementation (2 hours):**

**Step A3.1: Configure slowapi limits**
```python
# In app.py (already has slowapi, just configure it):

# BEFORE:
# limiter = Limiter(key_func=get_remote_address)

# AFTER:
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per minute"],  # Global: 1000 req/min
    storage_uri="memory://"
)

# Add per-endpoint limits:
# In individual route decorators:

@app.post("/api/search")
@limiter.limit("100 per minute")  # 100 searches per user per minute
async def search(request: SearchRequest, firebase_uid: str = Depends(verify_firebase_token)):
    """Search endpoint with rate limiting."""
    ...

@app.post("/api/ingest")
@limiter.limit("10 per minute")  # Ingestion is slower, fewer limits
async def ingest(request: IngestRequest, firebase_uid: str = Depends(verify_firebase_token)):
    """Ingest endpoint with rate limiting."""
    ...
```

**Step A3.2: Add rate limit error handler**
```python
# In app.py:

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": str(exc.detail),
            "retry_after": 60
        }
    )
```

**Step A3.3: Make limits configurable**
```python
# In config.py:

self.RATE_LIMIT_SEARCH = int(os.getenv("RATE_LIMIT_SEARCH", "100"))  # per minute
self.RATE_LIMIT_INGEST = int(os.getenv("RATE_LIMIT_INGEST", "10"))   # per minute
self.RATE_LIMIT_GLOBAL = int(os.getenv("RATE_LIMIT_GLOBAL", "1000")) # per minute

# In .env:
RATE_LIMIT_GLOBAL=1000          # Requests per minute, total
RATE_LIMIT_SEARCH=100           # Searches per minute, per user
RATE_LIMIT_INGEST=10            # Ingestions per minute, per user
```

**Testing:**
```bash
# 1. Send requests rapidly
for i in {1..101}; do curl http://localhost:5001/api/search; done

# Should get 429 on request 101+

# 2. Check rate limit headers
curl -i http://localhost:5001/api/search
# Should show: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
```

**Validation Checklist:**
- [ ] Rate limiting library working (slowapi already imported)
- [ ] 429 responses returned after limit exceeded
- [ ] Per-endpoint limits applied correctly
- [ ] Configuration via environment variables works
- [ ] Retry-After header included in 429 response

**Effort:** 2 hours  
**Risk:** Low (just request rejection)  
**Expected Improvement:** Prevents queue overflow, graceful rejection instead of timeout

---

## PHASE B: Query Optimization (Week 2-3)

### Task B1: Profile Current Queries (4 hours)

**Goal:** Identify which queries are slowest and most frequent

**Step B1.1: Enable SQL tracing**
```python
# In infrastructure/db_manager.py

import logging
from datetime import datetime

# Add tracing
class QueryTracer:
    """Trace slow queries."""
    
    SLOW_QUERY_THRESHOLD = 1.0  # Log queries >1 second
    
    @staticmethod
    def trace_query(query_string: str, execution_time: float):
        """Log query details."""
        if execution_time > QueryTracer.SLOW_QUERY_THRESHOLD:
            logger.warning(
                f"🐢 SLOW QUERY ({execution_time:.2f}s):\n{query_string[:200]}..."
            )

# Wrap cursor.execute:
class TracedCursor:
    """Cursor wrapper that traces queries."""
    
    def __init__(self, cursor):
        self.cursor = cursor
    
    def execute(self, query, params=None):
        import time
        start = time.time()
        try:
            result = self.cursor.execute(query, params)
            elapsed = time.time() - start
            QueryTracer.trace_query(query, elapsed)
            return result
        except Exception as e:
            elapsed = time.time() - start
            QueryTracer.trace_query(query, elapsed)
            raise
```

**Step B1.2: Enable Oracle SQL statistics**
```sql
-- Run in Oracle as admin:

ALTER SYSTEM SET statistics_level=ALL SCOPE=BOTH;
ALTER SESSION SET statistics_level=ALL;

-- Query performance:
SELECT * FROM v$sql ORDER BY elapsed_time DESC FETCH FIRST 20 ROWS ONLY;
```

**Step B1.3: Create query profiling script**
```python
# NEW FILE: scripts/profile_queries.py

"""
Profile TomeHub queries and identify optimization opportunities.

Run:
    python scripts/profile_queries.py [--duration 300] [--top 20]
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager
from config import settings

def profile_queries(duration_seconds=300, top_n=20):
    """Profile queries over time period."""
    print(f"Profiling queries for {duration_seconds} seconds...")
    print("Run some searches/ingest operations in another terminal\n")
    
    DatabaseManager.init_pool()
    
    start_time = datetime.utcnow() - timedelta(seconds=duration_seconds)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Get top slow queries
            query = """
            SELECT 
                executions,
                elapsed_time/1000000 as elapsed_seconds,
                elapsed_time/executions/1000000 as avg_time_seconds,
                sql_text
            FROM v$sql
            WHERE last_load_time > TO_DATE(:start_time, 'YYYY-MM-DD HH24:MI:SS')
            AND executions > 0
            ORDER BY elapsed_time DESC
            FETCH FIRST :top_n ROWS ONLY
            """
            
            cursor.execute(query, {
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'top_n': top_n
            })
            
            results = cursor.fetchall()
            
            print(f"\n📊 Top {top_n} Slowest Queries (last {duration_seconds}s):\n")
            print(f"{'Exec':<6} {'Total(s)':<10} {'Avg(s)':<10} SQL")
            print("-" * 100)
            
            for exec_count, total_time, avg_time, sql_text in results:
                # Truncate SQL
                sql_short = sql_text[:60].replace('\n', ' ')
                print(f"{exec_count:<6} {total_time:<10.2f} {avg_time:<10.4f} {sql_short}")
    
    DatabaseManager.close_pool()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=300, help="Profile duration (seconds)")
    parser.add_argument("--top", type=int, default=20, help="Top N queries to show")
    args = parser.parse_args()
    
    profile_queries(args.duration, args.top)
```

**Step B1.4: Run profiling during load test**
```bash
# Terminal 1: Start server
python apps/backend/app.py

# Terminal 2: Start profiler
python scripts/profile_queries.py --duration 300 --top 20

# Terminal 3: Generate load (use Apache Bench)
ab -n 1000 -c 50 http://localhost:5001/api/search
```

**Expected Output:**
```
📊 Top 20 Slowest Queries (last 300s):

Exec   Total(s)   Avg(s)    SQL
────────────────────────────────────────────────────────────────
500    125.50     0.2510    SELECT * FROM TOMEHUB_CONTENT WHERE...
300    95.20      0.3173    SELECT * FROM TOMEHUB_CONCEPTS WHERE...
200    80.15      0.4008    SELECT * FROM TOMEHUB_RELATIONS WHERE...
```

**Analysis Questions:**
1. Which queries are slowest? (>1 second average)
2. Which are executed most often? (high `Exec` count)
3. Can they be optimized with indexes? (look for full table scans)
4. Can results be cached? (frequently repeated queries)

**Effort:** 4 hours (includes running load test)  
**Risk:** None (read-only profiling)  
**Deliverable:** List of top 10 slow queries with execution counts

---

### Task B2: Add Query Result Caching (5 hours)

**Goal:** Cache frequently-executed queries for 10-60 minutes

**Step B2.1: Identify cacheable queries**
```python
# Based on profiling, create cache strategy:

# HIGH PRIORITY (cache for 60 min):
# SELECT * FROM TOMEHUB_CONCEPTS WHERE ...  (rarely changes)
# SELECT * FROM TOMEHUB_RELATIONS WHERE ... (rarely changes)

# MEDIUM PRIORITY (cache for 10 min):
# SELECT * FROM TOMEHUB_CONTENT WHERE ... (changes during ingestion)

# LOW PRIORITY (don't cache):
# SELECT FOR UPDATE statements (locking)
# Ingestion writes
```

**Step B2.2: Create query cache layer**
```python
# NEW FILE: services/query_cache_service.py

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class QueryCache:
    """Cache for database query results."""
    
    CACHE_TTL_SECONDS = {
        "concepts": 3600,      # 1 hour
        "relations": 3600,     # 1 hour
        "content": 600,        # 10 minutes
        "default": 300         # 5 minutes
    }
    
    def __init__(self, cache_service):
        """Initialize with main cache service."""
        self.cache = cache_service
    
    @staticmethod
    def _make_key(query: str, params: Dict) -> str:
        """Create cache key from query and parameters."""
        # Normalize query (remove extra whitespace)
        normalized = " ".join(query.split())
        
        # Include params in key
        param_str = json.dumps(params, sort_keys=True, default=str)
        
        # Create hash
        key_data = f"{normalized}:{param_str}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        
        return f"query:{key_hash}"
    
    async def get_cached_results(
        self,
        query: str,
        params: Dict,
        query_type: str = "default"
    ) -> Optional[List[tuple]]:
        """Get cached query results if available."""
        cache_key = self._make_key(query, params)
        ttl = self.CACHE_TTL_SECONDS.get(query_type, self.CACHE_TTL_SECONDS["default"])
        
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Query cache HIT: {query_type}")
            return cached.get("results")
        
        logger.debug(f"Query cache MISS: {query_type}")
        return None
    
    async def set_cached_results(
        self,
        query: str,
        params: Dict,
        results: List[tuple],
        query_type: str = "default"
    ):
        """Cache query results."""
        cache_key = self._make_key(query, params)
        ttl = self.CACHE_TTL_SECONDS.get(query_type, self.CACHE_TTL_SECONDS["default"])
        
        self.cache.set(
            cache_key,
            {"results": results, "cached_at": datetime.utcnow().isoformat()},
            ttl=ttl
        )
```

**Step B2.3: Integrate with search service**
```python
# In services/search_service.py

async def search(query_text: str, firebase_uid: str) -> SearchResult:
    """Search with query result caching."""
    
    # Try to get cached results
    cache_key = f"search:{query_text}"
    cached = await cache_service.get(cache_key)
    if cached:
        logger.info(f"Search cache HIT: {query_text[:50]}")
        return cached
    
    # Cache miss - execute search
    logger.info(f"Search cache MISS: {query_text[:50]}")
    
    # Existing search logic...
    chunks = get_rag_context(query_text)
    answer = await generate_evaluated_answer(query_text, chunks)
    
    result = SearchResult(
        query=query_text,
        answer=answer,
        chunks=chunks,
        cached=False
    )
    
    # Cache result for 10 minutes
    await cache_service.set(cache_key, result, ttl=600)
    
    return result
```

**Testing:**
```bash
# 1. Run same search twice
curl http://localhost:5001/api/search -d '{"query": "What is X?"}'
# First: Not cached, slow response
# Second: Cached, fast response

# 2. Check logs for cache hits
grep "Search cache" logs/app.log
```

**Validation Checklist:**
- [ ] Query cache service created and working
- [ ] Cache keys are unique per query + params
- [ ] TTL works correctly (results expire)
- [ ] Cache invalidated on new ingestion
- [ ] Logs show cache hits/misses

**Effort:** 5 hours  
**Risk:** Medium (need to invalidate on writes)  
**Expected Improvement:** 60% reduction in repeated query latency

---

### Task B3: Optimize N+1 Query Pattern (6 hours)

**Goal:** Reduce detail API calls that trigger N+1 queries

**Step B3.1: Identify N+1 patterns**
```
Current behavior:
GET /api/search?q=dasein → Returns 100 items with IDs
Client makes: GET /api/content/1, /api/content/2, ... /api/content/100
Result: 100 individual database queries!

Better API:
GET /api/search?q=dasein&include=details → Returns full items in one query
Client makes: Nothing (results already include details)
Result: 1 database query instead of 101
```

**Step B3.2: Update search response model**
```python
# In models/request_models.py

class SearchRequest(BaseModel):
    query: str
    include_details: bool = False  # NEW
    max_results: int = 50
    page: int = 1

class SearchResult(BaseModel):
    query: str
    results: List[Dict]  # Contains full details if requested
    total_count: int
    execution_time_ms: float
    cache_hit: bool
```

**Step B3.3: Update search service**
```python
# In services/search_service.py

async def search(
    request: SearchRequest,
    firebase_uid: str
) -> SearchResult:
    """
    Search with optional detail inclusion.
    
    If include_details=False:
        - Return minimal data (id, title, score)
        - Client can fetch details separately if needed
        - Reduces network bandwidth
    
    If include_details=True:
        - Return full data in one query (using JOIN)
        - Slightly slower but avoids N+1 problem
        - Better for mobile clients with high latency
    """
    
    if request.include_details:
        # Single query with JOINs to fetch all details
        query = """
        SELECT 
            tc.id, tc.title, tc.content, tc.source_type,
            tc.page_number, tc.book_id, tm.metadata
        FROM TOMEHUB_CONTENT tc
        LEFT JOIN TOMEHUB_METADATA tm ON tc.id = tm.content_id
        WHERE CONTAINS(tc.content, :search_text) = 1
        ORDER BY SCORE(1) DESC
        FETCH FIRST :limit ROWS ONLY
        """
        
        results = await execute_query_with_caching(query, {"search_text": request.query})
    else:
        # Minimal query, client fetches details on demand
        query = """
        SELECT id, title, SCORE(1) as relevance_score
        FROM TOMEHUB_CONTENT
        WHERE CONTAINS(content, :search_text) = 1
        ORDER BY SCORE(1) DESC
        FETCH FIRST :limit ROWS ONLY
        """
        
        results = await execute_query_with_caching(query, {"search_text": request.query})
    
    return SearchResult(
        query=request.query,
        results=results,
        total_count=len(results),
        execution_time_ms=elapsed_ms,
        cache_hit=was_cached
    )
```

**Step B3.4: Add batch detail endpoint**
```python
# In app.py

@app.post("/api/content/batch")
async def get_content_batch(
    ids: List[int],
    firebase_uid: str = Depends(verify_firebase_token)
):
    """Get multiple content items in one query (instead of N+1)."""
    
    query = """
    SELECT * FROM TOMEHUB_CONTENT
    WHERE id IN (:ids)
    ORDER BY CASE WHEN id = :first_id THEN 1 ELSE 2 END
    """
    
    # Execute single query for all IDs
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, {
                "ids": ids,
                "first_id": ids[0]
            })
            results = cursor.fetchall()
    
    return {"items": results}
```

**Testing:**
```bash
# Before optimization:
time for i in {1..100}; do 
  curl http://localhost:5001/api/content/$i 
done
# Time: 15-20 seconds (100 individual queries)

# After optimization:
curl http://localhost:5001/api/search \
  -d '{"query":"dasein","include_details":true}'
# Time: 2-3 seconds (single query with JOIN)

# Or batch endpoint:
curl http://localhost:5001/api/content/batch \
  -d '{"ids":[1,2,3,...,100]}'
# Time: 500-800ms (single batch query)
```

**Validation Checklist:**
- [ ] Search endpoint supports `include_details` parameter
- [ ] Batch endpoint implemented and working
- [ ] Performance improvement measured (should be 10-20x faster)
- [ ] Database execution plan uses JOINs (not N+1)
- [ ] Both endpoints return consistent data

**Effort:** 6 hours  
**Risk:** Medium (API change, backward compatibility)  
**Expected Improvement:** Eliminate N+1 query pattern, 10-20x faster detail retrieval

---

### Task B4: Implement Query Pagination (3 hours)

**Goal:** Reduce memory by not loading all results at once

**Step B4.1: Update search model**
```python
# In models/request_models.py

class SearchRequest(BaseModel):
    query: str
    page: int = 1
    page_size: int = 50  # Max results per page
    include_details: bool = False
    
    @validator('page')
    def page_positive(cls, v):
        if v < 1:
            raise ValueError('page must be >= 1')
        return v
    
    @validator('page_size')
    def page_size_reasonable(cls, v):
        if v > 1000:
            raise ValueError('page_size must be <= 1000')
        return v

class SearchResult(BaseModel):
    query: str
    results: List[Dict]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    execution_time_ms: float
    cache_hit: bool
```

**Step B4.2: Update search query**
```python
# In services/search_service.py

async def search(request: SearchRequest) -> SearchResult:
    """Search with pagination."""
    
    # Get total count (cached)
    count_query = "SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE CONTAINS(content, :search_text) = 1"
    total_count = await get_cached_count(count_query, request.query)
    
    # Calculate offset
    offset = (request.page - 1) * request.page_size
    
    # Get paginated results
    query = f"""
    SELECT * FROM (
        SELECT tc.*, ROW_NUMBER() OVER (ORDER BY SCORE(1) DESC) as rn
        FROM TOMEHUB_CONTENT tc
        WHERE CONTAINS(tc.content, :search_text) = 1
    )
    WHERE rn BETWEEN :offset + 1 AND :offset + :limit
    """
    
    results = await execute_query(query, {
        "search_text": request.query,
        "offset": offset,
        "limit": request.page_size
    })
    
    total_pages = (total_count + request.page_size - 1) // request.page_size
    
    return SearchResult(
        query=request.query,
        results=results,
        total_count=total_count,
        page=request.page,
        page_size=request.page_size,
        total_pages=total_pages,
        has_next=request.page < total_pages,
        execution_time_ms=elapsed_ms,
        cache_hit=was_cached
    )
```

**Testing:**
```bash
# Get first page
curl 'http://localhost:5001/api/search' \
  -d '{"query":"dasein","page":1,"page_size":50}'

# Get second page
curl 'http://localhost:5001/api/search' \
  -d '{"query":"dasein","page":2,"page_size":50}'
```

**Validation Checklist:**
- [ ] Pagination parameters validated
- [ ] Total count calculated correctly
- [ ] Offset/limit applied correctly
- [ ] has_next flag accurate
- [ ] Performance: Single page fast (50 results <<< 10000 results)

**Effort:** 3 hours  
**Risk:** Low (pure query optimization)  
**Expected Improvement:** Faster initial response, lower memory per query

---

## PHASE C: Resilience Hardening (Week 3-4)

### Task C1: Implement Read/Write Connection Pools (4 hours)

**Goal:** Separate read-heavy searches from write-heavy ingestion

**Problem:**
- Ingestion uses all 40 connections
- Searches starve waiting for connections
- Solution: Two separate pools

**Step C1.1: Create separate pool managers**
```python
# In infrastructure/db_manager.py

class ReadConnectionPool:
    """Pool for SELECT queries (reads)."""
    
    _pool = None
    
    @classmethod
    def init_pool(cls, settings):
        """Initialize read pool (can be larger)."""
        cls._pool = oracledb.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=settings.DB_DSN,
            min=5,
            max=50,  # Large pool for reads
            timeout=30
        )
    
    @classmethod
    def get_connection(cls):
        """Get read connection."""
        return cls._pool.acquire()


class WriteConnectionPool:
    """Pool for INSERT/UPDATE/DELETE queries (writes)."""
    
    _pool = None
    
    @classmethod
    def init_pool(cls, settings):
        """Initialize write pool (smaller, prioritized)."""
        cls._pool = oracledb.create_pool(
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dsn=settings.DB_DSN,
            min=2,
            max=10,  # Smaller pool, ingestion is less frequent
            timeout=30
        )
    
    @classmethod
    def get_connection(cls):
        """Get write connection."""
        return cls._pool.acquire()


class DatabaseManager:
    """High-level manager supporting both pools."""
    
    @staticmethod
    def init_pool(settings):
        """Initialize both read and write pools."""
        ReadConnectionPool.init_pool(settings)
        WriteConnectionPool.init_pool(settings)
    
    @staticmethod
    def get_read_connection():
        """Get connection for SELECT."""
        return ReadConnectionPool.get_connection()
    
    @staticmethod
    def get_write_connection():
        """Get connection for INSERT/UPDATE/DELETE."""
        return WriteConnectionPool.get_connection()
```

**Step C1.2: Update search service to use read pool**
```python
# In services/search_service.py

async def search(query_text: str):
    """Search uses read pool."""
    
    # Use read pool (large, 50 connections)
    connection = DatabaseManager.get_read_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM TOMEHUB_CONTENT WHERE ...")
            results = cursor.fetchall()
    finally:
        connection.close()
```

**Step C1.3: Update ingestion service to use write pool**
```python
# In services/ingestion_service.py

async def ingest_document(doc_data):
    """Ingestion uses write pool."""
    
    # Use write pool (small, 10 connections)
    connection = DatabaseManager.get_write_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO TOMEHUB_CONTENT VALUES (...)", doc_data)
            connection.commit()
    finally:
        connection.close()
```

**Configuration:**
```bash
# In .env:
DB_POOL_READ_SIZE=50           # Large pool for searches
DB_POOL_WRITE_SIZE=10          # Small pool for ingestion
DB_POOL_TIMEOUT=30
```

**Testing:**
```bash
# Terminal 1: Start ingestion (uses write pool)
python -c "from services.ingestion_service import ingest_book; ingest_book(...)"

# Terminal 2: Run searches (uses read pool)
for i in {1..100}; do
  curl http://localhost:5001/api/search -d '{"query":"test"}' &
done

# Observe: Searches don't block on ingestion
```

**Validation Checklist:**
- [ ] Two pools initialized at startup
- [ ] Logs show pool status: "Read: 5-50, Write: 2-10"
- [ ] Search queries use read pool
- [ ] Ingestion queries use write pool
- [ ] Under combined load: searches not blocked by ingestion

**Effort:** 4 hours  
**Risk:** Medium (affects connection management)  
**Expected Improvement:** Searches not blocked during ingestion (10x improvement in combined load)

---

### Task C2: Implement Stream Backpressure Limiting (4 hours)

**Goal:** Limit concurrent streams to prevent memory exhaustion

**Step C2.1: Create stream limiter**
```python
# NEW FILE: services/stream_limiter_service.py

import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class StreamLimiter:
    """Limit concurrent streaming responses to prevent OOM."""
    
    def __init__(self, max_concurrent_streams: int = 100):
        """Initialize limiter."""
        self.max_concurrent = max_concurrent_streams
        self.semaphore = asyncio.Semaphore(max_concurrent_streams)
        self.active_streams = 0
        self.lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a stream slot. Blocks if at max."""
        await self.semaphore.acquire()
        
        async with self.lock:
            self.active_streams += 1
            logger.debug(f"Stream acquired: {self.active_streams}/{self.max_concurrent}")
    
    async def release(self) -> None:
        """Release a stream slot."""
        self.semaphore.release()
        
        async with self.lock:
            self.active_streams -= 1
            logger.debug(f"Stream released: {self.active_streams}/{self.max_concurrent}")
    
    async def get_status(self) -> dict:
        """Get current stream status."""
        async with self.lock:
            return {
                "active_streams": self.active_streams,
                "max_concurrent": self.max_concurrent,
                "utilization": self.active_streams / self.max_concurrent
            }


# Global instance
stream_limiter = StreamLimiter(max_concurrent_streams=100)
```

**Step C2.2: Update streaming endpoints**
```python
# In app.py

from services.stream_limiter_service import stream_limiter

@app.post("/api/search/stream")
async def search_stream(request: SearchRequest, firebase_uid: str = Depends(verify_firebase_token)):
    """Search with streaming response, with backpressure limiting."""
    
    # Acquire stream slot (blocks if at capacity)
    try:
        await stream_limiter.acquire()
    except Exception as e:
        logger.error(f"Stream limit error: {e}")
        return JSONResponse(
            status_code=503,
            content={"error": "Server at stream capacity, please retry"}
        )
    
    try:
        # Generate streaming response
        async def stream_generator():
            try:
                chunks = await get_rag_context(request.query)
                yield json.dumps({"status": "chunks_loaded", "count": len(chunks)}) + "\n"
                
                answer = await generate_evaluated_answer(request.query, chunks)
                yield json.dumps({"status": "answer", "text": answer}) + "\n"
                
                yield json.dumps({"status": "complete"}) + "\n"
            finally:
                # This won't work with StreamingResponse, need different approach
                pass
        
        return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
    
    finally:
        # Release after stream completes
        await stream_limiter.release()
```

**Better approach with context manager:**
```python
# Create async context manager

class StreamSession:
    """Context manager for stream limiting."""
    
    def __init__(self, limiter: StreamLimiter):
        self.limiter = limiter
    
    async def __aenter__(self):
        await self.limiter.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.limiter.release()
        return False


# Usage:
@app.post("/api/search/stream")
async def search_stream(...):
    async with StreamSession(stream_limiter):
        # Streaming response
        return StreamingResponse(stream_generator())
```

**Step C2.3: Add health endpoint for streams**
```python
@app.get("/api/health/streams")
async def health_streams():
    """Get streaming endpoint health."""
    status = await stream_limiter.get_status()
    
    return {
        "status": "ok",
        "streams": status,
        "health": "critical" if status["utilization"] > 0.9 else "ok"
    }
```

**Configuration:**
```bash
# In config.py:
self.MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "100"))

# In .env:
MAX_CONCURRENT_STREAMS=100     # Adjust based on memory capacity
```

**Testing:**
```bash
# Simulate 101 concurrent streams
python -c "
import asyncio
import httpx

async def stream():
    async with httpx.AsyncClient() as client:
        async with client.stream('GET', 'http://localhost:5001/api/search/stream') as r:
            async for chunk in r.aiter_text():
                pass

async def main():
    tasks = [stream() for _ in range(101)]
    await asyncio.gather(*tasks)

asyncio.run(main())
"
```

**Validation Checklist:**
- [ ] StreamLimiter initialized with max capacity
- [ ] 100th stream completes successfully
- [ ] 101st stream waits or gets 503
- [ ] Memory stays below limit during heavy streaming
- [ ] Health endpoint shows stream count

**Effort:** 4 hours  
**Risk:** Medium (needs careful async handling)  
**Expected Improvement:** No more OOMkiller, graceful rejection at capacity

---

### Task C3: Implement Memory Pressure Response (3 hours)

**Goal:** Auto-scale when memory gets high, don't wait for OOMkiller

**Step C3.1: Implement auto-restart mechanism**
```python
# NEW FILE: services/auto_restart_service.py

import asyncio
import psutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AutoRestartManager:
    """Auto-restart worker if memory pressure too high."""
    
    CRITICAL_THRESHOLD = 0.85  # 85% memory usage
    WARNING_THRESHOLD = 0.75   # 75% memory usage
    CHECK_INTERVAL = 30        # Check every 30 seconds
    
    def __init__(self):
        self.memory_samples = []  # Track memory over time
        self.restart_requested = False
    
    async def monitor(self):
        """Monitor memory and request restart if critical."""
        while True:
            try:
                vm = psutil.virtual_memory()
                memory_percent = vm.percent / 100.0
                
                self.memory_samples.append(memory_percent)
                if len(self.memory_samples) > 10:
                    self.memory_samples.pop(0)
                
                if memory_percent >= self.CRITICAL_THRESHOLD:
                    # Memory critical - request restart
                    logger.critical(
                        f"🔴 MEMORY CRITICAL {memory_percent:.1%}. "
                        f"Requesting graceful shutdown."
                    )
                    self.restart_requested = True
                    # Stop accepting new requests
                    # Wait for current requests to finish
                    # Then shutdown cleanly
                    await self._graceful_shutdown()
                
                elif memory_percent >= self.WARNING_THRESHOLD:
                    logger.warning(
                        f"🟡 MEMORY WARNING {memory_percent:.1%}. "
                        f"Recent avg: {sum(self.memory_samples)/len(self.memory_samples):.1%}"
                    )
                
                await asyncio.sleep(self.CHECK_INTERVAL)
            
            except Exception as e:
                logger.error(f"Memory monitor error: {e}")
                await asyncio.sleep(self.CHECK_INTERVAL)
    
    async def _graceful_shutdown(self):
        """Gracefully shutdown when memory critical."""
        logger.info("Starting graceful shutdown...")
        
        # Option 1: Signal parent process (systemd/Docker) to restart
        # os.kill(os.getpid(), signal.SIGTERM)
        
        # Option 2: Mark as unhealthy and wait for load balancer to drain
        self.restart_requested = True
        await asyncio.sleep(30)  # Wait 30s for connections to drain
        
        logger.info("Forcing shutdown now.")
        import sys
        sys.exit(1)  # Exit, let supervisor restart
    
    async def get_status(self) -> dict:
        """Get memory status."""
        vm = psutil.virtual_memory()
        recent_avg = sum(self.memory_samples) / len(self.memory_samples) if self.memory_samples else 0
        
        return {
            "current_percent": vm.percent,
            "recent_average": recent_avg * 100,
            "restart_requested": self.restart_requested,
            "critical_threshold": self.CRITICAL_THRESHOLD * 100,
            "warning_threshold": self.WARNING_THRESHOLD * 100
        }


auto_restart_manager = AutoRestartManager()
```

**Step C3.2: Integrate into lifespan**
```python
# In app.py lifespan:

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting memory monitor...")
    memory_task = asyncio.create_task(auto_restart_manager.monitor())
    
    # ... rest of startup
    
    yield
    
    # Shutdown
    memory_task.cancel()
    DatabaseManager.close_pool()
```

**Step C3.3: Add health endpoint**
```python
@app.get("/api/health/restart")
async def health_restart():
    """Get auto-restart status."""
    status = await auto_restart_manager.get_status()
    
    return {
        "status": "ok" if not status["restart_requested"] else "restarting",
        "memory": status
    }
```

**Docker/Systemd Integration:**
```yaml
# docker-compose.yml
services:
  tomehub:
    image: tomehub:latest
    restart: always  # Auto-restart if exits
    deploy:
      resources:
        limits:
          memory: 2G  # Memory limit for container
        reservations:
          memory: 1G  # Guaranteed memory
```

**Testing:**
```bash
# Monitor memory
watch -n 5 'curl http://localhost:5001/api/health/memory | jq .'
watch -n 5 'curl http://localhost:5001/api/health/restart | jq .'

# Should see memory warning at 75%, critical at 85%
```

**Validation Checklist:**
- [ ] Auto-restart manager starts and monitors
- [ ] Warning logged at 75% memory
- [ ] Graceful shutdown at 85% memory
- [ ] Process exits cleanly (can be restarted)
- [ ] Health endpoints show status

**Effort:** 3 hours  
**Risk:** Low (monitioring + auto-restart)  
**Expected Improvement:** No OOMkiller surprise kills, graceful restart instead

---

## PHASE D: Monitoring & Observability (Week 4-6)

### Task D1: Add Prometheus Metrics (5 hours)

[See detailed Prometheus metrics implementation in separate section]

### Task D2: Create Grafana Dashboards (4 hours)

[See detailed Grafana dashboard setup in separate section]

### Task D3: Implement Alerting Rules (3 hours)

[See detailed AlertManager rules in separate section]

### Task D4: Add Circuit Breaker Metrics (2 hours)

[See detailed circuit breaker metrics integration in separate section]

---

## 📋 Implementation Checklist

### Week 1: Quick Wins
- [ ] A1: Increase DB pool to 40
- [ ] A2: Add memory monitoring
- [ ] A3: Implement rate limiting
- **Result:** Handle 100-150 concurrent users
- **Time:** 7 hours

### Week 2-3: Query Optimization
- [ ] B1: Profile queries (identify slow queries)
- [ ] B2: Add query result caching (10-60min TTL)
- [ ] B3: Optimize N+1 patterns (batch API)
- [ ] B4: Implement pagination
- **Result:** 60% reduction in DB load
- **Time:** 18 hours

### Week 3-4: Resilience
- [ ] C1: Separate read/write pools
- [ ] C2: Stream backpressure limiting
- [ ] C3: Memory pressure auto-restart
- **Result:** Graceful degradation, no OOMkiller
- **Time:** 11 hours

### Week 4-6: Monitoring
- [ ] D1: Prometheus metrics
- [ ] D2: Grafana dashboards
- [ ] D3: AlertManager rules
- [ ] D4: Circuit breaker metrics
- **Result:** Full observability, proactive alerting
- **Time:** 14 hours

---

## 🎯 Load Testing Checkpoints

### Before Implementation
```
100 concurrent users:
  - Error rate: 20-30%
  - p95 latency: 8-12s
  - Bottleneck: Database pool
```

### After Phase A (Quick Wins)
```
100 concurrent users:
  - Error rate: 5-10%
  - p95 latency: 5-7s
  - Improvement: Pool increase helps, still hitting SLA
```

### After Phase B (Query Optimization)
```
150 concurrent users:
  - Error rate: 5%
  - p95 latency: 4-6s
  - Improvement: Queries faster, less queue wait
```

### After Phase C (Resilience)
```
200 concurrent users:
  - Error rate: 2-3%
  - p95 latency: 5-7s
  - Improvement: Memory safe, graceful degradation
```

### After Phase D (Monitoring)
```
300+ concurrent users:
  - Full visibility into system behavior
  - Proactive alerting before failures
  - Can scale further with data-driven decisions
```

---

## 🚀 Deployment Strategy

### Phased Rollout
```
Week 1:   Phase A on staging → Load test → Deploy to prod
Week 2:   Phase B on staging → Load test → Deploy to prod
Week 3:   Phase C on staging → Load test → Deploy to prod
Week 4:   Phase D on staging → Load test → Deploy to prod
```

### Rollback Plan
Each phase is reversible:
- Phase A: Reduce pool size back to 20
- Phase B: Disable caching, revert API changes
- Phase C: Remove backpressure limiting
- Phase D: Disable metrics collection

### Monitoring During Rollout
```
- Database pool utilization
- Query latency percentiles
- Error rates by endpoint
- Memory usage trends
- Cache hit rates
```

---

## 📊 Success Criteria

| Phase | Target | Measurement |
|-------|--------|-------------|
| A | 150 users | Error rate <10%, p95 <8s |
| B | 200 users | DB queries -60%, cache hit >70% |
| C | 250 users | Memory stable, no OOMkiller |
| D | 300+ users | Full observability, proactive alerts |

---

**Next Steps:**
1. Review and approve implementation plan
2. Assign tasks to team members
3. Create Jira tickets for each task
4. Begin Phase A (Week 1)
5. Schedule weekly load tests

---

**Document Generated:** February 2, 2026  
**Target Start:** Week of Feb 3, 2026  
**Estimated Completion:** Week of Mar 16, 2026
