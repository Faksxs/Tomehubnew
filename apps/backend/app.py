# -*- coding: utf-8 -*-
"""
TomeHub FastAPI Backend
=======================
Combines Search (RAG), Graph, and Ingestion services into a unified Async API.

Migrated from Flask to FastAPI for better performance and validation.
Date: 2026-01-18
"""

import sys
import os
import json
import re
import uvicorn
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional, List, Any, Dict
import traceback

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Models
from models.request_models import (
    SearchRequest, SearchResponse, IngestRequest, 
    FeedbackRequest, AddItemRequest, BatchMigrateRequest,
    ChatRequest, ChatResponse, HighlightSyncRequest, ComparisonRequest, PersonalNoteSyncRequest, PurgeResourceRequest,
    LibraryItemUpsertRequest, LibraryItemPatchRequest, LibraryBulkDeleteRequest,
    PersonalNoteFolderUpsertRequest, PersonalNoteFolderPatchRequest,
)
from middleware.auth_middleware import verify_firebase_token

# Import Services (Legacy & New)
from services.search_service import generate_answer, get_rag_context
from services.dual_ai_orchestrator import generate_evaluated_answer
from services.ingestion_service import ingest_book, ingest_text_item, process_bulk_items_logic, sync_highlights_for_item, sync_personal_note_for_item, purge_item_content
from services.library_service import (
    list_library_items,
    upsert_library_item,
    patch_library_item,
    delete_library_item,
    bulk_delete_library_items,
    list_personal_note_folders,
    upsert_personal_note_folder,
    patch_personal_note_folder,
    delete_personal_note_folder,
)
from services.index_freshness_service import get_index_freshness_state, maybe_trigger_graph_enrichment_async
from services.external_kb_service import (
    get_external_kb_backfill_status,
    maybe_trigger_external_enrichment_async,
    start_external_kb_backfill_async,
)
from services.epistemic_distribution_service import get_epistemic_distribution
from services.feedback_service import submit_feedback
from services.pdf_service import get_pdf_metadata
from services.ai_service import (
    enrich_book_async, 
    generate_tags_async, 
    verify_cover_async, 
    analyze_highlights_async, 
    search_resources_async,
    stream_enrichment
)
from services.analytics_service import (
    is_analytic_word_count,
    extract_target_term,
    count_lemma_occurrences,
    resolve_book_id_from_question,
    count_all_notes_occurrences,
    resolve_all_book_ids,
    get_comparative_stats,
    get_keyword_contexts,
)
from services.query_plan_service import looks_explicit_compare_query
from models.request_models import (
    EnrichBookRequest, GenerateTagsRequest, VerifyCoverRequest, AnalyzeHighlightsRequest
)

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.cache_service import get_cache, generate_cache_key
from services.monitoring import DB_POOL_UTILIZATION, CIRCUIT_BREAKER_STATE, REDIS_AVAILABLE
from services.memory_monitor_service import MemoryMonitor
from services.embedding_service import get_circuit_breaker_status

# Configure Sentry - REPLACED BY LOKI (Standard Logging)
# (Sentry code removed)

# Configure Logging (Structured JSON)
from pythonjsonlogger import jsonlogger

logger = logging.getLogger("tomehub_api")
logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

# Console Handler (Stdout for Docker)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.propagate = False

# Remove default handlers to avoid duplicates
logging.getLogger().handlers = []
logging.getLogger().addHandler(logHandler)


def _allow_dev_unverified_auth() -> bool:
    return (
        settings.ENVIRONMENT == "development"
        and not bool(getattr(settings, "FIREBASE_READY", False))
        and bool(getattr(settings, "DEV_UNSAFE_AUTH_BYPASS", False))
    )


def get_verified_uid(request: Request, uid_from_jwt: Optional[str]) -> str:
    """
    Authoritative UID resolver for TomeHub.
    Prioritizes verified JWT, falls back to raw UID in development mode.
    """
    if uid_from_jwt:
        return uid_from_jwt

    # Local development fallbacks
    if settings.ENVIRONMENT == "development":
        # 1. Query Param
        uid = request.query_params.get("firebase_uid")
        # 2. X-Firebase-UID Header
        if not uid:
            uid = request.headers.get("X-Firebase-UID")
        # 3. Authorization Header (raw UID)
        if not uid:
            auth_header = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if auth_header and len(auth_header) < 128:
                uid = auth_header
        
        if uid:
            return uid

    raise HTTPException(status_code=401, detail="Authentication required")



def _validate_cors_origins(origins: list[str]) -> list[str]:
    normalized = [o.strip() for o in origins if str(o).strip()]
    if not normalized:
        raise ValueError("ALLOWED_ORIGINS cannot be empty")
    if "*" in normalized:
        raise ValueError("SECURITY: '*' is not allowed when allow_credentials=True")

    for origin in normalized:
        if origin.startswith("https://"):
            continue
        if settings.ENVIRONMENT == "development" and origin.startswith(
            ("http://localhost", "http://127.0.0.1", "http://0.0.0.0")
        ):
            continue
        raise ValueError(f"Invalid CORS origin: {origin}")
    return normalized


_HIGHLIGHT_FOCUS_TERMS = (
    "highlight", "highlights", "altini ciz", "altını çiz", "notlarim", "notlarım",
    "notlar", "alinan not", "alıntı", "alinti", "insight"
)


def _is_scope_policy_enabled_for_chat(firebase_uid: str, mode: str) -> bool:
    if not bool(getattr(settings, "SEARCH_SCOPE_POLICY_ENABLED", False)):
        return False

    enabled_modes = {
        str(m or "").strip().upper()
        for m in getattr(settings, "SEARCH_SCOPE_POLICY_CHAT_MODES", []) or []
    }
    if enabled_modes and str(mode or "STANDARD").strip().upper() not in enabled_modes:
        return False

    canary_uids = set(getattr(settings, "SEARCH_SCOPE_POLICY_CANARY_UIDS", set()) or set())
    if canary_uids and str(firebase_uid or "").strip() not in canary_uids:
        return False
    return True


def _looks_highlight_focused_query(message: str) -> bool:
    text = str(message or "").strip().lower()
    return any(term in text for term in _HIGHLIGHT_FOCUS_TERMS)


def _resolve_chat_scope_policy(
    *,
    message: str,
    firebase_uid: str,
    requested_scope_mode: str,
    explicit_book_id: Optional[str],
    context_book_id: Optional[str],
    compare_mode: Optional[str] = None,
    target_book_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    requested = str(requested_scope_mode or "AUTO").strip().upper() or "AUTO"
    anchor_book_id = str(explicit_book_id or context_book_id or "").strip() or None
    requested_targets = [str(b or "").strip() for b in (target_book_ids or []) if str(b or "").strip()]
    compare_mode_effective = str(compare_mode or "EXPLICIT_ONLY").strip().upper() or "EXPLICIT_ONLY"
    compare_query_explicit = looks_explicit_compare_query(message)

    if requested in {"AUTO", "BOOK_FIRST"}:
        if len(requested_targets) >= 2:
            return {
                "scope_mode": "GLOBAL",
                "resolved_book_id": anchor_book_id,
                "scope_decision": "COMPARE_GLOBAL_OVERRIDE_TARGETS",
            }
        if compare_query_explicit and compare_mode_effective in {"EXPLICIT_ONLY", "AUTO"}:
            return {
                "scope_mode": "GLOBAL",
                "resolved_book_id": anchor_book_id,
                "scope_decision": "COMPARE_GLOBAL_OVERRIDE_QUERY",
            }

    chosen_book_id = anchor_book_id
    if not chosen_book_id and requested in {"AUTO", "BOOK_FIRST"}:
        try:
            chosen_book_id = resolve_book_id_from_question(firebase_uid, message)
        except Exception:
            chosen_book_id = None

    if requested == "GLOBAL":
        return {
            "scope_mode": "GLOBAL",
            "resolved_book_id": None,
            "scope_decision": "GLOBAL_FORCED",
        }
    if requested == "HIGHLIGHT_FIRST":
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": chosen_book_id,
            "scope_decision": "HIGHLIGHT_FIRST_FORCED",
        }
    if requested == "BOOK_FIRST":
        if chosen_book_id:
            return {
                "scope_mode": "BOOK_FIRST",
                "resolved_book_id": chosen_book_id,
                "scope_decision": "BOOK_FIRST_FORCED",
            }
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": None,
            "scope_decision": "BOOK_FIRST_FALLBACK_NO_BOOK",
        }

    # AUTO mode
    if chosen_book_id:
        return {
            "scope_mode": "BOOK_FIRST",
            "resolved_book_id": chosen_book_id,
            "scope_decision": "AUTO_RESOLVED_BOOK",
        }
    if _looks_highlight_focused_query(message):
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": None,
            "scope_decision": "AUTO_HIGHLIGHT_FOCUS",
        }
    return {
        "scope_mode": "HIGHLIGHT_FIRST",
        "resolved_book_id": None,
        "scope_decision": "AUTO_DEFAULT_HIGHLIGHT_FIRST",
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Init Helper Services
    logger.info("🚀 Startup: Initializing TomeHub API...")
    
    # 0. Validate Model Versions (Phase 3)
    logger.info("Validating model versions...")
    try:
        # This will raise ValueError if versions are invalid or not bumped
        settings._validate_model_versions()
        logger.info(f"✓ Model versions validated successfully")
    except ValueError as e:
        error_msg = f"❌ Configuration Error: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    # 1. Check Firebase Auth
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    if settings.ENVIRONMENT == "production":
        if not settings.FIREBASE_READY:
            error_msg = (
                "CRITICAL: Firebase Admin SDK not initialized. "
                "Set GOOGLE_APPLICATION_CREDENTIALS and ensure credentials file exists. "
                "Firebase Auth is required for production."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        logger.info("✓ Firebase Auth ready for production")
    else:
        if settings.FIREBASE_READY:
            logger.info("✓ Firebase Auth configured (development mode)")
        else:
            logger.warning("⚠️ Firebase Auth not configured (OK for local development only)")
    
    # 2. Init Database Pool
    logger.info("Starting up: Initializing DB Pool...")
    DatabaseManager.init_pool()
    logger.info(f"✓ Database pools initialized (Read Max={settings.DB_READ_POOL_MAX}, Write Max={settings.DB_WRITE_POOL_MAX})")
    
    # 3. Initialize Cache
    if settings.CACHE_ENABLED:
        logger.info("Starting up: Initializing Cache...")
        from services.cache_service import init_cache
        cache = init_cache(
            l1_maxsize=settings.CACHE_L1_MAXSIZE,
            l1_ttl=settings.CACHE_L1_TTL,
            redis_url=settings.REDIS_URL
        )
        app.state.cache = cache
        logger.info("✓ Cache initialized successfully")
    else:
        logger.info("Cache disabled (CACHE_ENABLED=false)")
        app.state.cache = None
    
    # 4. Start Memory Monitor (Task A2)
    logger.info("Starting up: Initializing Memory Monitor...")
    from services.auto_restart_service import auto_restart_manager
    memory_task = asyncio.create_task(auto_restart_manager.monitor())
    app.state.memory_task = memory_task
    logger.info("✓ Memory monitor started")
    
    # 5. Start Background Metrics Updater (Phase D)
    async def metrics_background_updater():
        """Periodically updates custom tech Gauges for Prometheus."""
        logger.info("Metrics Updater Background Task started")
        while True:
            try:
                # DB Pool Stats
                stats = DatabaseManager.get_pool_stats()
                for pool_type in ["read", "write"]:
                    pool = stats[pool_type]
                    DB_POOL_UTILIZATION.labels(pool_type=pool_type, metric_type="active").set(pool["active"])
                    DB_POOL_UTILIZATION.labels(pool_type=pool_type, metric_type="opened").set(pool["opened"])
                    DB_POOL_UTILIZATION.labels(pool_type=pool_type, metric_type="max").set(pool["max"])
                
                # Circuit Breaker Status
                cb_status = get_circuit_breaker_status()
                state_map = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}
                CIRCUIT_BREAKER_STATE.labels(service="embedding").set(state_map.get(cb_status["state"], 0))

                # Redis-backed L2 cache health (0/1)
                redis_available = 0
                cache = getattr(app.state, "cache", None)
                if cache is not None:
                    try:
                        if getattr(cache, "l2", None) is not None and cache.l2.is_available():
                            redis_available = 1
                    except Exception:
                        redis_available = 0
                REDIS_AVAILABLE.labels(layer="l2_cache").set(redis_available)
                
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics updater: {e}")
                await asyncio.sleep(10)

    metrics_task = asyncio.create_task(metrics_background_updater())
    app.state.metrics_task = metrics_task
    logger.info("✓ Metrics updater started (10s interval)")
    
    yield
    # Shutdown: Clean up
    logger.info("🛑 Shutdown: Cancelling background tasks...")
    memory_task.cancel()
    metrics_task.cancel()
    try:
        await asyncio.gather(memory_task, metrics_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    
    logger.info("🛑 Shutdown: Closing DB Pool...")
    DatabaseManager.close_pool()

# Initialize FastAPI
app = FastAPI(
    title="TomeHub API",
    description="Unified Backend for TomeHub (Search + AI + Ingestion)",
    version="2.0.0",
    lifespan=lifespan
)

# Initialize Limiter
# Custom key function for rate limiting (User ID > IP)
def get_rate_limit_key(request: Request):
    # Try to get UID from header (set by auth middleware or client)
    # Note: Using header instead of body for standard limiter compatibility
    uid = request.headers.get("X-Firebase-UID")
    if uid:
        return uid
    return get_remote_address(request)

# Initialize Limiter
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[settings.RATE_LIMIT_GLOBAL]
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration
# CORS Configuration
# Use dynamic origins from environment variables via config.settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=_validate_cors_origins(settings.ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Layer 4 Flow Routes (MUST BE BEFORE Instrumentator)
# We import explicitly to fail fast if there's an issue
logger.info("Importing flow_routes...")
# Include Flow Router (Layer 4)
from routes import flow_routes
app.include_router(flow_routes.router)
logger.info("Router registered", extra={"route_count": len(flow_routes.router.routes)})

# Include AI Routes (migrated from local app.py handlers)
from routes import ai_routes
app.include_router(ai_routes.router)
logger.info("Router registered", extra={"route_count": len(ai_routes.router.routes)})

# Prometheus Instrumentation (must be AFTER all routers are added)
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/")
async def health_check():
    return {
        "status": "online",
        "service": "TomeHub API (FastAPI)",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/realtime/poll")
async def realtime_poll(
    request: Request,
    since_ms: int = 0,
    limit: int = 100,
    firebase_uid: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    """
    Fast polling endpoint for multi-device UX consistency.
    Returns coarse-grained change events since client timestamp.
    """
    if firebase_uid_from_jwt:
        verified_uid = firebase_uid_from_jwt
    else:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=401, detail="Authentication required")
        verified_uid = firebase_uid or request.query_params.get("firebase_uid")
        if not verified_uid:
            raise HTTPException(status_code=400, detail="firebase_uid is required in development")

    safe_limit = max(1, min(int(limit), 300))
    events: list[dict[str, Any]] = []
    cutoff_ms = max(int(since_ms or 0), 0)

    try:
        from services.change_event_service import fetch_change_events_since
        changes, last_event_id = fetch_change_events_since(
            firebase_uid=verified_uid,
            since_ms=cutoff_ms,
            limit=safe_limit,
        )
        if changes:
            server_time_ms = int(datetime.now().timestamp() * 1000)
            return {
                "success": True,
                "server_time_ms": server_time_ms,
                "server_time": datetime.now().isoformat(),
                "last_event_id": last_event_id,
                "changes": changes,
                "events": changes,
                "count": len(changes),
                "source": "outbox",
            }
    except Exception as e:
        logger.warning(f"Realtime polling outbox read failed (fallback to legacy query): {e}")

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ITEM_ID, TITLE, COALESCE(UPDATED_AT, CREATED_AT)
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE FIREBASE_UID = :p_uid
                    ORDER BY COALESCE(UPDATED_AT, CREATED_AT) DESC
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_uid": verified_uid, "p_limit": safe_limit},
                )
                for row in cursor.fetchall():
                    ts = row[2]
                    ts_ms = int(ts.timestamp() * 1000) if ts else int(datetime.now().timestamp() * 1000)
                    if ts_ms <= cutoff_ms:
                        continue
                    events.append(
                        {
                            "event_type": "book.updated",
                            "book_id": str(row[0]),
                            "title": str(row[1] or ""),
                            "updated_at_ms": ts_ms,
                        }
                    )

                cursor.execute(
                    """
                    SELECT ITEM_ID, CONTENT_TYPE, MAX(CREATED_AT)
                    FROM TOMEHUB_CONTENT_V2
                    WHERE FIREBASE_UID = :p_uid
                      AND CONTENT_TYPE IN ('HIGHLIGHT', 'INSIGHT', 'PERSONAL_NOTE')
                    GROUP BY ITEM_ID, CONTENT_TYPE
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_uid": verified_uid, "p_limit": safe_limit},
                )
                for row in cursor.fetchall():
                    source_type = str(row[1] or "").upper()
                    ts = row[2]
                    ts_ms = int(ts.timestamp() * 1000) if ts else int(datetime.now().timestamp() * 1000)
                    if ts_ms <= cutoff_ms:
                        continue
                    event_type = "highlight.synced" if source_type in {"HIGHLIGHT", "INSIGHT"} else "note.synced"
                    events.append(
                        {
                            "event_type": event_type,
                            "book_id": str(row[0] or ""),
                            "source_type": source_type,
                            "updated_at_ms": ts_ms,
                        }
                    )
    except Exception as e:
        logger.error(f"Realtime polling query failed: {e}")
        raise HTTPException(status_code=500, detail="Realtime polling failed")

    events.sort(key=lambda e: int(e.get("updated_at_ms") or 0), reverse=True)
    if len(events) > safe_limit:
        events = events[:safe_limit]
    server_time_ms = int(datetime.now().timestamp() * 1000)
    return {
        "success": True,
        "server_time_ms": server_time_ms,
        "server_time": datetime.now().isoformat(),
        "last_event_id": None,
        "changes": events,
        "events": events,
        "count": len(events),
        "source": "legacy_aggregate",
    }



# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@app.post("/api/search", response_model=SearchResponse)
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def search(
    request: Request,
    search_request: SearchRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Determine authoritative UID (JWT or request body in dev mode)
    if firebase_uid_from_jwt:
        # Production: JWT is authoritative
        firebase_uid = firebase_uid_from_jwt
        logger.info(f"Using JWT-verified UID: {firebase_uid}")
    else:
        # Development mode: use request body UID (with warning)
        firebase_uid = search_request.firebase_uid
        if _allow_dev_unverified_auth():
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            logger.error("SECURITY: Auth failed but ENVIRONMENT != development. Rejecting request.")
            raise HTTPException(status_code=401, detail="Authentication required")
    
    # Log search start
    logger.info(
        "Search started", 
        extra={"uid": firebase_uid, "question": search_request.question}
    )
    
    try:
        import asyncio
        from functools import partial
        visibility_scope = "all" if search_request.include_private_notes else search_request.visibility_scope
        
        loop = asyncio.get_running_loop()

        # Analytic short-circuit (Layer-3)
        if is_analytic_word_count(search_request.question):
            term = extract_target_term(search_request.question)
            resolved_book_id = search_request.book_id or search_request.context_book_id
            if not resolved_book_id:
                resolved_book_id = resolve_book_id_from_question(firebase_uid, search_request.question)

            if not resolved_book_id and not term:
                return {
                    "answer": "Analitik sayım için kitap ve kelime gerekli. Örn: \"Mahur Beste kitabında zaman kelimesi kaç defa geçiyor?\"",
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "book_and_term_missing"},
                        "search_variant": "search",
                        "graph_capability": "enabled",
                    },
                }
            if not resolved_book_id:
                return {
                    "answer": "Analitik sayım için hangi kitabı soruyorsun? Örn: \"Mahur Beste kitabında zaman kelimesi kaç defa geçiyor?\"",
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "book_id_required"},
                        "search_variant": "search",
                        "graph_capability": "enabled",
                    },
                }
            if not term:
                return {
                    "answer": "Sayılacak kelimeyi belirtir misin?",
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "term_missing"},
                        "search_variant": "search",
                        "graph_capability": "enabled",
                    },
                }
            count = count_lemma_occurrences(firebase_uid, resolved_book_id, term)
            
            # Fetch context snippets for the UI "See Contexts" button
            from services.analytics_service import get_keyword_contexts
            contexts = get_keyword_contexts(firebase_uid, resolved_book_id, term, limit=10)
            
            metadata_dict = {
                "status": "analytic",
                "analytics": {
                    "type": "word_count",
                    "term": term,
                    "count": count,
                    "match": "lemma",
                    "scope": "book_chunks",
                    "resolved_book_id": resolved_book_id,
                    "contexts": contexts if count > 0 else [],
                    "debug": {"cache": "disabled"},
                },
                "search_variant": "search",
                "graph_capability": "enabled",
            }
            
            logger.debug("Analytic search context count", extra={"count": len(metadata_dict['analytics']['contexts'])})
            
            return {
                "answer": f"\"{term}\" kelimesi bu kitapta toplam {count} kez geçiyor.",
                "sources": [],
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata_dict
            }
        
        scope_policy_active = _is_scope_policy_enabled_for_chat(firebase_uid, search_request.mode)
        effective_book_id = search_request.book_id
        effective_resource_type = search_request.resource_type
        effective_scope_mode = "GLOBAL"
        scope_decision = "LEGACY_SCOPE_POLICY_DISABLED"
        if scope_policy_active:
            scope_state = _resolve_chat_scope_policy(
                message=search_request.question,
                firebase_uid=firebase_uid,
                requested_scope_mode=search_request.scope_mode,
                explicit_book_id=search_request.book_id,
                context_book_id=search_request.context_book_id,
                compare_mode=search_request.compare_mode,
                target_book_ids=search_request.target_book_ids,
            )
            effective_scope_mode = scope_state["scope_mode"]
            scope_decision = scope_state["scope_decision"]
            effective_book_id = scope_state.get("resolved_book_id")

            if effective_scope_mode == "BOOK_FIRST":
                effective_resource_type = "BOOK"
            elif effective_scope_mode == "HIGHLIGHT_FIRST":
                effective_resource_type = "ALL_NOTES"
            else:
                effective_resource_type = search_request.resource_type

        scope_metadata = {
            "scope_policy_active": scope_policy_active,
            "scope_decision": scope_decision,
            "scope_mode": effective_scope_mode,
            "resolved_book_id": effective_book_id,
        }

        # Run synchronous RAG search in thread pool
        result = await loop.run_in_executor(
            None, 
            partial(
                generate_answer, 
                search_request.question, 
                firebase_uid, 
                effective_book_id,
                None, # chat_history
                "", # session_summary
                search_request.limit,
                search_request.offset,
                None, # session_id
                effective_resource_type,
                effective_scope_mode,
                scope_policy_active,
                search_request.compare_mode,
                search_request.target_book_ids,
                visibility_scope,
                search_request.content_type,
                search_request.ingestion_type,
            )
        )
        
        # Unpack result (answer, sources, metadata)
        answer, sources, metadata = result
        logger.info(
            "Search finished successfully",
            extra={
                "answer_length": len(answer),
                "source_count": len(sources) if sources else 0,
                "first_source_title": sources[0].get('title') if sources else None,
                "first_source_score": sources[0].get('similarity_score') if sources else None,
                "metadata": metadata,
            }
        )

        if isinstance(metadata, dict):
            metadata.setdefault("search_variant", "search")
            metadata.setdefault("graph_capability", "enabled")
            for key, value in scope_metadata.items():
                metadata.setdefault(key, value)
            metadata.setdefault("visibility_scope", visibility_scope)
            metadata.setdefault("content_type_filter", search_request.content_type)
            metadata.setdefault("ingestion_type_filter", search_request.ingestion_type)
        
        return {
            "answer": answer,
            "sources": sources or [],
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        }
    except Exception as e:
        logger.error("Search failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat_endpoint(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Stateful Chat Endpoint (LogosChat - Layer 3).
    Orchestrates session, history, and RAG search.
    """
    # Determine authoritative UID (JWT or request body in dev mode)
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
        logger.info(f"Using JWT-verified UID: {firebase_uid}")
    else:
        firebase_uid = chat_request.firebase_uid
        if _allow_dev_unverified_auth():
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            logger.error("SECURITY: Auth failed but ENVIRONMENT != development. Rejecting request.")
            raise HTTPException(status_code=401, detail="Authentication required")
    
    logger.info(
        "Chat started",
        extra={"session_id": chat_request.session_id, "uid": firebase_uid}
    )
    
    try:
        import asyncio
        from functools import partial
        from services.chat_history_service import (
            create_session, add_message, get_session_context, summarize_session_history
        )
        
        loop = asyncio.get_running_loop()
        
        # 1. Handle Session Creation
        session_id = chat_request.session_id
        if not session_id:
            new_title = f"Chat: {chat_request.message[:40]}..."
            session_id = await loop.run_in_executor(None, create_session, firebase_uid, new_title)
            if not session_id:
                raise HTTPException(status_code=500, detail="Failed to create session")
            
        # 2. Get Context (Summary + History)
        ctx_data = await loop.run_in_executor(None, get_session_context, session_id)
        
        # 3. Save User Message
        await loop.run_in_executor(None, add_message, session_id, 'user', chat_request.message)

        # 3.5 Analytic short-circuit (Layer-3)
        if is_analytic_word_count(chat_request.message):
            term = extract_target_term(chat_request.message)
            resolved_book_id = chat_request.book_id
            if not resolved_book_id:
                resolved_book_id = resolve_book_id_from_question(firebase_uid, chat_request.message)

            if not resolved_book_id and not term:
                answer = "Analitik sayım için kitap ve kelime gerekli. Örn: \"Mahur Beste kitabında zaman kelimesi kaç defa geçiyor?\""
                await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, [])
                background_tasks.add_task(summarize_session_history, session_id)
                return {
                    "answer": answer,
                    "session_id": session_id,
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "conversation_state": {},
                    "thinking_history": [],
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "book_and_term_missing"},
                    },
                }
            if not resolved_book_id:
                answer = "Analitik sayım için hangi kitabı soruyorsun? Örn: \"Mahur Beste kitabında zaman kelimesi kaç defa geçiyor?\""
                await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, [])
                background_tasks.add_task(summarize_session_history, session_id)
                return {
                    "answer": answer,
                    "session_id": session_id,
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "conversation_state": {},
                    "thinking_history": [],
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "book_id_required"},
                    },
                }
            if not term:
                answer = "Sayılacak kelimeyi belirtir misin?"
                await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, [])
                background_tasks.add_task(summarize_session_history, session_id)
                return {
                    "answer": answer,
                    "session_id": session_id,
                    "sources": [],
                    "timestamp": datetime.now().isoformat(),
                    "conversation_state": {},
                    "thinking_history": [],
                    "metadata": {
                        "status": "analytic",
                        "analytics": {"type": "word_count", "error": "term_missing"},
                    },
                }

            # 3.9 Fetch all data for narrative response
            # 3.9 Fetch all data for narrative response
            # Implementation Strategy: Single book analytic only.
            
            # A. Count in Current Book (Critical)
            try:
                count = count_lemma_occurrences(firebase_uid, resolved_book_id, term)
            except Exception as e:
                logger.error(f"Primary count failed: {e}")
                count = 0

            # B. Build Simple Narrative (Current Book Only)
            answer = f"\"{term}\" kelimesi bu kitapta toplam **{count}** kez geçiyor."

            logger.info(f"Final Narrative Answer: {answer}")
            
            # C. Fetch Contexts for 'See Contexts' button
            contexts = get_keyword_contexts(firebase_uid, resolved_book_id, term, limit=10)
            
            await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, [])
            background_tasks.add_task(summarize_session_history, session_id)
            return {
                "answer": answer,
                "session_id": session_id,
                "sources": [],
                "timestamp": datetime.now().isoformat(),
                "conversation_state": {},
                "thinking_history": [],
                "metadata": {
                    "status": "analytic",
                    "analytics": {
                        "type": "word_count",
                        "term": term,
                        "count": count,
                        "match": "lemma",
                        "scope": "book_chunks",
                        "resolved_book_id": resolved_book_id,
                        "contexts": contexts
                    },
                },
            }

        scope_policy_active = _is_scope_policy_enabled_for_chat(firebase_uid, chat_request.mode)
        effective_book_id = chat_request.book_id
        effective_resource_type = chat_request.resource_type
        effective_scope_mode = "GLOBAL"
        scope_decision = "LEGACY_SCOPE_POLICY_DISABLED"
        if scope_policy_active:
            scope_state = _resolve_chat_scope_policy(
                message=chat_request.message,
                firebase_uid=firebase_uid,
                requested_scope_mode=chat_request.scope_mode,
                explicit_book_id=chat_request.book_id,
                context_book_id=chat_request.context_book_id,
                compare_mode=chat_request.compare_mode,
                target_book_ids=chat_request.target_book_ids,
            )
            effective_scope_mode = scope_state["scope_mode"]
            scope_decision = scope_state["scope_decision"]
            effective_book_id = scope_state.get("resolved_book_id")

            if effective_scope_mode == "BOOK_FIRST":
                effective_resource_type = "BOOK"
            elif effective_scope_mode == "HIGHLIGHT_FIRST":
                effective_resource_type = "ALL_NOTES"
            else:
                effective_resource_type = chat_request.resource_type

        scope_metadata = {
            "scope_policy_active": scope_policy_active,
            "scope_decision": scope_decision,
            "scope_mode": effective_scope_mode,
            "resolved_book_id": effective_book_id,
        }

        # 4. Generate Answer (Using RAG with history)
        # Route based on mode:
        # - STANDARD: Use fast legacy flow (generate_answer)
        # - EXPLORER: Use Dual-AI Orchestrator (deep dialectical analysis)
        use_explorer_mode = chat_request.mode == 'EXPLORER'
        
        answer = "Üzgünüm, ilgili içerik bulunamadı."
        sources = []
        conversation_state = None  # To return in response
        thinking_history = []      # To return in response
        final_metadata = {}
        # Guardrail: prevent accidentally tiny retrieval pools in chat mode.
        retrieval_limit = int(chat_request.limit or 20)
        if use_explorer_mode:
            retrieval_limit = max(20, retrieval_limit)
        else:
            retrieval_limit = max(10, retrieval_limit)
        retrieval_limit = min(100, retrieval_limit)
        
        if use_explorer_mode:
            # EXPLORER Mode: Dual-AI Orchestrator with conversation state
            # Reuse already-fetched session context instead of another DB read.
            state_payload = str((ctx_data or {}).get('conversation_state_json') or '').strip()
            summary_payload = str((ctx_data or {}).get('summary') or '').strip()
            conversation_state = {
                "active_topic": "",
                "assumptions": [],
                "open_questions": [],
                "established_facts": [],
                "turn_count": 0,
            }
            raw_state_payload = state_payload or summary_payload
            if raw_state_payload:
                if raw_state_payload.startswith("{"):
                    try:
                        parsed_state = json.loads(raw_state_payload)
                        if isinstance(parsed_state, dict):
                            conversation_state.update(parsed_state)
                    except Exception:
                        conversation_state["legacy_summary"] = raw_state_payload
                        conversation_state["active_topic"] = raw_state_payload[:100]
                else:
                    conversation_state["legacy_summary"] = raw_state_payload
                    conversation_state["active_topic"] = raw_state_payload[:100]

            # 1. Retrieve Context
            rag_ctx = await loop.run_in_executor(
                None, 
                partial(
                    get_rag_context,
                    chat_request.message, 
                    firebase_uid, 
                    effective_book_id,
                    chat_history=ctx_data['recent_messages'],
                    mode='EXPLORER',
                    resource_type=effective_resource_type,
                    scope_mode=effective_scope_mode,
                    apply_scope_policy=scope_policy_active,
                    compare_mode=chat_request.compare_mode,
                    target_book_ids=chat_request.target_book_ids,
                    limit=retrieval_limit,
                    offset=chat_request.offset
                )
            )
            
            if rag_ctx:
                from services.dual_ai_orchestrator import generate_evaluated_answer
                
                final_result = await generate_evaluated_answer(
                    question=chat_request.message,
                    chunks=rag_ctx['chunks'],
                    answer_mode='EXPLORER',
                    confidence_score=rag_ctx['confidence'],
                    network_status=rag_ctx.get('network_status', 'IN_NETWORK'),
                    conversation_state=conversation_state,  # Pass structured state
                    source_diversity_count=int(rag_ctx.get("source_diversity_count") or 0),
                )
                
                answer = final_result['final_answer']
                thinking_history = final_result['metadata'].get('history', [])
                
                # Merge RAG degradations with Orchestrator metadata
                rag_meta = rag_ctx.get('metadata', {})
                if rag_meta: 
                    # Ensure final_result metadata has these too
                    if 'degradations' in rag_meta:
                        if 'degradations' not in final_result['metadata']:
                            final_result['metadata']['degradations'] = []
                        final_result['metadata']['degradations'].extend(rag_meta['degradations'])
                    # Phase-1: forward retrieval diagnostics for UI/observability
                    for key in (
                        "retrieval_fusion_mode",
                        "retrieval_path",
                        "graph_candidates_count",
                        "external_graph_candidates_count",
                        "vector_candidates_count",
                        "source_diversity_count",
                        "source_type_diversity_count",
                        "academic_scope",
                        "external_kb_used",
                        "wikidata_qid",
                        "openalex_used",
                        "dbpedia_used",
                        "orkg_used",
                        "search_log_id",
                        "graph_bridge_attempted",
                        "quote_target_count",
                        "compare_applied",
                        "target_books_used",
                        "target_books_truncated",
                        "unauthorized_target_book_ids",
                        "evidence_policy",
                        "per_book_evidence_count",
                        "latency_budget_hit",
                        "compare_degrade_reason",
                        "compare_mode",
                    ):
                        if key in rag_meta:
                            final_result['metadata'][key] = rag_meta[key]
                        
                final_metadata = final_result['metadata']
                
                # Use the exact sources seen by the LLM
                used_chunks = final_result['metadata'].get('used_chunks', [])
                for i, c in enumerate(used_chunks, 1):
                    sources.append({
                        'id': i,
                        'title': c.get('title', 'Unknown'),
                        'score': c.get('answerability_score', 0),
                        'page_number': c.get('page_number', 0),
                        'content': str(c.get('content_chunk', ''))[:500]
                    })
        else:
            # STANDARD Mode: Fast legacy flow
            answer_result, sources_result, meta_result = await loop.run_in_executor(
                None,
                partial(
                    generate_answer,
                    chat_request.message,
                    firebase_uid,
                    effective_book_id,
                    ctx_data['recent_messages'],
                    ctx_data['summary'] or "",
                    retrieval_limit,
                    chat_request.offset,
                    session_id,
                    effective_resource_type,
                    effective_scope_mode,
                    scope_policy_active,
                    chat_request.compare_mode,
                    chat_request.target_book_ids,
                )
            )
            
            if answer_result:
                answer = answer_result
                sources = sources_result or []
                final_metadata = meta_result or {}

        if isinstance(final_metadata, dict):
            final_metadata.setdefault("effective_retrieval_limit", retrieval_limit)
            for key, value in scope_metadata.items():
                final_metadata.setdefault(key, value)
        
        # 5. Save Assistant Message
        await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, sources)
        
        # 6. Periodic Summarization (Background)
        background_tasks.add_task(summarize_session_history, session_id)
        
        return {
            "answer": answer,
            "session_id": session_id,
            "sources": sources or [],
            "timestamp": datetime.now().isoformat(),
            "conversation_state": conversation_state,
            "thinking_history": thinking_history,
            "metadata": final_metadata
        }
        
    except Exception as e:
        logger.error("Chat failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/ingested-books")
async def get_ingested_books(
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Returns list of book_ids that have ingested PDF content for the user.
    """
    # 1. Determine UID (Priority: JWT > QueryParam)
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
    else:
        # Fallback to query param OR manual header extraction for raw UIDs (Dev mode)
        firebase_uid = request.query_params.get("firebase_uid")
        
        # If still none, check Authorization header manually to see if it's a raw UID
        if not firebase_uid:
            auth_header = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if auth_header and len(auth_header) < 128: # Raw UIDs are short, JWTs are long
                firebase_uid = auth_header

    if not firebase_uid:
         raise HTTPException(status_code=401, detail="Authentication required")

    try:
        from services.analytics_service import resolve_ingested_book_ids
        import asyncio

        loop = asyncio.get_running_loop()
        book_ids = await loop.run_in_executor(
            None,
            resolve_ingested_book_ids,
            firebase_uid,
            "pdf"
        )

        logger.info(f"Ingested books fetched", extra={"uid": firebase_uid, "count": len(book_ids)})
        return {
            "book_ids": book_ids,
            "count": len(book_ids)
        }
    except Exception as e:
        logger.error(f"Ingested books endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/epistemic-distribution")
async def get_epistemic_distribution_endpoint(
    request: Request,
    book_id: Optional[str] = None,
    limit: int = 250,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
    else:
        if not _allow_dev_unverified_auth():
            raise HTTPException(status_code=401, detail="Authentication required")
        firebase_uid = request.query_params.get("firebase_uid")
        if not firebase_uid:
            auth_header = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if auth_header and len(auth_header) < 128:
                firebase_uid = auth_header
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Authentication required")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: get_epistemic_distribution(firebase_uid=firebase_uid, book_id=book_id, limit=limit),
    )
    return result

@app.get("/api/analytics/concordance")
async def get_concordance(
    book_id: str,
    term: str,
    limit: int = 50,
    offset: int = 0,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Endpoint for paginated KWIC (Concordance) retrieval.
    """
    if not firebase_uid_from_jwt:
         raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from services.analytics_service import get_keyword_contexts
        import asyncio
        
        loop = asyncio.get_running_loop()
        contexts = await loop.run_in_executor(
            None, 
            get_keyword_contexts, 
            firebase_uid_from_jwt, 
            book_id, 
            term, 
            limit, 
            offset
        )
        
        return {
            "book_id": book_id,
            "term": term,
            "contexts": contexts,
            "limit": limit,
            "offset": offset,
            "count": len(contexts)
        }
    except Exception as e:
        logger.error("Concordance endpoint failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/distribution")
async def get_distribution(
    book_id: str,
    term: str,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Endpoint for keyword distribution across pages.
    """
    if not firebase_uid_from_jwt:
         raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from services.analytics_service import get_keyword_distribution
        import asyncio
        
        loop = asyncio.get_running_loop()
        distribution = await loop.run_in_executor(
            None, 
            get_keyword_distribution, 
            firebase_uid_from_jwt, 
            book_id, 
            term
        )
        
        return {
            "book_id": book_id,
            "term": term,
            "distribution": distribution
        }
    except Exception as e:
        logger.error("Distribution endpoint failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analytics/compare")
async def get_comparative_stats_endpoint(
    request: ComparisonRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Endpoint for cross-book keyword comparison.
    """
    if not firebase_uid_from_jwt:
         raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from services.analytics_service import get_comparative_stats
        import asyncio
        
        loop = asyncio.get_running_loop()
        stats = await loop.run_in_executor(
            None, 
            get_comparative_stats, 
            firebase_uid_from_jwt, 
            request.target_book_ids, 
            request.term
        )
        
        return {
            "term": request.term,
            "comparison": stats
        }
    except Exception as e:
        logger.error("Comparison endpoint failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/smart-search")
async def perform_search(
    request: SearchRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Pure weighted search (Search - Layer 2).
    """
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
    else:
        firebase_uid = request.firebase_uid
        if _allow_dev_unverified_auth():
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.smart_search_service import perform_search
        from functools import partial
        visibility_scope = "all" if request.include_private_notes else request.visibility_scope

        loop = asyncio.get_running_loop()
        results, metadata = await loop.run_in_executor(
            None,
            partial(
                perform_search,
                request.question, 
                firebase_uid, 
                limit=request.limit, 
                offset=request.offset,
                result_mix_policy="lexical_then_semantic_tail",
                semantic_tail_cap=settings.SEARCH_SMART_SEMANTIC_TAIL_CAP,
                visibility_scope=visibility_scope,
                content_type=request.content_type,
                ingestion_type=request.ingestion_type,
            )
        )

        if isinstance(metadata, dict):
            metadata.setdefault("search_variant", "smart_search")
            metadata.setdefault("graph_capability", "disabled")
            metadata.setdefault("visibility_scope", visibility_scope)
            metadata.setdefault("content_type_filter", request.content_type)
            metadata.setdefault("ingestion_type_filter", request.ingestion_type)
        
        return {
            "results": results,
            "total": metadata.get("total_count", len(results)),
            "query": request.question,
            "metadata": metadata
        }
    except Exception as e:
        logger.error("Smart search failed", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback")
async def feedback(
    request: FeedbackRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
    else:
        firebase_uid = request.firebase_uid
        if _allow_dev_unverified_auth():
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Pydantic model dump
        data = request.model_dump()
        data['firebase_uid'] = firebase_uid  # Ensure verified UID is used
        
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(None, submit_feedback, data)

        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to save feedback")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# INGESTION ENDPOINTS
# ============================================================================

@app.post("/api/extract-metadata")
async def extract_metadata_endpoint(
    file: UploadFile = File(...),
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # JWT verified, firebase_uid_from_jwt can be used if needed for logging/tracking
    filename = str(getattr(file, "filename", "") or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = os.path.join(upload_dir, f"temp_meta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    
    try:
        with open(temp_path, "wb") as buffer:
             content = await file.read()
             buffer.write(content)
             
        metadata = await get_pdf_metadata(temp_path)
        return metadata
    except Exception as e:
        logger.error("Error extracting metadata", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/api/reports/search")
async def search_reports(
    topic: str,
    limit: int = 20,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
    firebase_uid: str | None = None
):
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        uid = firebase_uid_from_jwt
    else:
        uid = firebase_uid
        if _allow_dev_unverified_auth():
            logger.warning(f"⚠️ Dev mode: Using unverified UID from query: {uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, search_reports_by_topic, uid, topic, limit)
    return {"topic": topic, "count": len(results), "results": results}

from services.report_service import generate_file_report, search_reports_by_topic

def upsert_ingestion_status(
    book_id: str,
    firebase_uid: str,
    status: str,
    file_name: Optional[str] = None,
    chunk_count: Optional[int] = None,
    embedding_count: Optional[int] = None
):
    """Upsert ingestion status for a book/user."""
    if not book_id:
        return
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                merge_sql = """
                MERGE INTO TOMEHUB_INGESTED_FILES target
                USING (SELECT :p_bid as book_id, :p_uid as firebase_uid FROM DUAL) src
                ON (target.BOOK_ID = src.book_id AND target.FIREBASE_UID = src.firebase_uid)
                WHEN MATCHED THEN
                    UPDATE SET
                        STATUS = :p_status,
                        SOURCE_FILE_NAME = COALESCE(:p_file, target.SOURCE_FILE_NAME),
                        CHUNK_COUNT = :p_chunk_count,
                        EMBEDDING_COUNT = :p_embed_count,
                        UPDATED_AT = CURRENT_TIMESTAMP
                WHEN NOT MATCHED THEN
                    INSERT (BOOK_ID, FIREBASE_UID, SOURCE_FILE_NAME, STATUS, CHUNK_COUNT, EMBEDDING_COUNT)
                    VALUES (:p_bid, :p_uid, :p_file, :p_status, :p_chunk_count, :p_embed_count)
                """
                cursor.execute(merge_sql, {
                    "p_bid": book_id,
                    "p_uid": firebase_uid,
                    "p_file": file_name,
                    "p_status": status,
                    "p_chunk_count": chunk_count,
                    "p_embed_count": embedding_count
                })
                conn.commit()
        try:
            from services.change_event_service import emit_change_event
            emit_change_event(
                firebase_uid=firebase_uid,
                item_id=book_id,
                entity_type="INGESTION_STATUS",
                event_type="ingestion.status_changed",
                payload={
                    "status": status,
                    "file_name": file_name,
                    "chunk_count": chunk_count,
                    "embedding_count": embedding_count,
                },
                source_service="app.upsert_ingestion_status",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Failed to upsert ingestion status: {e}")

def fetch_ingestion_status(book_id: str, firebase_uid: str):
    """Fetch ingestion status for a book/user."""
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Phase 4: Compatibility view-first (includes index state summary).
                try:
                    cursor.execute(
                        """
                        SELECT
                            INGESTION_STATUS,
                            SOURCE_FILE_NAME,
                            CHUNK_COUNT,
                            EMBEDDING_COUNT,
                            INGESTION_UPDATED_AT,
                            INDEX_FRESHNESS_STATE,
                            TOTAL_CHUNKS,
                            EMBEDDED_CHUNKS,
                            GRAPH_LINKED_CHUNKS,
                            VECTOR_READY,
                            GRAPH_READY,
                            FULLY_READY,
                            VECTOR_COVERAGE_RATIO,
                            GRAPH_COVERAGE_RATIO,
                            LAST_CHECKED_AT
                        FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM
                        WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid
                        """,
                        {"p_bid": book_id, "p_uid": firebase_uid}
                    )
                    row = cursor.fetchone()
                    if row:
                        return {
                            "status": row[0],
                            "file_name": row[1],
                            "chunk_count": row[2],
                            "embedding_count": row[3],
                            "updated_at": row[4],
                            "item_index_state": {
                                "index_freshness_state": row[5],
                                "total_chunks": row[6],
                                "embedded_chunks": row[7],
                                "graph_linked_chunks": row[8],
                                "vector_ready": row[9],
                                "graph_ready": row[10],
                                "fully_ready": row[11],
                                "vector_coverage_ratio": row[12],
                                "graph_coverage_ratio": row[13],
                                "last_checked_at": row[14].isoformat() if row[14] else None,
                            },
                        }
                except Exception:
                    # View may be unavailable in older envs; fallback to base table.
                    pass

                cursor.execute(
                    """
                    SELECT STATUS, SOURCE_FILE_NAME, CHUNK_COUNT, EMBEDDING_COUNT, UPDATED_AT
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid}
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "status": row[0],
                    "file_name": row[1],
                    "chunk_count": row[2],
                    "embedding_count": row[3],
                    "updated_at": row[4],
                    "item_index_state": None,
                }
    except Exception as e:
        logger.error(f"Failed to fetch ingestion status: {e}")
        return None


def _get_pdf_index_stats(book_id: str, firebase_uid: str) -> Dict[str, int]:
    """
    Returns effective PDF chunk/embedding counts, excluding synthetic metadata-only rows
    that were inserted by non-PDF item sync paths in older versions.
    """
    stats = {"effective_chunks": 0, "effective_embeddings": 0, "raw_chunks": 0}
    if not book_id or not firebase_uid:
        return stats
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS raw_chunks,
                        SUM(
                            CASE
                                WHEN UPPER(DBMS_LOB.SUBSTR(CONTENT_CHUNK, 7, 1)) = 'TITLE: '
                                     AND DBMS_LOB.INSTR(UPPER(CONTENT_CHUNK), CHR(10) || 'AUTHOR:') > 0
                                THEN 1 ELSE 0
                            END
                        ) AS synthetic_chunks,
                        SUM(
                            CASE
                                WHEN VEC_EMBEDDING IS NOT NULL
                                     AND NOT (
                                         UPPER(DBMS_LOB.SUBSTR(CONTENT_CHUNK, 7, 1)) = 'TITLE: '
                                         AND DBMS_LOB.INSTR(UPPER(CONTENT_CHUNK), CHR(10) || 'AUTHOR:') > 0
                                     )
                                THEN 1 ELSE 0
                            END
                        ) AS effective_embeddings
                    FROM TOMEHUB_CONTENT_V2
                    WHERE ITEM_ID = :p_bid
                      AND FIREBASE_UID = :p_uid
                      AND CONTENT_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone() or (0, 0, 0)
                raw_chunks = int(row[0] or 0)
                synthetic_chunks = int(row[1] or 0)
                stats["raw_chunks"] = raw_chunks
                stats["effective_chunks"] = max(0, raw_chunks - synthetic_chunks)
                stats["effective_embeddings"] = int(row[2] or 0)
    except Exception as e:
        logger.error(f"Failed to compute PDF index stats: {e}")
    return stats


def _normalize_title_candidates(raw_title: Optional[str]) -> List[str]:
    """Build conservative title candidates for ingestion-status fallback."""
    if not raw_title:
        return []
    title = str(raw_title).strip()
    if not title:
        return []

    candidates: List[str] = []

    def _add(value: str):
        v = str(value or "").strip()
        if len(v) < 2:
            return
        if v not in candidates:
            candidates.append(v)

    _add(title)
    no_suffix = re.sub(r"\s*\((highlight|insight|note)\)\s*$", "", title, flags=re.IGNORECASE).strip()
    _add(no_suffix)
    if " - " in no_suffix:
        _add(no_suffix.split(" - ", 1)[0].strip())
    if ":" in no_suffix:
        _add(no_suffix.split(":", 1)[0].strip())

    return candidates




def resolve_pdf_book_id_by_title(firebase_uid: str, title: Optional[str]) -> Optional[str]:
    """
    Resolve a likely PDF/EPUB BOOK_ID by fuzzy title match for legacy/migrated IDs.
    Returns the candidate with the largest chunk count.
    """
    title_candidates = _normalize_title_candidates(title)
    if not firebase_uid or not title_candidates:
        return None

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                like_parts = []
                params: Dict[str, Any] = {"p_uid": firebase_uid}
                for idx, candidate in enumerate(title_candidates):
                    key = f"p_title_{idx}"
                    like_parts.append(f"LOWER(TITLE) LIKE LOWER(:{key})")
                    params[key] = f"%{candidate}%"

                where_like = " OR ".join(like_parts)
                sql = f"""
                    SELECT ITEM_ID, COUNT(*) AS chunk_count
                    FROM TOMEHUB_CONTENT_V2
                    WHERE FIREBASE_UID = :p_uid
                      AND CONTENT_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK')
                      AND ({where_like})
                    GROUP BY ITEM_ID
                    ORDER BY chunk_count DESC
                    FETCH FIRST 1 ROWS ONLY
                """
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0])
    except Exception as e:
        logger.error(f"Failed to resolve PDF book id by title: {e}")

    return None


def _parse_csv_tags(raw_tags: Optional[str]) -> List[str]:
    if not raw_tags:
        return []
    return [part.strip() for part in str(raw_tags).replace("\n", ",").split(",") if part.strip()]


def _collect_highlight_tags(highlights: List[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in highlights or []:
        tags = item.tags if hasattr(item, "tags") else item.get("tags", [])
        for tag in tags or []:
            normalized = str(tag or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
    return out


def _safe_upload_filename(upload_file: UploadFile) -> str:
    raw_name = str(getattr(upload_file, "filename", "") or "").strip()
    if not raw_name:
        return "upload.pdf"
    try:
        from werkzeug.utils import secure_filename as _secure_filename
        safe_name = _secure_filename(raw_name)
    except Exception:
        safe_name = raw_name
    safe_name = os.path.basename(str(safe_name or "").replace("\x00", "")).strip()
    return safe_name or "upload.pdf"

def run_ingestion_background(temp_path: str, title: str, author: str, firebase_uid: str, book_id: str, categories: Optional[str] = None):
    """
    Background task wrapper for book ingestion.
    """
    try:
        logger.info(f"Starting background ingestion for: {title}")
        success = ingest_book(temp_path, title, author, firebase_uid, book_id, categories=categories)
        
        if success:
            logger.info(f"Background ingestion success: {title}")
            # Update ingestion status to COMPLETED with counts
            if book_id:
                try:
                    with DatabaseManager.get_read_connection() as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                """
                                SELECT COUNT(*) as chunk_count,
                                       SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END) as embedding_count
                                FROM TOMEHUB_CONTENT_V2
                                WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid
                                """,
                                {"p_bid": book_id, "p_uid": firebase_uid}
                            )
                            row = cursor.fetchone()
                            chunk_count = row[0] if row else 0
                            embedding_count = row[1] if row and row[1] is not None else 0
                    upsert_ingestion_status(
                        book_id=book_id,
                        firebase_uid=firebase_uid,
                        status="COMPLETED",
                        chunk_count=chunk_count,
                        embedding_count=embedding_count
                    )
                except Exception as e:
                    logger.error(f"Failed to update ingestion status counts: {e}")
                else:
                    maybe_trigger_graph_enrichment_async(
                        firebase_uid=firebase_uid,
                        book_id=book_id,
                        reason="pdf_ingest_completed",
                    )
                    maybe_trigger_external_enrichment_async(
                        book_id=book_id,
                        firebase_uid=firebase_uid,
                        title=title,
                        author=author,
                        tags=_parse_csv_tags(categories),
                        mode_hint="INGEST",
                    )

            # Trigger Memory Layer: File Report Generation
            logger.info(f"Generating File Report for {book_id}...")
            report_success = generate_file_report(book_id, firebase_uid)
            if report_success:
                logger.info(f"File Report generated for {title}")
            else:
                logger.error(f"File Report generation failed for {title}")
        else:
            logger.error(f"Background ingestion failed: {title}")
            if book_id:
                upsert_ingestion_status(
                    book_id=book_id,
                    firebase_uid=firebase_uid,
                    status="FAILED"
                )
            
    except Exception as e:
        logger.error(f"Background ingestion exception: {e}")
        if book_id:
            upsert_ingestion_status(
                book_id=book_id,
                firebase_uid=firebase_uid,
                status="FAILED"
            )
        # Note: We rely on ingest_book's internal logic for file cleanup (Task 1.3 will fix that logic next)

@app.post("/api/ingest")
@limiter.limit(settings.RATE_LIMIT_INGEST)
async def ingest_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(...),
    firebase_uid: str = Form(...),
    book_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Log ingestion start
    logger.info("Ingesting file", extra={"upload_filename": file.filename, "title": title})
    
    # Verify firebase_uid from JWT in production, fall back to form data in development
    if firebase_uid_from_jwt:
        verified_firebase_uid = firebase_uid_from_jwt
    else:
        verified_firebase_uid = firebase_uid
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=401, detail="Authentication required")
        else:
            logger.warning(f"⚠️ Dev mode: Using unverified UID from form data for ingestion {file.filename}")
    
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = None
    
    try:
        # Save file
        import uuid
        original_filename = _safe_upload_filename(file)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        temp_path = os.path.join(upload_dir, unique_filename)

        # Upsert ingestion status as PROCESSING (if book_id provided)
        if book_id:
            upsert_ingestion_status(
                book_id=book_id,
                firebase_uid=verified_firebase_uid,
                status="PROCESSING",
                file_name=original_filename
            )

        # Stream file to disk to avoid Memory Spike (OOM)
        with open(temp_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024 * 5) # 5MB chunks
                if not chunk:
                    break
                buffer.write(chunk)
        
        # Add to background tasks
        background_tasks.add_task(
            run_ingestion_background, 
            temp_path, 
            title, 
            author, 
            verified_firebase_uid, 
            book_id,
            categories=tags
        )
        
        return {
            "success": True,
            "message": f"Ingestion started for '{title}'",
            "timestamp": datetime.now().isoformat()
        }
             
    except Exception as e:
        logger.error("Ingestion setup error", extra={"error": str(e), "traceback": traceback.format_exc()})
        # If we failed before adding task, cleanup immediately
        if temp_path and os.path.exists(temp_path):
             os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{book_id}/ingestion-status")
async def get_ingestion_status(
    book_id: str,
    request: Request,
    firebase_uid: Optional[str] = None,
    title: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        verified_firebase_uid = firebase_uid_from_jwt
    else:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=401, detail="Authentication required")
        verified_firebase_uid = firebase_uid or request.headers.get("X-Firebase-UID")
        if not verified_firebase_uid:
            raise HTTPException(status_code=400, detail="firebase_uid is required in development")

    effective_book_id = book_id
    matched_by_title = False
    match_source = "exact_book_id"
    match_confidence = 1.0

    row = fetch_ingestion_status(effective_book_id, verified_firebase_uid)
    if not row and title:
        resolved_book_id = resolve_pdf_book_id_by_title(verified_firebase_uid, title)
        if resolved_book_id:
            effective_book_id = resolved_book_id
            matched_by_title = (resolved_book_id != book_id)
            match_source = "title_fallback"
            match_confidence = 0.6 if matched_by_title else 0.95
            row = fetch_ingestion_status(effective_book_id, verified_firebase_uid)

    freshness = get_index_freshness_state(effective_book_id, verified_firebase_uid)
    if row:
        row_status = str(row.get("status") or "").upper()
        # Guard against stale/incorrect status rows by validating effective PDF-like chunks.
        if row_status == "COMPLETED":
            pdf_stats = _get_pdf_index_stats(effective_book_id, verified_firebase_uid)
            if pdf_stats.get("effective_chunks", 0) <= 0:
                row = None
            else:
                row["chunk_count"] = pdf_stats.get("effective_chunks")
                row["embedding_count"] = pdf_stats.get("effective_embeddings")
        if row:
            item_index_state = row.get("item_index_state") or {}
            return {
                "status": row.get("status"),
                "file_name": row.get("file_name"),
                "chunk_count": int(row["chunk_count"]) if row.get("chunk_count") is not None else None,
                "embedding_count": int(row["embedding_count"]) if row.get("embedding_count") is not None else None,
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
                "resolved_book_id": effective_book_id,
                "matched_by_title": matched_by_title,
                "match_source": match_source,
                "match_confidence": match_confidence,
                "item_index_state": item_index_state,
                "index_freshness_state": freshness.get("index_freshness_state"),
                "index_freshness": freshness,
            }

    # Fallback: check if content exists for this book
    try:
        pdf_stats = _get_pdf_index_stats(effective_book_id, verified_firebase_uid)
        if pdf_stats.get("effective_chunks", 0) > 0:
            return {
                "status": "COMPLETED",
                "file_name": None,
                "chunk_count": int(pdf_stats.get("effective_chunks", 0)),
                "embedding_count": int(pdf_stats.get("effective_embeddings", 0)),
                "updated_at": datetime.now().isoformat(),
                "resolved_book_id": effective_book_id,
                "matched_by_title": matched_by_title,
                "match_source": "content_fallback",
                "match_confidence": 0.5,
                "item_index_state": None,
                "index_freshness_state": freshness.get("index_freshness_state"),
                "index_freshness": freshness,
            }
    except Exception as e:
        logger.error(f"Fallback ingestion status check failed: {e}")

    return {
        "status": "NOT_FOUND",
        "file_name": None,
        "chunk_count": None,
        "embedding_count": None,
        "updated_at": None,
        "resolved_book_id": effective_book_id,
        "matched_by_title": matched_by_title,
        "match_source": match_source,
        "match_confidence": match_confidence if row else (0.0 if effective_book_id == book_id else 0.3),
        "item_index_state": None,
        "index_freshness_state": freshness.get("index_freshness_state"),
        "index_freshness": freshness,
    }


def _run_calculate_graph_stats_background():
    import subprocess
    import sys
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'calculate_graph_stats.py')
        logger.info(f"Triggering background graph centrality calculation: {script_path}")
        # Run the script as a separate process so it doesn't block the API thread
        subprocess.Popen([sys.executable, script_path])
    except Exception as e:
        logger.error(f"Failed to trigger graph centrality calculation: {e}", exc_info=True)


@app.post("/api/admin/recalculate_graph")
async def recalculate_graph_endpoint(
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    """
    Triggers the graph centrality recalculation script in the background.
    Useful after bulk ingesting new books to update discovery bridges.
    """
    if not firebase_uid_from_jwt and not _allow_dev_unverified_auth():
        raise HTTPException(status_code=401, detail="Authentication required")
        
    background_tasks.add_task(_run_calculate_graph_stats_background)
    return {"success": True, "message": "Graph centrality calculation started in background."}


@app.post("/api/admin/external-kb/backfill/start")
async def start_external_kb_backfill(
    request: Request,
    all_users: bool = False,
    firebase_uid: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    if firebase_uid_from_jwt:
        verified_uid = firebase_uid_from_jwt
    else:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=401, detail="Authentication required")
        verified_uid = firebase_uid or request.query_params.get("firebase_uid")
        if not verified_uid:
            raise HTTPException(status_code=400, detail="firebase_uid is required in development")

    if all_users and settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="all_users backfill is disabled in production")

    scope_uid = None if all_users else verified_uid
    status = start_external_kb_backfill_async(scope_uid=scope_uid)
    return {"success": True, "status": status}


@app.get("/api/admin/external-kb/backfill/status")
async def external_kb_backfill_status(
    request: Request,
    firebase_uid: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    if not firebase_uid_from_jwt and settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=401, detail="Authentication required")
    if not firebase_uid_from_jwt and settings.ENVIRONMENT != "production":
        _ = firebase_uid or request.query_params.get("firebase_uid")
    return {"success": True, "status": get_external_kb_backfill_status()}


import time

@app.get("/api/library/items")
async def list_library_items_endpoint(
    request: Request,
    limit: int = 1000,
    cursor: Optional[str] = None,
    types: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        parsed_types = [t.strip() for t in str(types or "").split(",") if t.strip()] if types else None
        
        start_time = time.time()
        result = list_library_items(
            verified_uid,
            limit=limit,
            cursor=cursor,
            types=parsed_types,
        )
        duration = time.time() - start_time
        logger.info(f"library list completed in {duration:.4f}s for user {verified_uid}")
        
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"library list failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/library/items/{item_id}")
async def upsert_library_item_endpoint(
    item_id: str,
    payload: LibraryItemUpsertRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        result = upsert_library_item(verified_uid, item_id, payload.model_dump())
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"library upsert failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/library/items/{item_id}")
async def patch_library_item_endpoint(
    item_id: str,
    payload: LibraryItemPatchRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        result = patch_library_item(verified_uid, item_id, payload.patch or {})
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"library patch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/library/items/{item_id}")
async def delete_library_item_endpoint(
    item_id: str,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        result = delete_library_item(verified_uid, item_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Delete failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"library delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/library/items/bulk-delete")
async def bulk_delete_library_items_endpoint(
    payload: LibraryBulkDeleteRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        result = bulk_delete_library_items(verified_uid, payload.item_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"library bulk delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/library/personal-note-folders")
async def list_personal_note_folders_endpoint(
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        folders = list_personal_note_folders(verified_uid)
        return {"success": True, "folders": folders}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"folder list failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/library/personal-note-folders/{folder_id}")
async def upsert_personal_note_folder_endpoint(
    folder_id: str,
    payload: PersonalNoteFolderUpsertRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        folder = upsert_personal_note_folder(verified_uid, folder_id, payload.model_dump())
        return {"success": True, "folder": folder}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"folder upsert failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/library/personal-note-folders/{folder_id}")
async def patch_personal_note_folder_endpoint(
    folder_id: str,
    payload: PersonalNoteFolderPatchRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        folder = patch_personal_note_folder(verified_uid, folder_id, payload.model_dump(exclude_none=True))
        return {"success": True, "folder": folder}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"folder patch failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/library/personal-note-folders/{folder_id}")
async def delete_personal_note_folder_endpoint(
    folder_id: str,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(request, firebase_uid_from_jwt)
        return delete_personal_note_folder(verified_uid, folder_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"folder delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/add-item")
async def add_item_endpoint(
    request: AddItemRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        # Verify firebase_uid from JWT in production, fall back to request body in development
        if firebase_uid_from_jwt:
            verified_firebase_uid = firebase_uid_from_jwt
        else:
            verified_firebase_uid = request.firebase_uid
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=401, detail="Authentication required")
            else:
                logger.warning(f"⚠️ Dev mode: Using unverified UID from request body for add-item")
        
        success = ingest_text_item(
            text=request.text,
            title=request.title,
            author=request.author,
            source_type=request.type,
            firebase_uid=verified_firebase_uid,
            book_id=request.book_id,
            page_number=request.page_number,
            chunk_type=request.chunk_type,
            chunk_index=request.chunk_index,
            comment=request.comment,
            tags=request.tags
        )
        if success:
            if request.book_id:
                maybe_trigger_graph_enrichment_async(
                    firebase_uid=verified_firebase_uid,
                    book_id=request.book_id,
                    reason="add_item",
                )
                maybe_trigger_external_enrichment_async(
                    book_id=request.book_id,
                    firebase_uid=verified_firebase_uid,
                    title=request.title,
                    author=request.author,
                    tags=request.tags,
                    mode_hint="INGEST",
                )
                freshness = get_index_freshness_state(request.book_id, verified_firebase_uid)
            else:
                freshness = None
            return {
                "success": True,
                "message": "Item added",
                "metadata": {
                    "index_freshness_state": freshness.get("index_freshness_state") if freshness else None,
                    "index_freshness": freshness,
                },
            }
        raise HTTPException(status_code=500, detail="Failed to add item")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/books/{book_id}/sync-highlights")
async def sync_highlights_endpoint(
    book_id: str,
    request: HighlightSyncRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        if firebase_uid_from_jwt:
            verified_firebase_uid = firebase_uid_from_jwt
        else:
            verified_firebase_uid = request.firebase_uid
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=401, detail="Authentication required")
            else:
                logger.warning("⚠️ Dev mode: Using unverified UID for sync-highlights")

        result = sync_highlights_for_item(
            firebase_uid=verified_firebase_uid,
            book_id=book_id,
            title=request.title,
            author=request.author,
            highlights=[h.model_dump() for h in request.highlights],
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Sync failed"))
        try:
            maybe_trigger_graph_enrichment_async(
                firebase_uid=verified_firebase_uid,
                book_id=book_id,
                reason="sync_highlights",
            )
        except Exception as e:
            logger.warning(f"Graph enrichment trigger skipped after highlight sync: {e}")
        try:
            maybe_trigger_external_enrichment_async(
                book_id=book_id,
                firebase_uid=verified_firebase_uid,
                title=request.title,
                author=request.author,
                tags=_collect_highlight_tags(request.highlights),
                mode_hint="INGEST",
            )
        except Exception as e:
            logger.warning(f"External enrichment trigger skipped after highlight sync: {e}")
        try:
            freshness = get_index_freshness_state(book_id, verified_firebase_uid)
            result["index_freshness_state"] = freshness.get("index_freshness_state")
            result["index_freshness"] = freshness
        except Exception as e:
            logger.warning(f"Index freshness read failed after highlight sync: {e}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/notes/{book_id}/sync-personal-note")
async def sync_personal_note_endpoint(
    book_id: str,
    request: PersonalNoteSyncRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        if firebase_uid_from_jwt:
            verified_firebase_uid = firebase_uid_from_jwt
        else:
            verified_firebase_uid = request.firebase_uid
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=401, detail="Authentication required")
            logger.warning("⚠️ Dev mode: Using unverified UID for sync-personal-note")

        result = sync_personal_note_for_item(
            firebase_uid=verified_firebase_uid,
            book_id=book_id,
            title=request.title,
            author=request.author,
            content=request.content,
            tags=request.tags,
            category=request.category or "PRIVATE",
            delete_only=bool(request.delete_only),
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Sync failed"))
        try:
            maybe_trigger_graph_enrichment_async(
                firebase_uid=verified_firebase_uid,
                book_id=book_id,
                reason="sync_personal_note",
            )
        except Exception as e:
            logger.warning(f"Graph enrichment trigger skipped after personal note sync: {e}")
        try:
            maybe_trigger_external_enrichment_async(
                book_id=book_id,
                firebase_uid=verified_firebase_uid,
                title=request.title,
                author=request.author,
                tags=request.tags,
                mode_hint="INGEST",
            )
        except Exception as e:
            logger.warning(f"External enrichment trigger skipped after personal note sync: {e}")
        try:
            freshness = get_index_freshness_state(book_id, verified_firebase_uid)
            result["index_freshness_state"] = freshness.get("index_freshness_state")
            result["index_freshness"] = freshness
        except Exception as e:
            logger.warning(f"Index freshness read failed after personal note sync: {e}")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/resources/{book_id}/purge")
async def purge_resource_endpoint(
    book_id: str,
    request: PurgeResourceRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        if firebase_uid_from_jwt:
            verified_firebase_uid = firebase_uid_from_jwt
        else:
            verified_firebase_uid = request.firebase_uid
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=401, detail="Authentication required")
            logger.warning("⚠️ Dev mode: Using unverified UID for resource purge")

        result = purge_item_content(
            firebase_uid=verified_firebase_uid,
            book_id=book_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Purge failed"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/migrate_bulk")
async def migrate_bulk_endpoint(
    request: BatchMigrateRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        # Verify firebase_uid from JWT in production, fall back to request body in development
        if firebase_uid_from_jwt:
            verified_firebase_uid = firebase_uid_from_jwt
        else:
            verified_firebase_uid = request.firebase_uid
            if settings.ENVIRONMENT == "production":
                raise HTTPException(status_code=401, detail="Authentication required")
            else:
                logger.warning(f"⚠️ Dev mode: Using unverified UID from request body for bulk migration")
        
        result = process_bulk_items_logic(request.items, verified_firebase_uid)
        return {
            "success": True,
            "processed": len(request.items),
            "results": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("Starting FastAPI Server on port 8000 (DIRECT)...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
