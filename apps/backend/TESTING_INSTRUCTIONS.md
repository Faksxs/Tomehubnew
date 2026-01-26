# Testing Instructions for Optimizations

## Quick Start

### Step 1: Install Dependencies

```bash
cd apps/backend
pip install -r requirements.txt
```

This will install:
- `cachetools>=5.3.0` (for L1 cache)
- `redis>=5.0.0` (for L2 cache, optional)

### Step 2: Verify Code Changes

```bash
python scripts/verify_optimizations.py
```

This checks if all optimizations are in place without requiring a full system setup.

### Step 3: Set Up Environment (Optional)

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

### Step 4: Start Redis (Optional, for L2 cache)

```bash
# Using Docker
docker run -d -p 6379:6379 redis:latest

# Or using local Redis
redis-server
```

### Step 5: Run Tests

#### Option A: Quick Verification (No DB/API required)
```bash
python scripts/verify_optimizations.py
```

#### Option B: Full Cache Tests (Requires DB connection)
```bash
python scripts/test_caching.py
```

#### Option C: Performance Comparison (Requires DB + API)
```bash
python scripts/performance_comparison.py
```

#### Option D: Comprehensive Tests (All features)
```bash
python scripts/test_all_optimizations.py
```

## What Each Test Does

### `verify_optimizations.py`
- **Purpose:** Code verification only
- **Requirements:** None (just checks files)
- **Time:** < 1 second
- **Use when:** You want to quickly verify changes are in place

### `test_caching.py`
- **Purpose:** Test cache functionality
- **Requirements:** Database connection
- **Time:** ~10-30 seconds
- **Use when:** You want to test cache behavior

### `performance_comparison.py`
- **Purpose:** Measure performance improvements
- **Requirements:** Database + API keys
- **Time:** ~30-60 seconds
- **Use when:** You want to see actual performance gains

### `test_all_optimizations.py`
- **Purpose:** Comprehensive test suite
- **Requirements:** Full system setup
- **Time:** ~1-2 minutes
- **Use when:** You want to test everything

## Expected Results

### Verification Script
```
✅ All optimizations are in place!
```

### Cache Tests
```
✓ PASS: Query Normalization
✓ PASS: Cache Key Generation
✓ PASS: L1 Cache
✓ PASS: Multi-Layer Cache
✓ PASS: Search Orchestrator Caching
```

### Performance Comparison
```
📊 Cache Impact:
  First run improvement: 0-20% faster
  Cached run improvement: 80-95% faster (10-50x speedup)
```

## Manual Testing

### Test 1: Cache Status Endpoint

Start the backend:
```bash
python app.py
# Or: uvicorn app:app --reload
```

Check cache status:
```bash
curl http://localhost:5000/api/cache/status
```

Expected response:
```json
{
  "status": "enabled",
  "l1": {
    "size": 0,
    "maxsize": 1000,
    "ttl": 600
  },
  "l2": {
    "available": true,
    "type": "redis"
  }
}
```

### Test 2: Search with Cache

First request (cache miss):
```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"question": "vicdanın doğası", "firebase_uid": "test_user_001"}'
```

Check logs for:
- `"Cache hit for query: vicdanın doğası..."` (should NOT appear on first call)
- `"Cached search results for key: ..."` (should appear)

Second request (cache hit):
```bash
# Same command as above
```

Check logs for:
- `"Cache hit for query: vicdanın doğası..."` (should appear)
- Much faster response time

### Test 3: Database Pool

Check logs when backend starts:
```
Database Pool initialized successfully.
```

Should show `max=20` in the pool configuration.

## Troubleshooting

### "ModuleNotFoundError: No module named 'cachetools'"

**Solution:**
```bash
pip install cachetools redis
```

### "Redis connection failed"

**Solution:**
- Redis is optional - L1 cache will still work
- To enable L2 cache: Start Redis or set `REDIS_URL` in `.env`

### "Database Pool not initialized"

**Solution:**
- Make sure `.env` has correct database credentials
- Check that `DatabaseManager.init_pool()` is called in `app.py` lifespan

### Cache not working

**Check:**
1. Is `CACHE_ENABLED=true` in `.env`?
2. Are cache dependencies installed?
3. Check logs for cache initialization messages

## Performance Metrics to Monitor

After testing, monitor these metrics:

1. **Cache Hit Rate:**
   - Target: >80%
   - Check: Log messages showing "Cache hit"

2. **Search Latency:**
   - Cached queries: <50ms (target)
   - Uncached queries: 700-3500ms (baseline)

3. **Database Pool Utilization:**
   - Should stay below 80% under normal load
   - Check: Pool busy connections / max connections

4. **Reranking Skip Rate:**
   - Target: 30-50% of queries skip reranking
   - Check: Log messages "Skipping reranking"

## Next Steps After Testing

1. **If tests pass:**
   - Deploy to staging environment
   - Monitor performance metrics
   - Proceed to Priority 3 optimizations (if needed)

2. **If tests fail:**
   - Review error messages
   - Check dependencies are installed
   - Verify environment variables are set
   - Check database connectivity

3. **Performance tuning:**
   - Adjust cache TTL based on usage patterns
   - Increase L1 cache size if memory allows
   - Add Redis for L2 cache if not already using it
