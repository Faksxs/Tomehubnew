# Testing Guide for Caching Optimizations

This guide explains how to test the caching and optimization changes we've implemented.

## Prerequisites

1. **Install Dependencies**
   ```bash
   cd apps/backend
   pip install -r requirements.txt
   ```

2. **Set Environment Variables**
   Create or update `.env` file:
   ```bash
   # Required
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_DSN=your_dsn
   GEMINI_API_KEY=your_gemini_key
   
   # Optional (for L2 cache)
   REDIS_URL=redis://localhost:6379/0
   CACHE_ENABLED=true
   CACHE_L1_MAXSIZE=1000
   CACHE_L1_TTL=600
   ```

3. **Start Redis (Optional, for L2 cache)**
   ```bash
   # Using Docker
   docker run -d -p 6379:6379 redis:latest
   
   # Or using local Redis
   redis-server
   ```

## Test Scripts

### 1. Basic Caching Tests

Run comprehensive caching tests:

```bash
cd apps/backend
python scripts/test_caching.py
```

**What it tests:**
- Query normalization
- Cache key generation
- L1 cache (in-memory)
- L2 cache (Redis, if available)
- Multi-layer cache
- Search orchestrator caching
- Query expansion caching

**Expected output:**
```
✓ PASS: Query Normalization
✓ PASS: Cache Key Generation
✓ PASS: L1 Cache
⚠ Redis not available, skipping L2 cache tests
✓ PASS: Multi-Layer Cache
✓ PASS: Search Orchestrator Caching
✓ PASS: Query Expansion Caching

Total: 6/7 tests passed
```

### 2. Cache Invalidation Test

Test that cache is properly invalidated after ingestion:

```bash
python scripts/test_cache_integration.py
```

**What it tests:**
- Cache invalidation on ingestion
- Pattern-based cache deletion
- Cache repopulation after invalidation

### 3. Performance Benchmark

Measure cache performance impact:

```bash
python scripts/test_performance.py
```

**What it tests:**
- Search latency without cache
- Search latency with cache (first vs cached)
- Cache speedup calculation

**Expected output:**
```
📊 Cache Speedup: 10-50x faster for cached queries
✓ Excellent cache performance!
```

## Manual Testing

### Test 1: Verify Cache is Working

1. **Start the backend:**
   ```bash
   cd apps/backend
   python app.py
   # Or with uvicorn
   uvicorn app:app --reload
   ```

2. **Make a search request:**
   ```bash
   curl -X POST http://localhost:5000/api/search \
     -H "Content-Type: application/json" \
     -d '{
       "question": "vicdanın doğası",
       "firebase_uid": "test_user_001"
     }'
   ```

3. **Check logs for cache hit:**
   Look for: `"Cache hit for query: vicdanın doğası..."`

4. **Make the same request again:**
   The second request should be much faster and show a cache hit in logs.

### Test 2: Verify Cache Invalidation

1. **Perform a search** (creates cache entry)

2. **Ingest a new book:**
   ```bash
   curl -X POST http://localhost:5000/api/ingest \
     -F "file=@test_book.pdf" \
     -F "title=Test Book" \
     -F "author=Test Author" \
     -F "firebase_uid=test_user_001"
   ```

3. **Check logs for cache invalidation:**
   Look for: `"Cache invalidated for user test_user_001"`

4. **Perform the same search again:**
   Should compute fresh results (not from cache)

### Test 3: Test Database Pool

1. **Check database pool initialization:**
   Look for in logs: `"Database Pool initialized successfully"`
   Should show: `max=20` (instead of 10)

2. **Test concurrent requests:**
   ```bash
   # Run multiple searches in parallel
   for i in {1..5}; do
     curl -X POST http://localhost:5000/api/search \
       -H "Content-Type: application/json" \
       -d "{\"question\": \"test query $i\", \"firebase_uid\": \"user$i\"}" &
   done
   wait
   ```

3. **Check for connection errors:**
   Should not see "Database pool exhausted" errors

## API Endpoint Testing

### Test Cache Status (Optional - Add this endpoint)

You can add a simple endpoint to check cache status:

```python
# In app.py
@app.get("/api/cache/status")
async def cache_status():
    from services.cache_service import get_cache
    cache = get_cache()
    
    if not cache:
        return {"status": "disabled"}
    
    return {
        "status": "enabled",
        "l1_size": cache.l1.size(),
        "l2_available": cache.l2.is_available()
    }
```

Then test:
```bash
curl http://localhost:5000/api/cache/status
```

## Expected Performance Improvements

After implementing caching, you should see:

1. **First Request (Cache Miss):**
   - Latency: ~700-3500ms (normal)
   - Cache: Computes and stores

2. **Subsequent Requests (Cache Hit):**
   - Latency: ~10-50ms (80-95% reduction)
   - Cache: Returns from L1 or L2

3. **Query Expansion:**
   - First: ~500-2000ms (LLM call)
   - Cached: ~1-5ms (99% reduction)

4. **Database Pool:**
   - Can handle 2x more concurrent requests
   - No connection timeout errors under normal load

## Troubleshooting

### Cache Not Working

1. **Check if cache is enabled:**
   ```bash
   echo $CACHE_ENABLED  # Should be "true"
   ```

2. **Check Redis connection (if using L2):**
   ```bash
   redis-cli ping  # Should return "PONG"
   ```

3. **Check logs for errors:**
   Look for: `"Cache initialization failed"` or `"Redis connection failed"`

### Cache Hit Rate Low

1. **Check query normalization:**
   - Queries with different formatting should normalize to same key
   - Test with: `normalize_query("  Test  Query  ")`

2. **Check cache key generation:**
   - Same query + user should generate same key
   - Different users should generate different keys

3. **Check TTL settings:**
   - Search results: 1 hour
   - Query expansions: 7 days

### Database Pool Issues

1. **Check pool size:**
   - Should be `max=20` in logs
   - Check `db_manager.py` line 39

2. **Monitor pool utilization:**
   - Add logging to track `pool.busy / pool.max`
   - Should stay below 80% under normal load

## Next Steps

After verifying these tests pass:

1. **Monitor in production:**
   - Track cache hit rates
   - Monitor search latency (p50, p95, p99)
   - Track database pool utilization

2. **Optimize further:**
   - Adjust TTL values based on usage patterns
   - Increase L1 cache size if memory allows
   - Add Redis if not already using it

3. **Implement Priority 2 optimizations:**
   - Parallel query expansion
   - Smart reranking skip
   - Intent classification caching
