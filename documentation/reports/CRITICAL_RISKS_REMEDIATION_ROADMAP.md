# Critical Risks Remediation Roadmap

**Created:** February 2, 2026  
**Target:** Production-ready authentication, data integrity, and observability  
**Timeline:** 2-3 weeks (if full-time)

---

## Executive Summary

Three critical risks threaten production deployment:

| Risk | Blast Radius | Fix Complexity | Time |
|------|--------------|-----------------|------|
| Firebase auth bypass | Data leakage (multi-tenant) | Medium | 4 hours |
| Embedding API silent failures | Wrong answers (undetected) | Medium | 2-3 hours |
| Model version cache miss | Stale cached decisions | Low | 1 hour |

**Recommended sequence:** Auth → Embeddings → Cache (dependency-ordered)

---

## PHASE 1: Fix Firebase Authentication (Days 1-2)

### 1.1 Root Cause Summary
Current `middleware/auth_middleware.py` has:
- ❌ No real JWT validation ("TEMPORARY" comment, active code)
- ❌ Returns `None` → request body `firebase_uid` trusted
- ❌ No dev/prod differentiation
- ❌ Attackers can inject arbitrary UIDs

### 1.2 Solution Architecture

```
Flows:
┌─ PRODUCTION ─────────────────────────────┐
│ Client sends Authorization: Bearer <JWT> │
│         ↓                                 │
│ Firebase Admin SDK verifies JWT         │
│         ↓                                 │
│ Extract firebase_uid from decoded token │
│         ↓                                 │
│ Route handler uses verified UID         │
└────────────────────────────────────────────┘

┌─ DEVELOPMENT (explicit fallback) ─────────┐
│ If ENVIRONMENT=development & Firebase off │
│ Log warning: "DEV MODE - no auth check"   │
│ Route can opt-in to request body UID     │
└───────────────────────────────────────────┘
```

### 1.3 Implementation Steps

**Step 1.3.1: Set up Firebase Admin SDK (0.5 hours)**

Prerequisite: User must provide service account JSON key

**Action items:**
1. User adds `GOOGLE_APPLICATION_CREDENTIALS=/path/to/serviceAccountKey.json` to `.env`
2. Or: User uploads key to `apps/backend/firebase-adminsdk.json`
3. Code detects and loads key automatically

**Step 1.3.2: Rewrite auth_middleware.py (1.5 hours)**

Replace current logic:
```python
# OLD (app.py currently imports this)
from middleware.auth_middleware import verify_firebase_token

# NEW: Proper implementation with dev mode
async def verify_firebase_token(request: Request) -> str:
    """
    Verify Firebase JWT.
    
    Production: Real JWT validation
    Development: Request-body UID (UNSAFE, logged)
    
    Returns: firebase_uid (verified or from request body in dev)
    Raises: HTTPException 401/403 on failure
    """
    # 1. Extract Authorization header
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    # 2. Parse Bearer token
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    token = parts[1]
    
    # 3. Verify JWT based on environment
    if os.getenv("ENVIRONMENT") == "development" and os.getenv("FIREBASE_ADMIN_SDK_MISSING"):
        # DEV MODE: Accept request body UID with warning
        logger.warning("⚠️ DEVELOPMENT MODE: Firebase Admin SDK not configured. Using request body UID (INSECURE).")
        # Let route handler extract UID from request body
        return None  # Signal: use request body
    
    # 4. PRODUCTION: Real verification
    try:
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        
        if not uid:
            logger.error(f"Firebase token missing 'uid' claim")
            raise HTTPException(status_code=401, detail="Invalid token claims")
        
        logger.info(f"✓ Firebase JWT verified for UID: {uid}")
        return uid
        
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except auth.InvalidIdTokenError as e:
        logger.warning(f"Invalid Firebase token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Firebase verification failed: {e}")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")
```

**Step 1.3.3: Update config.py (0.5 hours)**

Add environment validation:
```python
# config.py
import os
import firebase_admin
from firebase_admin import credentials

class Settings:
    def __init__(self):
        # ... existing settings ...
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        
        # Try to initialize Firebase Admin SDK
        self._init_firebase()
    
    def _init_firebase(self):
        """Initialize Firebase Admin SDK if credentials available."""
        if firebase_admin._apps:  # Already initialized
            return
        
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if cred_path and os.path.exists(cred_path):
            try:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                logger.info("✓ Firebase Admin SDK initialized")
                self.FIREBASE_READY = True
            except Exception as e:
                logger.error(f"Firebase init failed: {e}")
                self.FIREBASE_READY = False
        else:
            if self.ENVIRONMENT == "production":
                raise ValueError(
                    "CRITICAL: GOOGLE_APPLICATION_CREDENTIALS not set. "
                    "Firebase Auth is required for production."
                )
            logger.warning("Firebase Admin SDK credentials not found (OK for local dev)")
            self.FIREBASE_READY = False
```

**Step 1.3.4: Update app.py lifespan (1 hour)**

Verify auth on startup:
```python
# app.py lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Startup: Initializing TomeHub API...")
    
    # 1. Check Firebase Auth
    if settings.ENVIRONMENT == "production":
        if not settings.FIREBASE_READY:
            raise RuntimeError(
                "CRITICAL: Firebase Admin SDK not initialized. "
                "Set GOOGLE_APPLICATION_CREDENTIALS and ENVIRONMENT=production"
            )
        logger.info("✓ Firebase Auth ready for production")
    else:
        logger.warning("⚠️ Running in DEVELOPMENT mode. Firebase auth may be bypassed.")
    
    # 2. Init DB Pool
    DatabaseManager.init_pool()
    logger.info("✓ Database pool initialized (max=20 connections)")
    
    # 3. Init Cache
    if settings.CACHE_ENABLED:
        from services.cache_service import init_cache
        cache = init_cache(...)
        app.state.cache = cache
        logger.info("✓ Cache initialized")
    
    yield
    
    logger.info("🛑 Shutdown: Closing DB Pool...")
    DatabaseManager.close_pool()
```

**Step 1.3.5: Route Updates (0.5 hours)**

Update routes to handle auth result:

```python
# Example route in app.py or routes/

@app.post("/api/search")
async def search_route(
    request: SearchRequest,
    firebase_uid_from_jwt: str = Depends(verify_firebase_token)
) -> SearchResponse:
    """
    Search endpoint with verified Firebase UID.
    
    If firebase_uid_from_jwt is None (dev mode):
        Use request.firebase_uid (FROM REQUEST BODY)
        Log warning that this is insecure
    
    If firebase_uid_from_jwt is str (production):
        Use verified UID (IGNORE request body)
    """
    
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        # Production: JWT is authoritative
        firebase_uid = firebase_uid_from_jwt
        logger.info(f"Using JWT-verified UID: {firebase_uid}")
    else:
        # Dev mode: Use request body (with warning)
        firebase_uid = request.firebase_uid
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            logger.error("SECURITY: Auth failed but ENVIRONMENT != development. Rejecting request.")
            raise HTTPException(status_code=401, detail="Auth failed")
    
    # Rest of handler uses verified firebase_uid
    # ... search logic ...
```

### 1.4 Testing & Validation

**Test 1.4.1: Auth Success (Production)**
```bash
# With valid JWT
curl -X POST http://localhost:5000/api/search \
  -H "Authorization: Bearer <valid_jwt_token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'

# Expected: 200 OK, answer returned
# Log: "✓ Firebase JWT verified for UID: xyz"
```

**Test 1.4.2: Auth Failure (Invalid JWT)**
```bash
curl -X POST http://localhost:5000/api/search \
  -H "Authorization: Bearer invalid_token" \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}'

# Expected: 401 Unauthorized
# Log: "Invalid Firebase token"
```

**Test 1.4.3: Auth Bypass Attempt (Production)**
```bash
# Try to inject UID in request body (should be ignored in production)
curl -X POST http://localhost:5000/api/search \
  -H "Authorization: Bearer <valid_jwt_for_user_a>" \
  -H "Content-Type: application/json" \
  -d '{"question": "test", "firebase_uid": "user_b_id"}'

# Expected: Request processed as user_a (from JWT), not user_b
# Log: "Using JWT-verified UID: user_a_id"
```

**Test 1.4.4: Dev Mode**
```bash
# Set ENVIRONMENT=development
export ENVIRONMENT=development
python app.py

# Auth still required (won't be bypassed)
# But errors won't crash server
```

### 1.5 Rollout Plan

**Phase 1.5.1: Pre-deployment**
- [ ] User provides Firebase service account JSON key
- [ ] Add to `.env`: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json`
- [ ] Code review of auth_middleware.py changes
- [ ] Test on staging with real Firebase project

**Phase 1.5.2: Deployment**
- [ ] Deploy code to production with `ENVIRONMENT=production`
- [ ] Monitor logs for auth errors (1st hour)
- [ ] Alert: If any 401 errors in first 10 minutes, rollback

**Phase 1.5.3: Post-deployment**
- [ ] Audit all existing sessions (check if any cross-UID access)
- [ ] Update frontend to always send valid JWT
- [ ] Remove any "test" or "mock" JWT patterns from codebase

---

## PHASE 2: Add Embedding Failure Observability (Days 2-3)

### 2.1 Root Cause Summary
- ❌ `get_embedding()` catches exceptions, prints to stdout, returns `None`
- ❌ No circuit breaker: keeps retrying broken API
- ❌ No metrics: can't detect "silent embedding failures"
- ❌ Semantic search quietly disabled when embeddings fail

### 2.2 Solution Architecture

```
┌─ Embedding Request ────────────────────┐
│ text → get_embedding(text)             │
│         ↓                               │
│    Try Gemini API (20s timeout)        │
│         ↓                               │
│    Success: Return array.array(768)    │
│    Failure: ↓                          │
│   - Track in metrics (prometheus)      │
│   - Log with context (type of error)   │
│   - Return None                        │
│   - Circuit breaker marks API as DOWN  │
└───────────────────────────────────────┘

┌─ Circuit Breaker Logic ────────────────┐
│ Track: 5 consecutive failures          │
│ Action: Stop calling API for 5 minutes │
│ Callers get instant error (not 20s)    │
│ Recovery: Auto-retry after 5m          │
└───────────────────────────────────────┘

┌─ Caller Fallback ──────────────────────┐
│ Search failed with circuit break       │
│ Fallback: Use ExactMatch + LemmaMatch  │
│ Log warning: "Semantic search disabled"│
└───────────────────────────────────────┘
```

### 2.3 Implementation Steps

**Step 2.3.1: Install dependencies (0.25 hours)**

```bash
cd apps/backend
pip install pybreaker prometheus-client
# Update requirements.txt with:
# - pybreaker>=0.7.0
# - prometheus-client>=0.21.0
```

**Step 2.3.2: Create embedding_circuit.py (1 hour)**

New file: `services/embedding_circuit.py`

```python
import time
import logging
from typing import Optional
import array
from pybreaker import CircuitBreaker
from prometheus_client import Counter, Histogram
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Metrics
embedding_success = Counter(
    'embedding_api_calls_success_total',
    'Total successful embedding API calls'
)

embedding_failures = Counter(
    'embedding_api_calls_failure_total',
    'Total embedding API call failures',
    ['error_type']
)

embedding_latency = Histogram(
    'embedding_api_latency_ms',
    'Embedding API latency in milliseconds',
    buckets=[100, 500, 1000, 2000, 5000, 10000, 20000]
)

embedding_circuit_breaks = Counter(
    'embedding_circuit_breaker_open_total',
    'Total times circuit breaker opened'
)

# Circuit Breaker: Fail after 5 consecutive failures, recover after 5 minutes
embedding_breaker = CircuitBreaker(
    fail_max=5,
    reset_timeout=300,  # 5 minutes
    listeners=[],
    name="embedding_api"
)

class EmbeddingCircuitBreaker:
    """Wrapper around Gemini embedding API with circuit breaker pattern."""
    
    @staticmethod
    @embedding_breaker
    def _call_gemini(text: str, task_type: str = "retrieval_document") -> Optional[list]:
        """Raw call to Gemini embedding API."""
        start_time = time.time()
        
        try:
            result = genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type=task_type,
                request_options={'timeout': 20}
            )
            
            latency = (time.time() - start_time) * 1000
            embedding_latency.observe(latency)
            embedding_success.inc()
            
            # Extract embedding
            if isinstance(result, dict):
                embedding_list = result.get('embedding')
            elif hasattr(result, 'embedding'):
                embedding_list = result.embedding
            else:
                embedding_list = None
            
            if not embedding_list or len(embedding_list) != 768:
                logger.error(f"Invalid embedding dimensions: {len(embedding_list) if embedding_list else 'None'}")
                embedding_failures.labels(error_type='invalid_dimensions').inc()
                return None
            
            return embedding_list
            
        except TimeoutError as e:
            embedding_failures.labels(error_type='timeout').inc()
            logger.error(f"Embedding API timeout: {e}")
            raise
        except Exception as e:
            embedding_failures.labels(error_type=type(e).__name__).inc()
            logger.error(f"Embedding API error ({type(e).__name__}): {e}")
            raise
    
    @staticmethod
    def get_embedding(text: str) -> Optional[array.array]:
        """
        Generate embedding with circuit breaker protection.
        
        Returns: array.array(768) or None
        """
        if not text or not isinstance(text, str):
            logger.error("Invalid input: text must be non-empty string")
            return None
        
        try:
            # This call is protected by circuit breaker
            embedding_list = EmbeddingCircuitBreaker._call_gemini(text)
            
            if embedding_list:
                return array.array("f", embedding_list)
            return None
            
        except CircuitBreaker.CircuitBreakerListenerException as e:
            # Circuit is OPEN - fail fast
            embedding_circuit_breaks.inc()
            logger.error(f"⚠️ Embedding API circuit breaker OPEN: {e}")
            logger.error("Embedding service unavailable. Searches will use keyword matching only.")
            return None
        except Exception as e:
            logger.error(f"Unexpected embedding error: {e}")
            return None
    
    @staticmethod
    def get_query_embedding(text: str) -> Optional[array.array]:
        """Embedding optimized for query retrieval."""
        if not text:
            logger.error("Invalid input: text must be non-empty string")
            return None
        
        try:
            embedding_list = EmbeddingCircuitBreaker._call_gemini(text, task_type="retrieval_query")
            
            if embedding_list:
                return array.array("f", embedding_list)
            return None
            
        except CircuitBreaker.CircuitBreakerListenerException as e:
            embedding_circuit_breaks.inc()
            logger.error(f"⚠️ Query embedding circuit breaker OPEN: {e}")
            return None
        except Exception as e:
            logger.error(f"Query embedding error: {e}")
            return None
```

**Step 2.3.3: Update services to use circuit breaker (0.5 hours)**

Replace imports in all files that call `get_embedding()`:

```python
# OLD: from services.embedding_service import get_embedding
# NEW:
from services.embedding_circuit import EmbeddingCircuitBreaker

# OLD: embedding = get_embedding(text)
# NEW:
embedding = EmbeddingCircuitBreaker.get_embedding(text)

# OLD: embedding = get_query_embedding(text)
# NEW:
embedding = EmbeddingCircuitBreaker.get_query_embedding(text)
```

Files to update:
- `services/search_service.py` (multiple calls)
- `services/ingestion_service.py` (batch embeddings)
- `services/flow_service.py` (_resolve_anchor)
- `services/embedding_service.py` (keep as-is for compatibility, but deprecate)

**Step 2.3.4: Add Prometheus metrics endpoint (0.25 hours)**

Already done if Prometheus instrumentation is enabled in `app.py`. Verify:

```python
# app.py should have:
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Verify by accessing:
# http://localhost:5000/metrics
# Should show: embedding_api_calls_failure_total, embedding_circuit_breaker_open_total, etc.
```

**Step 2.3.5: Add alerting configuration (0.5 hours)**

If Prometheus is deployed, add alerts:

```yaml
# prometheus/alerts.yml (or Grafana alert rule)

- alert: EmbeddingAPIErrors
  expr: rate(embedding_api_calls_failure_total[5m]) > 0.1  # >10% error rate
  for: 5m
  annotations:
    summary: "Embedding API error rate high"
    description: "{{ $value }} failures per second in last 5 minutes"

- alert: EmbeddingCircuitBreakerOpen
  expr: increase(embedding_circuit_breaker_open_total[1m]) > 0
  for: 1m
  annotations:
    summary: "⚠️ Embedding API circuit breaker OPEN"
    description: "Circuit breaker opened. Semantic search disabled."
```

### 2.4 Testing & Validation

**Test 2.4.1: Success path**
```python
# In test_embedding_circuit.py
from services.embedding_circuit import EmbeddingCircuitBreaker

embedding = EmbeddingCircuitBreaker.get_embedding("test text")
assert embedding is not None
assert len(embedding) == 768
# Check metrics: embedding_api_calls_success_total should increment
```

**Test 2.4.2: Circuit breaker on repeated failures**
```python
# Mock genai.embed_content to fail
import unittest.mock as mock

with mock.patch('google.generativeai.embed_content', side_effect=TimeoutError):
    for i in range(6):  # 6 calls (fail_max=5)
        embedding = EmbeddingCircuitBreaker.get_embedding("test")
        if i < 5:
            assert embedding is None  # Failed but circuit not open yet
        else:
            # Circuit should be open now
            assert embedding is None
            # Check metric: embedding_circuit_breaker_open_total incremented
```

**Test 2.4.3: Circuit breaker recovery**
```python
# After 5 minutes (simulated), circuit should try to recover
time.sleep(300 + 10)  # 5 minutes + buffer
embedding = EmbeddingCircuitBreaker.get_embedding("test")
# Should attempt API call again (may fail if API still down)
```

**Test 2.4.4: Fallback to keyword search**
```python
# Test that search still works when embeddings fail
# Search orchestrator should log: "Semantic search disabled"
# And return results from ExactMatch + LemmaMatch only
```

### 2.5 Rollout Plan

**Phase 2.5.1: Pre-deployment**
- [ ] Code review of embedding_circuit.py
- [ ] Run test suite
- [ ] Deploy to staging, test with real Gemini API
- [ ] Verify metrics appear in Prometheus/Grafana

**Phase 2.5.2: Deployment**
- [ ] Deploy to production
- [ ] Monitor dashboard: `embedding_api_calls_failure_total` should be ~0
- [ ] Set alert threshold (e.g., >10% error rate in 5 minutes)

**Phase 2.5.3: Post-deployment**
- [ ] Document circuit breaker behavior in runbooks
- [ ] Alert on-call: "If embedding_circuit_breaker_open, check Gemini API status"

---

## PHASE 3: Enforce Model Version Bumps (Day 3)

### 3.1 Root Cause Summary
- ❌ Developer can forget to bump `LLM_MODEL_VERSION` or `EMBEDDING_MODEL_VERSION`
- ❌ Old cached results reused with new prompts → stale decisions
- ❌ No automated check on deployment

### 3.2 Solution Architecture

```
┌─ On Startup ──────────────────────────┐
│ Load .env variables                   │
│ Check LLM_MODEL_VERSION is newer      │
│ Check EMBEDDING_MODEL_VERSION         │
│ Compare to last deployed version      │
│         ↓                              │
│ If NOT newer: FAIL WITH ERROR         │
│ If newer: Continue                    │
└───────────────────────────────────────┘
```

### 3.3 Implementation Steps

**Step 3.3.1: Add version tracking to config.py (0.5 hours)**

```python
# config.py

import re

class Settings:
    def __init__(self):
        # ... existing code ...
        
        self.LLM_MODEL_VERSION = os.getenv("LLM_MODEL_VERSION", "v1")
        self.EMBEDDING_MODEL_VERSION = os.getenv("EMBEDDING_MODEL_VERSION", "v2")
        
        # Validate versions on startup
        self._validate_model_versions()
    
    def _validate_model_versions(self):
        """
        Ensure model versions are properly formatted and updated.
        
        Prevents cache invalidation bugs by requiring explicit version bumps.
        """
        # Load last deployed versions from .deployed file (optional)
        last_deployed = self._load_last_deployed_versions()
        
        # Validate format (v1, v2, v1.0.1, etc.)
        if not re.match(r'^v\d+(\.\d+)*$', self.LLM_MODEL_VERSION):
            raise ValueError(
                f"Invalid LLM_MODEL_VERSION format: {self.LLM_MODEL_VERSION}. "
                f"Use format: v1, v2, v1.0.1, etc."
            )
        
        if not re.match(r'^v\d+(\.\d+)*$', self.EMBEDDING_MODEL_VERSION):
            raise ValueError(
                f"Invalid EMBEDDING_MODEL_VERSION format: {self.EMBEDDING_MODEL_VERSION}. "
                f"Use format: v1, v2, v1.0.1, etc."
            )
        
        # If versions were deployed before, check they're newer
        if last_deployed:
            if self._compare_versions(self.LLM_MODEL_VERSION, last_deployed.get('llm')) <= 0:
                raise ValueError(
                    f"LLM_MODEL_VERSION must be newer than last deployed: {last_deployed.get('llm')}. "
                    f"Current: {self.LLM_MODEL_VERSION}. "
                    f"Suggestion: Increment to v{self._next_version(last_deployed.get('llm'))}"
                )
            
            if self._compare_versions(self.EMBEDDING_MODEL_VERSION, last_deployed.get('embedding')) <= 0:
                raise ValueError(
                    f"EMBEDDING_MODEL_VERSION must be newer than last deployed: {last_deployed.get('embedding')}. "
                    f"Current: {self.EMBEDDING_MODEL_VERSION}. "
                    f"Suggestion: Increment to v{self._next_version(last_deployed.get('embedding'))}"
                )
    
    def _load_last_deployed_versions(self):
        """Load versions from .deployed file (created on successful deploy)."""
        deployed_file = os.path.join(os.path.dirname(__file__), '.deployed')
        if os.path.exists(deployed_file):
            try:
                import json
                with open(deployed_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not read .deployed file: {e}")
        return None
    
    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """
        Compare two version strings.
        Returns: >0 if v1 > v2, <0 if v1 < v2, 0 if equal
        """
        def parse(v):
            return [int(x) for x in v.lstrip('v').split('.')]
        
        parts1 = parse(v1)
        parts2 = parse(v2)
        
        # Pad with zeros
        max_len = max(len(parts1), len(parts2))
        parts1 += [0] * (max_len - len(parts1))
        parts2 += [0] * (max_len - len(parts2))
        
        if parts1 > parts2:
            return 1
        elif parts1 < parts2:
            return -1
        else:
            return 0
    
    @staticmethod
    def _next_version(current: str) -> str:
        """Suggest next version number."""
        if not current:
            return "v2"
        
        parts = current.lstrip('v').split('.')
        parts[0] = str(int(parts[0]) + 1)
        return 'v' + '.'.join(parts)
```

**Step 3.3.2: Record versions on successful deployment (0.25 hours)**

Add to `.github/workflows/deploy.yml` or deployment script:

```bash
#!/bin/bash
# deploy.sh

# ... deploy code ...

# On successful deployment, record versions
cat > apps/backend/.deployed <<EOF
{
  "llm": "$(grep LLM_MODEL_VERSION .env | cut -d= -f2)",
  "embedding": "$(grep EMBEDDING_MODEL_VERSION .env | cut -d= -f2)",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "commit": "$(git rev-parse --short HEAD)"
}
EOF

echo "✓ Versions recorded: $(cat apps/backend/.deployed)"
```

**Step 3.3.3: Add startup validation to app.py (0.25 hours)**

```python
# app.py lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Startup: Validating configuration...")
    
    # This will raise ValueError if versions are invalid
    try:
        settings._validate_model_versions()
        logger.info(f"✓ Model versions validated: LLM={settings.LLM_MODEL_VERSION}, Embedding={settings.EMBEDDING_MODEL_VERSION}")
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        raise
    
    # ... rest of startup ...
```

### 3.4 Testing & Validation

**Test 3.4.1: Version validation on startup**
```python
# In test_config.py

from config import Settings
import os

def test_valid_versions():
    os.environ["LLM_MODEL_VERSION"] = "v2"
    os.environ["EMBEDDING_MODEL_VERSION"] = "v3"
    settings = Settings()
    assert settings.LLM_MODEL_VERSION == "v2"
    # Should not raise

def test_invalid_version_format():
    os.environ["LLM_MODEL_VERSION"] = "invalid"
    with pytest.raises(ValueError):
        settings = Settings()

def test_version_not_bumped():
    # Simulate .deployed file with v1
    # Try to start with LLM_MODEL_VERSION=v1
    # Should raise error
    pass
```

**Test 3.4.2: Version comparison**
```python
assert Settings._compare_versions("v2", "v1") > 0
assert Settings._compare_versions("v1", "v2") < 0
assert Settings._compare_versions("v1", "v1") == 0
assert Settings._compare_versions("v1.0.1", "v1.0.0") > 0
```

### 3.5 Rollout Plan

**Phase 3.5.1: Pre-deployment**
- [ ] Update `.env` with bumped versions (e.g., LLM_MODEL_VERSION=v2)
- [ ] Test locally: `python app.py` should succeed with new versions
- [ ] Code review of config.py changes

**Phase 3.5.2: Deployment**
- [ ] Deploy with updated `.env`
- [ ] Verify `.deployed` file is created on successful deployment
- [ ] Check logs: "✓ Model versions validated"

**Phase 3.5.3: Post-deployment**
- [ ] Document in runbooks: "Always bump model versions in .env before deploying"
- [ ] Add pre-deployment checklist: "Have you updated LLM_MODEL_VERSION?"

---

## CONSOLIDATED TIMELINE

```
Day 1 (Phase 1 - Firebase Auth):
├─ 08:00 - 08:30: Gather Firebase service account key from user
├─ 08:30 - 10:00: Implement auth_middleware.py rewrite
├─ 10:00 - 10:30: Update config.py and app.py lifespan
├─ 10:30 - 11:30: Update routes to use verified UID
├─ 11:30 - 12:30: Testing (local + staging)
└─ 13:00 - 14:00: Deploy to production + monitoring

Day 2 (Phase 2 - Embedding Circuit Breaker):
├─ 08:00 - 08:15: pip install pybreaker + prometheus-client
├─ 08:15 - 09:15: Create embedding_circuit.py
├─ 09:15 - 09:45: Update all imports to use circuit breaker
├─ 09:45 - 10:15: Verify Prometheus metrics
├─ 10:15 - 11:00: Testing (mock failures + circuit breaker)
├─ 11:00 - 12:00: Deploy to production + alert setup
└─ 12:00 - 13:00: Monitoring + documentation

Day 3 (Phase 3 - Model Version Validation):
├─ 08:00 - 08:30: Add version tracking to config.py
├─ 08:30 - 09:00: Create .deployed file recording
├─ 09:00 - 09:15: Add startup validation to app.py
├─ 09:15 - 10:00: Testing (version mismatch scenarios)
├─ 10:00 - 10:30: Deploy to production
└─ 10:30 - 11:00: Documentation + runbook updates
```

**Total: ~3 days (24-32 engineer-hours with testing + deployment overhead)**

---

## DEPENDENCIES & PREREQUISITES

### Phase 1 Prerequisites
- [ ] Firebase project already exists and is configured
- [ ] User provides Firebase Admin SDK service account JSON key
- [ ] `.env` file is writable and has `GOOGLE_APPLICATION_CREDENTIALS` placeholder

### Phase 2 Prerequisites
- [ ] `pip install pybreaker prometheus-client` available
- [ ] Prometheus is deployed (or will be deployed for production)
- [ ] Alert management system ready (Alertmanager, PagerDuty, etc.)

### Phase 3 Prerequisites
- [ ] Git repository has CI/CD pipeline
- [ ] Deployment process can create `.deployed` file

---

## ROLLBACK PLAN

**If Phase 1 breaks production:**
```bash
# Rollback: Disable Firebase JWT check
export ENVIRONMENT=development  # Falls back to request body UID
# Re-enable Firebase when fixed
```

**If Phase 2 breaks searches:**
```bash
# Disable circuit breaker (revert to old embedding_service.py imports)
git revert <commit>
# Circuit breaker will auto-recover after 5m if API comes back online
```

**If Phase 3 fails to deploy:**
```bash
# Remove .deployed file validation from config.py
# Deploy old app.py without version check
```

---

## SUCCESS CRITERIA

### Phase 1: Firebase Auth
- ✅ Production deployment with `ENVIRONMENT=production` requires valid Firebase JWT
- ✅ Staging deployment with `ENVIRONMENT=development` works with request body UID (with warning)
- ✅ Audit: Zero instances of cross-user data access in logs
- ✅ Security test: Injecting fake UID in request body is ignored (production only)

### Phase 2: Embedding Circuit Breaker
- ✅ Metrics exposed at `/metrics` endpoint
- ✅ Alerts configured for >10% error rate
- ✅ Circuit breaker opens after 5 consecutive failures
- ✅ Searches still work when embeddings fail (keyword matching fallback)
- ✅ Observability: Can identify "semantic search disabled" in logs

### Phase 3: Model Version Validation
- ✅ App fails to start if LLM_MODEL_VERSION not bumped
- ✅ `.deployed` file recorded on successful deployment
- ✅ Next developer knows exactly what version to bump to

---

## APPROVAL CHECKLIST

Before implementation, please confirm:

- [ ] **Phase 1 (Firebase Auth):** Ready to provide service account JSON key?
- [ ] **Phase 2 (Embedding Circuit Breaker):** Prometheus deployed in production?
- [ ] **Phase 3 (Model Version Validation):** CI/CD pipeline can create `.deployed` file?
- [ ] **Timeline:** 3-day window acceptable?
- [ ] **Rollback:** Understand rollback procedures if needed?

**Please review and confirm which phases are ready to implement.**
