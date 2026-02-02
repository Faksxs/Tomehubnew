# TomeHub System - SRE Mental Stress Test Report
**Date:** February 2, 2026  
**System:** Async FastAPI + Oracle Pool + L1/L2 Cache + LLM Integration  
**Scenario:** Production high-load stress testing

---

## Executive Summary

| Metric | Current | Breaking Point | Risk Level |
|--------|---------|-----------------|------------|
| Pool Size | 20 conn | 15-18 → Queueing | 🔴 HIGH |
| Cache Hit Rate | 60-70% | <40% → L2 thrash | 🟡 MEDIUM |
| LLM Latency p95 | 2-3s | >5s → Circuit open | 🔴 HIGH |
| Streaming Timeout | 60s | 30s timeout → Drops | 🟠 MEDIUM |
| Memory per Worker | 200-300MB | >500MB → OOM | 🔴 HIGH |

---

## 1. LOAD SCENARIOS & FAILURE MODES

### Scenario 1A: Concurrent Search Queries (100 simultaneous)

**Load Profile:**
```
┌─ 100 concurrent users
├─ Each: /search (complex query, 5-7 second SLA)
├─ Backend workers: 4 (Uvicorn)
├─ Oracle pool: 20 connections
└─ LLM calls per search: 2-3 (embeddings + generation)
```

**Timeline:**

```
T=0s:   100 requests arrive
        ├─ 4 workers start processing (4 workers × 4 concurrent = 16 max concurrent)
        ├─ 84 requests queue in Uvicorn (FastAPI backlog)
        └─ Database pool: 4 connections used, 16 available
        
T=0.5s: LLM embedding API calls start (100 × 2 = 200 embedding requests)
        ├─ 20 circuit breaker slots filled
        ├─ 180 requests queue in circuit breaker
        ├─ p95 LLM latency: 2-3s
        └─ Some requests start HALF_OPEN recovery test
        
T=1s:   Cache hit rate analysis
        ├─ L1 cache: 60 hits (60% of 100)
        ├─ L2 cache (Redis): 15 hits (15% of remaining 40)
        ├─ Database queries: 25 × 3-5 queries each = 75-125 queries
        ├─ Database pool: 18-20 connections active
        └─ Remaining 0-2 connections for new requests
        
T=3s:   LLM returns (first batch completed)
        ├─ Response generation starts
        ├─ Streaming begins (60+ concurrent streams)
        ├─ Memory: 4 workers × 100MB per stream = 400MB
        └─ Network: 60 streams × 1-5 Mbps = 60-300 Mbps
        
T=3-7s: Timeout risk window
        ├─ Queued requests hit 5-7s SLA
        ├─ Users waiting >5s start retrying
        ├─ 20-30 retry requests add to queue
        ├─ Pool exhaustion: 20/20 connections + queue of 15-20
        └─ New requests wait 2-3s just for connection
        
T=7s:   First requests complete, releases begin
        ├─ 40-50 requests complete successfully
        ├─ 30-40 requests timeout (SLA breach)
        ├─ 20-30 retried requests start processing
        └─ Cascading effect: more retries than completions
        
T=10s:  System degraded
        ├─ Success rate: 50-60%
        ├─ Timeout rate: 20-30%
        ├─ Retry rate: 15-25%
        └─ Response time p95: 8-12 seconds
        
T=15s:  Recovery phase (if no circuit breaker failure)
        ├─ Most original requests complete
        ├─ Retry queue drains
        ├─ Connection pool returns to normal
        └─ System stabilizes
```

**Failure Mode: SLOW DEGRADATION**
- Not a hard crash, but graceful performance decline
- Success rate stays >50% but SLA consistently breached
- Timeouts cluster around the 5-7s window
- Retries extend problem for 5-10 more seconds

**Bottleneck Analysis:**
```
1. Database Connection Pool (20 conn)
   Issue: 100 concurrent search queries need ~100 DB calls
   Queue depth: 75-80 waiting for connection
   Wait time: 1-3s per connection
   
2. LLM Circuit Breaker (Single global instance)
   Issue: 200 embedding requests queued
   Max throughput: ~30 embeddings/sec (if no failures)
   Batch latency: 6-8 seconds for all 200
   Risk: If any fail, circuit opens for ALL searches
   
3. Async Task Queue
   Issue: FastAPI only has 4 workers
   Backpressure: 84/100 requests queued immediately
   Queueing latency: 1-2s before worker even touches request
   
4. Memory per concurrent stream
   Issue: 60 concurrent streams × 1-5MB each = 60-300MB
   Worker process: ~200MB baseline + 60-300MB streaming
   Total per worker: 260-500MB × 4 = 1-2GB
```

---

### Scenario 1B: Same Load, But Cache is Cold

**Assumptions:**
- Redis down or cache invalidated
- All 100 searches miss L1 + L2
- All 100 require fresh database queries + LLM calls

**Timeline:**

```
T=0s:   100 requests arrive
        └─ All will miss cache (guaranteed)
        
T=0.5s: Database load
        ├─ 100 searches × 5 queries = 500 DB queries
        ├─ Pool: 20 conn, 480 queued
        ├─ Queue depth: 480 waiting queries
        └─ Average wait: 500 queries ÷ 20 conn ÷ T seconds
        
T=1s:   DB exhaustion phase
        ├─ Slow queries start (cache miss = full table scans)
        ├─ Query latency: 500ms → 2s (without index)
        ├─ Timeout cascade: Queries waiting 2-3s
        ├─ Circuit breaker: 200 embedding requests piled up
        └─ p95 latency: 8-12s already
        
T=2-3s: FAILURE POINT
        ├─ 30-40% of searches timeout (before completion)
        ├─ Retries add 50-100 more queries
        ├─ Database connection pool: 20/20 all waiting
        ├─ Memory: 4 workers × 300MB = 1.2GB (streaming)
        └─ System enters cascading failure
        
T=3-5s: Cascade worsens
        ├─ New requests start getting connection timeout (0ms response)
        ├─ Load balancer sees failures, might mark backend unhealthy
        ├─ Remaining cache hits can't keep up with failures
        └─ Error rate: 40-60%
```

**Failure Mode: SUDDEN COLLAPSE**
- Not slow degradation, but sudden timeout wall
- Error rate jumps from 0% to 40%+ in <2 seconds
- Once database exhausted, recovery takes 30-60s
- If LLM circuit breaker also opens: complete failure for searches

**Cascade Chain:**
```
Cold cache → 500 DB queries queued
          → 20 connections all busy
          → New requests timeout immediately
          → Retries add to queue
          → More timeouts
          → Circuit breaker opens (if LLM also slow)
          → Search completely fails for 5+ minutes
```

---

### Scenario 2: LLM Embedding API Degradation

**Load Profile:**
```
- 50 concurrent searches (moderate load)
- Each needs 2 embedding API calls
- LLM API becomes slow: 5s latency (vs normal 1-2s)
- Then fails: 50% error rate for 10 minutes
```

**Timeline (Without Circuit Breaker):**
```
T=0s:   50 searches start
        ├─ 100 embedding requests sent to LLM API
        └─ Normal latency: 1-2s
        
T=2s:   LLM performance degrades (5s latency observed)
        ├─ All 50 requests now blocked waiting for embeddings
        ├─ Database work done, waiting for LLM
        ├─ Response queue building
        └─ Worker threads: All 4 waiting on LLM I/O
        
T=5s:   First embedding responses return
        ├─ But new requests continue arriving
        ├─ New embeddings sent to slow LLM
        ├─ Queue depth: 30-40 awaiting LLM
        └─ Response time: 5s LLM + 2s DB + 1s generation = 8s
        
T=10s:  LLM API fails outright (50% errors)
        ├─ 50 new requests, 25 embedding calls fail
        ├─ Without circuit breaker: retries compound
        ├─ Retry storm: 25 failed × 3 retries = 75 extra requests
        ├─ Total: 75 requests queued for failed LLM
        └─ New users continue arriving → queue grows to 200+
        
T=15s:  Cascading failure
        ├─ All searches blocked on LLM
        ├─ Error rate: 75%+ (everything times out)
        ├─ Queue depth: 200+ requests
        ├─ Recovery time: When LLM API recovers (10-30 min? manually?)
        └─ System completely broken for searches
```

**Failure Mode: RESOURCE STARVATION**
- All 4 workers blocked on slow LLM I/O
- No capacity for new requests
- Queue grows unbounded
- Memory exhaustion: Each waiting request = 1-5MB
- With 200+ queued: 200-1000MB additional memory

**Impact Without Phase 2 (Circuit Breaker):**
```
❌ No fast-fail mechanism
❌ Requests wait full timeout (20-30s in some cases)
❌ Retry amplification: 1 failure → 3 retries → 3 more failures
❌ Memory leak: Waiting requests accumulate in queue
❌ Eventually: OOM crash or kernel kills process
```

**Impact WITH Phase 2 (Circuit Breaker):**
```
✅ Circuit opens after 5 failures
✅ Fast-fail: 1ms rejection instead of 20s timeout
✅ No retry amplification
✅ Graceful degradation: Keyword search still works
✅ Recovery: Automatic retry after 5 minutes
```

---

### Scenario 2B: Long-Running Ingestion + Peak Search Load

**Load Profile:**
```
- Batch ingestion: 10,000 documents being processed
- Each document: 5-10 DB inserts + 1 embedding call
- Concurrently: 50 user searches arrive
```

**Timeline:**

```
T=0s:   Ingestion starts
        ├─ 10,000 docs × 5 inserts = 50,000 DB writes
        ├─ Database pool: 10 connections reserved for ingestion
        ├─ Available for searches: 10 connections
        └─ LLM capacity: 50% reserved for ingestion embeddings
        
T=30s:  Peak search load arrives (50 concurrent users)
        ├─ Each search needs: 5 DB queries + 2 embeddings
        ├─ Available pool: Only 10 connections
        ├─ Queue depth: 50 searches × 5 queries = 250 queued
        ├─ LLM: Already handling 10,000 embedding requests
        ├─ Circuit breaker: 50% capacity left (if any)
        └─ Database queue: 250+ waiting
        
T=60s:  Database becomes bottleneck
        ├─ Ingestion: 50,000 writes in progress
        ├─ Searches: 250 queries queued
        ├─ Pool: 20/20 all ingestion-related
        ├─ Search latency: p95 = 30s+ (beyond SLA)
        ├─ Search error rate: 40-50% (timeout)
        └─ Users experience "search is broken"
        
T=120s: Ingestion still ongoing
        ├─ 60% of original documents processed
        ├─ User searches: Still queued, still timing out
        ├─ Cascading retries: 50-100 more requests
        ├─ Error logs: Flooded with timeouts
        └─ System appears broken (but it's just slow)
        
T=180s: Ingestion complete
        ├─ All 10,000 documents inserted
        ├─ 10 connections freed up
        ├─ Search queue finally drains
        ├─ Searches complete: 8-15s latency (delayed but successful)
        └─ Users see recovered system
```

**Failure Mode: RESOURCE CONTENTION**
- Not a crash, but catastrophic slow-down
- Both operations blocked each other
- Search SLA breached for 3-5 minutes
- User experience: "System is down" even though it's working

**Root Cause:**
```
Problem 1: Single shared database pool
- No QoS or priority queuing
- Ingestion eats all 20 connections
- Searches starved

Problem 2: Single shared LLM circuit breaker
- Ingestion embeddings use 80% capacity
- Only 20% left for search embeddings
- Circuit breaker can't differentiate priority

Problem 3: No load shedding
- Both ingestion + search try to complete
- Neither gets enough resources
- Both slow to crawl

Solution needed:
- Separate pools for read vs write
- Priority queuing (search >urgent > ingestion)
- Load shedding (reject low-priority under high load)
```

---

### Scenario 3: Memory Exhaustion with Streaming

**Load Profile:**
```
- 40 concurrent searches with streaming responses
- Each stream: 1-5MB response (depends on richness)
- Worker process baseline: 200MB
- Total worker capacity: ~500MB (per worker)
```

**Timeline:**

```
T=0s:   40 concurrent streams start
        ├─ Worker 1: 200MB baseline + 40 × 1MB = 240MB
        ├─ Worker 2: 200MB baseline + 40 × 1MB = 240MB
        ├─ Worker 3: 200MB baseline + 40 × 1MB = 240MB
        ├─ Worker 4: 200MB baseline + 40 × 1MB = 240MB
        └─ Total: ~960MB (under 1GB, OK)
        
T=1s:   Streams build up
        ├─ Some streams complete (100-200ms)
        ├─ New requests queue behind existing streams
        ├─ Average stream duration: 2-3s (slow network)
        ├─ Concurrent streams: 40 still active + 20 new arriving
        ├─ Per worker now: 200MB + 60 × 1MB = 260MB
        └─ Total: ~1.04GB (approaching memory pressure)
        
T=2s:   Network becomes slow
        ├─ Client bandwidth limited (slow 3G/4G)
        ├─ Streams take 5-10s to complete instead of 2s
        ├─ Concurrent count: 40 + 30 new = 70 total
        ├─ Per worker: 200MB + 70 × 1MB = 270MB
        ├─ Plus buffer for response bodies
        └─ Total: ~1.3GB (memory pressure!)
        
T=3-4s: MEMORY PRESSURE PHASE
        ├─ Linux kernel: Memory pressure > 80%
        ├─ Swap I/O triggered (if swap exists)
        ├─ Response latency jumps: 5s → 15s (due to swap)
        ├─ New stream setup slower (memory allocation struggle)
        ├─ Garbage collection running more frequently
        └─ Worker threads: Slowing due to GC pauses
        
T=5s:   OOM killer activates
        ├─ If memory pressure > 95%
        ├─ Kernel randomly kills process
        ├─ Scenario A: Kills worker (70 streams dropped)
        ├─ Scenario B: Kills entire Python process (all 4 workers down)
        └─ Result: 280-1120 users see connection reset
        
```

**Failure Mode: SILENT RESOURCE EXHAUSTION**
- System doesn't report being out of memory
- Streams just slowly get dropped
- Users see: "Connection reset by peer"
- Logs: Maybe OOMkiller mention, but buried
- SRE sees: Intermittent connection drops, no clear cause

**Memory Amplification:**
```
Response body alone: 1-5MB per stream
Per-stream overhead:
  - Python object overhead: 50-100KB
  - Async task state: 50KB
  - Buffer cache: 100-500KB (if buffering response)
  - Socket buffer: 64KB (TCP send buffer)
  
Real memory per stream: 200KB - 1MB beyond response body

With 70 concurrent streams:
  - 70 × 3MB avg (body + overhead) = 210MB
  - 4 workers × 200MB baseline = 800MB
  - Total: 1GB just for this scenario
  
Plus system overhead:
  - OS page cache: 100-200MB
  - Other processes: 100-500MB
  
Total system memory with 40-70 streams: 1.2-1.5GB
```

**Mitigation Gaps:**
```
❌ No stream buffer limit per request
❌ No max concurrent streams hard limit (e.g., reject if >100)
❌ No memory monitoring/alerting
❌ No graceful degradation on memory pressure
❌ No backpressure mechanism (server stops accepting streams)
```

---

### Scenario 4: Database Query Amplification (N+1 Problem)

**Scenario:** Search returns 100 results, frontend requests details for each

**Timeline:**

```
T=0s:   User searches: "What is Dasein?"
        └─ Single query: SELECT * FROM TOMEHUB_CONTENT WHERE ... LIMIT 100
        
T=1s:   Results arrive (100 items)
        └─ Sends back 100 IDs: [1, 2, 3, ..., 100]
        
T=1.5s: Frontend makes 100 individual detail requests
        ├─ GET /api/content/1
        ├─ GET /api/content/2
        ├─ ...
        ├─ GET /api/content/100
        └─ Results in 100 parallel DB queries!
        
T=2s:   Database load spike
        ├─ Expected: 1 query (already done)
        ├─ Actual: 100 queries hitting database
        ├─ Pool: 20 connections, 80 queries queued
        ├─ Each query: 50-200ms from cache miss
        ├─ Total time: 5-10 seconds
        └─ User sees: 5-10s delay for detail view
        
T=12s:  With 10 concurrent users doing same thing
        ├─ 10 users × 100 detail requests = 1,000 queries
        ├─ Pool: 20 connections, 980 queued
        ├─ Wait time per query: 1,000 ÷ 20 ÷ 10sec = 5 seconds
        ├─ User experience: 15+ seconds to load details
        └─ Appears as system slowdown
```

**Failure Mode: QUERY AMPLIFICATION**
- Single user request triggers hidden N+1 queries
- With 10 concurrent users: 1,000 queries instead of expected 10-20
- Database thrashing from poorly designed API contract
- No error, just slow degradation

**Impact:**
```
If undetected:
- Scales badly: 100 users = 10,000 queries (system collapse)
- Memory: Each queued query holds state (connection, buffers)
- CPU: Query parsing, optimization, execution overhead

Detection clues:
- Database CPU 100% despite low user count
- Query logs: Thousands of identical detail queries
- API latency: Slow response even with cache hits elsewhere
```

---

## 2. FAILURE MODE MATRIX

### What Fails and Why?

```
┌─────────────────────────────────────────────────────────────────┐
│ Failure Mode               │ Symptom           │ Root Cause      │
├─────────────────────────────────────────────────────────────────┤
│ SLOW DEGRADATION          │ p95 latency ↑     │ Queue buildup   │
│                           │ SLA breach        │ Resource pool   │
│                           │ But success ✓     │ exhaustion      │
├─────────────────────────────────────────────────────────────────┤
│ SUDDEN COLLAPSE           │ Error rate ↑ fast │ Hard limit hit  │
│                           │ Timeout wall      │ (connection,    │
│                           │ No recovery       │ memory, thread) │
├─────────────────────────────────────────────────────────────────┤
│ RESOURCE STARVATION       │ Requests queued   │ Worker threads  │
│                           │ blocked waiting   │ all blocked on  │
│                           │ Memory leak       │ I/O (LLM, DB)   │
├─────────────────────────────────────────────────────────────────┤
│ CASCADING FAILURE         │ Retries amplify   │ No circuit      │
│                           │ More failures     │ breaker, retry  │
│                           │ Load increases    │ exponential      │
├─────────────────────────────────────────────────────────────────┤
│ SILENT EXHAUSTION         │ Intermittent      │ Memory/connection│
│                           │ connection reset  │ pool leaks      │
│                           │ No error message  │ Undetected      │
├─────────────────────────────────────────────────────────────────┤
│ CACHE THRASHING           │ Hit rate ↓        │ Cache size too  │
│                           │ Latency ↑         │ small, eviction │
│                           │ More DB queries   │ rate too high   │
└─────────────────────────────────────────────────────────────────┘
```

### Time to Failure

```
Scenario                    │ TFF     │ Recovery Time │ Impact
────────────────────────────┼─────────┼───────────────┼──────────────
100 concurrent searches     │ 5-7s    │ 10-15s        │ SLA breach
Cold cache (100 users)      │ 1-2s    │ 30-60s        │ Collapse
LLM API fails               │ 5s      │ 10-30 min     │ Complete outage
Memory pressure (70 streams)│ 3-5s    │ Process dies  │ Hard restart
Database pool exhaustion    │ 2-3s    │ 15-30s        │ All searches fail
```

---

## 3. BOTTLENECK ANALYSIS

### Critical Bottleneck #1: Database Connection Pool (20 connections)

**Current Spec:**
```
Pool Size: 20 connections
Max Concurrency: 20 simultaneous queries
Queue: Unbounded (grows until OOM or timeout)
```

**Breaking Point:**
```
Capacity: 20 concurrent queries
100 concurrent users (each needs 5 queries):
  - Required: 100 × 5 = 500 connections
  - Available: 20
  - Queue depth: 480
  - Queue latency: 480 ÷ 20 ÷ 10sec = 2.4 seconds average
  
Add 3-5 second query latency:
  - Total per-request latency: 5-7 seconds
  - SLA: 5-7 seconds
  - Result: 50% of requests breach SLA
```

**Failure Progression:**
```
Step 1: Queue builds (0-100ms)
  - All 20 connections in use
  - 80 requests waiting
  
Step 2: Queue timeout (1-2s)
  - Requests waiting timeout
  - Retries add to queue
  
Step 3: Cascade (2-3s)
  - More timeouts than completions
  - Queue grows exponentially
  
Step 4: Collapse (3-5s)
  - New requests immediately timeout
  - System appears broken
```

**Mitigation Options:**
```
Option A: Increase pool size to 50
  - Pro: Handles 50 concurrent users better
  - Con: Database license costs, connection limits
  
Option B: Connection pooling/multiplexing
  - Pro: Many logical connections, fewer physical
  - Con: Complexity, Oracle dialect support
  
Option C: Query optimization
  - Pro: Reduce queries per request (5 → 1-2)
  - Con: Schema redesign, query rewrites
  
Option D: Read replicas
  - Pro: Distribute read-heavy queries
  - Con: Cost, replication lag
```

---

### Critical Bottleneck #2: LLM Circuit Breaker (Single Global Instance)

**Current Spec:**
```
Circuit Breaker: 1 shared instance for all embeddings
Failure threshold: 5 consecutive failures
State transitions: CLOSED → OPEN → HALF_OPEN
Recovery timeout: 5 minutes
```

**Breaking Point:**
```
Scenario: 200 embedding requests (100 searches × 2 embeddings each)

Without failure:
  - LLM throughput: 30-50 embeddings/sec
  - Total time: 200 ÷ 40 = 5 seconds
  - OK: Searches complete in 7-8 seconds
  
With degraded LLM (5s latency):
  - LLM throughput: 1 embedding per 5 seconds = 0.2/sec
  - Total time: 200 ÷ 0.2 = 1,000 seconds!
  - Result: Searches timeout before first response
  
With LLM API failures (50% error rate):
  - 200 requests → 100 fail
  - Circuit breaker: Counts failures across ALL searches
  - After 5 failures: OPENS
  - Result: ALL searches fail (not just those hitting failing API)
  - Recovery: 5 minutes of complete failure
```

**Single Global Point of Failure:**
```
Issue: One circuit breaker for all embedding requests
Problem: Failure in embeddings affects BOTH:
  - Semantic search (needs embeddings)
  - Query expansion (uses embeddings)
  - AI generation (might use embeddings)

If circuit opens:
  - No semantic search possible
  - Fallback to keyword search only
  - AI generation quality degrades
  - Search success rate: 40-60% (depends on fallback)

Recovery dependency:
  - Blocked on LLM API health
  - Can't proceed for 5 minutes (hardcoded timeout)
  - Manual intervention: Delete `.deployed` or restart
```

**Mitigation Options:**
```
Option A: Multiple circuit breakers
  - One per task type (query expansion, embeddings for search, etc.)
  - Pro: Failure isolation
  - Con: Complexity, more state to track
  
Option B: Adaptive circuit breaker
  - Instead of binary OPEN/CLOSED, reduce traffic % by % when degraded
  - Pro: Graceful degradation instead of hard failure
  - Con: More complex logic, harder to reason about
  
Option C: Bulkheads
  - Separate thread pools for each circuit breaker
  - Pro: One failure doesn't starve other operations
  - Con: Thread pool overhead, Python GIL contention
```

---

### Critical Bottleneck #3: Memory Per Concurrent Stream

**Current Spec:**
```
Worker baseline: 200MB
Per-stream overhead: 200KB - 1MB (including response buffer)
Max memory per worker: ~500MB
Workers: 4
Total system memory: 2GB (typical VM)
```

**Breaking Point:**
```
Per worker max concurrent streams:
  - Available: 500MB - 200MB = 300MB
  - Per stream: 1MB (conservative)
  - Max: 300 streams per worker
  - Actual achievable: 100-150 (due to GC overhead, Python internals)

Across 4 workers:
  - Max: 400-600 concurrent streams
  - Reality: System degradation starts at 200-300

With slow network (10Mbps):
  - Each stream takes 5-10 seconds
  - If 50 requests/sec arrive: Queue grows
  - Concurrent count: 50 req/sec × 5 sec = 250 concurrent
  - Memory: 250 × 1MB = 250MB (plus 800MB baseline) = 1.05GB
  - Swap kicks in → Performance degrades 50%+

With OOM:
  - Kernel kills worker process
  - All ~250 streams dropped
  - Cascading failures for other requests
```

**Failure Timeline:**
```
T=0:    System normal, 50 MB free memory
T+1s:   200 requests arrive, 200 streams start
        Memory: 800MB (baseline) + 200MB (streams) = 1GB
        Free: 1GB remaining
T+2s:   Network slow, streams not completing
        Concurrent: Still 150-180 active
        Memory: Stable at 1.05GB
T+3s:   GC pressure increases
        Garbage collection pause: 100-500ms
        User experience: Slow stream responses
T+4s:   Memory pressure > 80%
        Swap usage: 100-200MB
        Performance: Degraded 30-50%
T+5s:   New streams slower to start (memory allocation delay)
        Network still slow, concurrent streams accumulate
        Memory: 1.2GB+ (including swap)
T+6s:   OOMkiller triggered
        Kills worker or entire process
        Result: Abrupt connection reset for all streams
```

**Silent Exhaustion Risk:**
- No error message saying "out of memory"
- Just "connection reset" from client perspective
- Logs might show OOMkiller, but buried in syslog
- Appears intermittent, hard to reproduce

---

### Critical Bottleneck #4: Async Task Queue (Uvicorn Workers)

**Current Spec:**
```
Uvicorn workers: 4
Backlog per worker: ~1000 (OS limit, tunable)
Total backlog: ~4000 requests
```

**Breaking Point:**
```
Request arrival rate: 100 requests/sec
Worker processing rate: 10 requests/sec (slow searches)
Queue buildup: 100 - 10 = 90 requests/sec

Backlog growth:
T=0s:   Backlog: 0
T+1s:   Backlog: 90
T+2s:   Backlog: 180
T+3s:   Backlog: 270
T+4s:   Backlog: 360
T+5s:   Backlog: 450 (getting concerning)
T+10s:  Backlog: 900 (80% of capacity)
T+11s:  Backlog: 990 (exceeds OS default)
T+12s:  New requests: REJECTED (connection refused)
```

**Consequences:**
```
When backlog exceeds capacity:
  - Load balancer gets SYN_RECEIVED (TCP accept queue full)
  - Client sees "Connection refused"
  - Not a timeout, but immediate rejection
  - User experience: "Server down" (not "server slow")
  
When requests finally process:
  - Average wait time: 2-5 seconds
  - Response time: wait + processing
  - Total: 8-15 seconds (vs SLA 5-7)
  - User sees: System is slow
  
If all 4 workers blocked:
  - New requests queued in OS kernel
  - OS queues: 1000-2000 requests (varies by tuning)
  - Total wait: 100-200 seconds for new requests
  - Result: Complete system unavailability
```

---

## 4. WRONG ANSWER SCENARIOS

### When TomeHub Returns Incorrect Results

```
┌──────────────────────────────────────────────────────────────┐
│ Scenario                   │ Cause          │ Detectability  │
├──────────────────────────────────────────────────────────────┤
│ Stale cached answer        │ Cache version  │ Hard (if users │
│ with old prompt result     │ not bumped     │ don't notice) │
│                            │ (Phase 3 fix)  │ Low without    │
│                            │                │ Phase 3        │
├──────────────────────────────────────────────────────────────┤
│ Embedding version changed, │ Model updated  │ Hard (silently │
│ cache key not updated      │ but search key │ returns stale  │
│                            │ unchanged      │ vectors)       │
├──────────────────────────────────────────────────────────────┤
│ Partial/corrupted response │ Stream cut off │ Easy (JSON     │
│ from network timeout       │ mid-response   │ parse error)   │
├──────────────────────────────────────────────────────────────┤
│ LLM circuit open, fallback │ Keyword search │ Detectable     │
│ returns suboptimal results │ only, lower    │ (different     │
│ (keyword-only search)      │ quality        │ result ranking)│
├──────────────────────────────────────────────────────────────┤
│ Database query timeout,    │ Partial result │ Noticeable     │
│ missing 30% of chunks      │ set returned   │ (fewer results)│
├──────────────────────────────────────────────────────────────┤
│ Dual-AI Judge fails, Work  │ No evaluation  │ Hard (low      │
│ AI returns unreviewed      │ of answer      │ quality slips  │
│ low-quality answer         │ quality        │ through)       │
└──────────────────────────────────────────────────────────────┘
```

### Example: Prompt Change Without Version Bump

```
Timeline:

Day 1: Deploy with LLM_MODEL_VERSION=v1
  - Prompt: "Answer as a philosopher"
  - Answer for "What is Dasein?": Ontological perspective
  - Cached with key: ["what is dasein", v1]

Day 2: Change prompt without bumping version
  - Prompt: "Answer as a neuroscientist"
  - But still LLM_MODEL_VERSION=v1 (forgot to bump!)

Day 3: User searches "What is Dasein?"
  - Cache lookup: ["what is dasein", v1]
  - Result: Old cached answer (philosophical)
  - Expected: New answer (neuroscientific)
  - User sees: Wrong perspective, without knowing

  WITH PHASE 3 FIX:
  - Developer must change LLM_MODEL_VERSION=v1 → v2
  - Cache key changes: ["what is dasein", v1] → ["what is dasein", v2]
  - No cache hit
  - New answer generated with new prompt
  - User gets correct (new) answer
```

---

## 5. TIMEOUT SCENARIOS

### What Times Out Under Load?

```
Component               │ Timeout     │ Under Load    │ Impact
────────────────────────┼─────────────┼───────────────┼─────────────
Search endpoint         │ 30s (HTTP)  │ At 5-7s load  │ Early timeout
LLM embedding call      │ 60s         │ At 2-3s       │ Circuit breaks
Database query          │ 30s (Oracle)│ At 1-2s       │ Connection lost
Stream response         │ 60s         │ At 5-10s      │ Connection reset
Cache.get()             │ 5s (Redis)  │ Never        │ Fallback to DB
User sees error         │ SLA: 5-7s   │ Breached      │ Error page shown
```

### Timeout Cascade Under Database Exhaustion

```
T=0s:   Database pool: 20/20 occupied
        New query arrives
        
T=0.1s: Query waits for connection (none available)
        Queue: 1 item
        
T+1s:   No connections freed
        Queue: 100+ items
        New query added to queue
        
T+5s:   Original query finally gets connection
        Executes (200ms)
        
T+5.2s: Query returns, but...
        By now, client timeout expired!
        Client sees: Connection timeout
        Server still processing result
        
T+5.3s: Server finishes, sends result to dead client
        Network sends anyway (wastes bandwidth)
        
Result: Work done, result discarded, users see timeout
```

---

## 6. MITIGATION STRATEGIES

### Short-term (Immediate, <1 day)

```
1. Increase connection pool: 20 → 40
   Cost: Oracle license increase
   Benefit: Handles 100 concurrent searches
   
2. Reduce worker timeouts: 30s → 10s
   Cost: Faster failure detection
   Benefit: Better error messaging, faster retry
   
3. Add request rate limiting: 1000 req/sec → 500 req/sec
   Cost: Some requests rejected
   Benefit: Prevents queue explosion, protects system

4. Monitor Phase 2 (Circuit Breaker) health
   - Check /api/health/circuit-breaker
   - Alert on state change to OPEN
   - Manual recovery if needed (restart app)

5. Monitor Phase 3 (Version Validation)
   - Verify .deployed file exists and is current
   - Alert on version validation failure at startup
```

### Medium-term (1-2 weeks)

```
1. Optimize queries: 5 queries/search → 2 queries/search
   Reduce database load by 60%
   
2. Implement query result caching: 24-hour TTL
   Reduce DB queries further
   
3. Use read replicas for expensive queries
   Distribute load across multiple DB instances
   
4. Implement bulkheads: Separate pools for ingestion vs search
   Prevent one operation starving the other
   
5. Add memory monitoring and alerting
   Alert when memory usage > 70%
   Auto-restart workers if > 85%
```

### Long-term (1-3 months)

```
1. Database query redesign
   - Denormalize some tables
   - Add materialized views for common queries
   - Reduce N+1 queries
   
2. Multiple circuit breakers
   - Separate by operation type
   - Prevent cascading failure
   
3. Implement graceful degradation tiers
   Tier 1: Search with embeddings (full quality)
   Tier 2: Search without embeddings (keyword only)
   Tier 3: Return cached results only
   
4. Dedicated ingestion worker pool
   - Separate from user-facing requests
   - Can be slower without impacting search
   
5. Elasticsearch or similar
   - Offload full-text search from Oracle
   - Much faster for large result sets
```

---

## 7. CURRENT STATE ASSESSMENT

### What Phase 1 (Firebase Auth) Improved

✅ **Security:** Prevents unauthorized API access  
✅ **Accounting:** Tracks which user made which request  
✅ **Rate limiting:** Per-user limits prevent abuse  
✅ **Audit trail:** All requests logged with user context  

⚠️ **Performance:** No impact (middleware < 1ms overhead)  
✅ **Reliability:** Auth failures are fast (1-2ms), not slow

---

### What Phase 2 (Circuit Breaker) Improved

✅ **LLM API resilience:** Prevents cascading failures  
✅ **Fast failure:** 1ms rejection instead of 20s timeout  
✅ **Auto-recovery:** 5-minute timeout, automatic retry  
✅ **Graceful degradation:** Search continues with keywords  

⚠️ **Single point of failure:** One circuit breaker for all embeddings  
⚠️ **Manual recovery:** Restart app if circuit stuck (rare)  

**Impact on Stress Test:**
```
Scenario 1A (100 concurrent searches):
  Without Phase 2: Cascading LLM failures, error rate 30-40%
  With Phase 2: Clean failure at 5 minutes, error rate 5-10%
  
Scenario 2 (LLM degradation):
  Without Phase 2: System appears broken for 10-30 minutes
  With Phase 2: System fails fast, recovers in 5 minutes
```

---

### What Phase 3 (Version Validation) Improved

✅ **Cache safety:** Never reuses stale cached results  
✅ **Deployment safety:** Prevents version mismatch bugs  
✅ **Clear errors:** Startup validation catches mistakes  
✅ **Automatic enforcement:** No manual version tracking  

⚠️ **Doesn't prevent:** Cold cache loads, slow database queries  
⚠️ **Doesn't help:** High-load scenarios (just makes them safer)  

**Impact on Stress Test:**
```
Scenario: "What is Dasein?" search after prompt change
  Without Phase 3: Returns old cached answer (wrong!)
  With Phase 3: Would have prevented code from deploying
                or caught mismatch before cache hit
  
Scenario: Cold cache + load test
  Without Phase 3: Wrong answers possible (unknowable)
  With Phase 3: Answers guaranteed consistent (knowable wrong/right)
```

---

## 8. REMAINING VULNERABILITIES

### Not Covered by Phases 1-3

```
Vulnerability              │ Severity │ Mitigation
───────────────────────────┼──────────┼─────────────────
High concurrency timeout   │ 🔴 HIGH  │ Connection pool ↑
                           │          │ Query optimization
───────────────────────────┼──────────┼─────────────────
Cold cache (Redis down)    │ 🔴 HIGH  │ L1 cache tuning
                           │          │ Query caching
───────────────────────────┼──────────┼─────────────────
Memory exhaustion          │ 🟡 MEDIUM│ Memory limits
                           │          │ Stream backpressure
───────────────────────────┼──────────┼─────────────────
Database replication lag   │ 🟡 MEDIUM│ Read-after-write
                           │          │ Consistency checks
───────────────────────────┼──────────┼─────────────────
N+1 query pattern          │ 🟡 MEDIUM│ API redesign
                           │          │ Batch queries
───────────────────────────┼──────────┼─────────────────
LLM rate limiting          │ 🟠 MEDIUM│ Token bucket
                           │          │ Queueing strategy
───────────────────────────┼──────────┼─────────────────
Ingestion blocking search  │ 🟠 MEDIUM│ Separate pools
                           │          │ Priority queueing
```

---

## 9. FAILURE DECISION TREE

### How to Diagnose System State Under Load

```
Symptom: "Search is slow"
├─ Time: Always slow? Or sudden?
│  ├─ Gradual: Pool exhaustion (increase pool size)
│  └─ Sudden: Cache miss or DB unavailable
├─ Error rate: High? Or just latency?
│  ├─ High errors (>10%): Database or LLM failure
│  └─ Low errors: Just slow, queue buildup
└─ Check: Logs for timeouts, queue depth, connection count

Symptom: "Intermittent connection reset"
├─ Memory usage: Check ps aux | grep python
│  ├─ >1.5GB: OOMkiller likely
│  └─ <1GB: Network issue
├─ Stream count: lsof | grep socket
│  ├─ >500: Too many concurrent streams
│  └─ <100: Network might be slow

Symptom: "Wrong answer returned"
├─ Is cache involved? Check request for 'cache_hit'
│  ├─ Yes: Version mismatch? Check .deployed
│  └─ No: LLM or judge AI issue
├─ Recent code changes? Check git log --oneline -n 20
│  ├─ Yes: Did you bump versions? (Phase 3 check)
│  └─ No: Database issue likely

Symptom: "LLM seems to be down"
├─ Check: GET /api/health/circuit-breaker
│  ├─ state: "open": Circuit open, wait 5 min or restart
│  ├─ state: "half_open": Recovery in progress, wait 30s
│  ├─ state: "closed": Circuit fine, issue elsewhere
└─ If open: Check LLM API health independently
```

---

## 10. FINAL STRESS TEST SUMMARY

### Breaking Points by Load Level

```
Load         │ Latency p95 │ Error Rate │ Failure Mode
─────────────┼─────────────┼────────────┼──────────────────────
10 users     │ 2-3s        │ 0%         │ None
50 users     │ 3-5s        │ 0%         │ None
100 users    │ 5-8s        │ 5-10%      │ Slow degradation
150 users    │ 8-15s       │ 15-25%     │ Gradual collapse
200+ users   │ 20-30s+     │ 40%+       │ Complete failure
```

### What Fails First Under Load

```
1. Database connection pool (20 → 100 needed) [CRITICAL]
   - Timeout: 2-3 seconds after SLA breach
   - Impact: 50% of searches fail

2. LLM circuit breaker (50% error rate on API)
   - Timeout: 5 seconds (queue buildup)
   - Impact: Fallback to keyword search, 50% quality loss

3. Memory on streaming (40+ concurrent streams)
   - Timeout: OOMkiller after 3-5s sustained load
   - Impact: Abrupt connection resets

4. Task queue backlog (Uvicorn)
   - Timeout: New requests rejected after 10 seconds load
   - Impact: "Connection refused" for new users

5. Cache (if Redis down)
   - Timeout: All searches slow (database only)
   - Impact: 5-10x latency increase
```

### Mitigation Priority

```
Priority 1 (Before 100 users):
  ✅ Implement Phase 2 (Circuit Breaker) - DONE
  ✅ Implement Phase 3 (Version Validation) - DONE
  ✅ Implement Phase 1 (Firebase Auth) - DONE
  ⏳ Increase DB pool: 20 → 40 connections
  ⏳ Add memory monitoring and alerting

Priority 2 (Before 500 users):
  ⏳ Query optimization (5 → 2 queries/search)
  ⏳ Implement read replicas
  ⏳ Caching layer for frequent queries

Priority 3 (Before 2000+ users):
  ⏳ Elasticsearch for full-text search
  ⏳ Multiple circuit breakers
  ⏳ Dedicated ingestion worker pool
  ⏳ Database sharding
```

---

## CONCLUSION

**Current State (With Phases 1-3):**
- ✅ Secure (Firebase Auth prevents unauthorized access)
- ✅ Resilient to LLM failures (Circuit breaker + retry logic)
- ✅ Safe from cache bugs (Version validation enforces bumps)
- ⚠️ Can handle ~50-100 concurrent users reliably
- ❌ Breaks under 200+ concurrent users (database bottleneck)

**Biggest Risks (Unfixed):**
1. Database pool exhaustion (CRITICAL)
2. Memory exhaustion under high streaming load (HIGH)
3. Cold cache performance (MEDIUM)
4. Ingestion blocking search operations (MEDIUM)

**Recommended Next Actions:**
1. Load test with 100-200 concurrent users
2. Profile to identify actual bottleneck (likely database)
3. Increase connection pool and measure improvement
4. Implement query optimization to reduce DB load
5. Deploy memory monitoring and alerting
6. Add circuit breaker health checks to monitoring dashboard

---

**Report Generated:** February 2, 2026  
**System:** TomeHub with Phase 1, Phase 2, Phase 3 complete  
**Status:** Production-ready for low-to-moderate load (50-100 concurrent users)  
**Next:** Load testing and database optimization
