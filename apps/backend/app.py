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
from urllib.parse import quote
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, BackgroundTasks, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Annotated, Optional, List, Any, Dict
import traceback
import hashlib

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Models
from models.request_models import (
    SearchRequest, SearchResponse, IngestRequest, 
    FeedbackRequest, AddItemRequest, BatchMigrateRequest,
    ChatRequest, ChatResponse, HighlightSyncRequest, ComparisonRequest, PersonalNoteSyncRequest, PurgeResourceRequest,
    MemoryProfileRefreshRequest,
    LibraryItemUpsertRequest, LibraryItemPatchRequest, LibraryBulkDeleteRequest,
    PersonalNoteFolderUpsertRequest, PersonalNoteFolderPatchRequest,
)
from middleware.auth_middleware import verify_firebase_token
from middleware.admin_middleware import require_admin

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
from services.tmdb_service import search_tmdb_media, get_tmdb_media_details
from services.index_freshness_service import get_index_freshness_state, maybe_trigger_graph_enrichment_async
from services.external_kb_service import (
    get_external_kb_backfill_status,
    maybe_trigger_external_enrichment_async,
    start_external_kb_backfill_async,
)
from services.epistemic_distribution_service import get_epistemic_distribution
from services.feedback_service import submit_feedback
from services.pdf_metadata_service import get_pdf_metadata
from services.ai_service import (
    enrich_book_async, 
    generate_tags_async, 
    verify_cover_async, 
    analyze_highlights_async, 
    search_resources_async,
    stream_enrichment
)
from services.api_route_support_service import (
    execute_chat_request,
    execute_search_request,
    fetch_realtime_poll_payload,
)
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
from services.ingestion_status_service import (
    delete_ingested_file_row,
    fetch_ingestion_status as fetch_ingestion_status_record,
    get_pdf_record,
    get_user_storage_bytes,
    is_active_parse_status,
    upsert_ingestion_status as upsert_ingestion_status_record,
)
from services.object_storage_service import (
    cleanup_pdf_artifacts,
    ObjectStorageConfigError,
    compute_sha256,
    get_storage_quota_summary,
    stream_object,
    upload_pdf,
)
from services.pdf_async_ingestion_service import mark_pdf_for_cleanup, pdf_async_ingestion_manager

# Configure Sentry - REPLACED BY LOKI (Standard Logging)
# (Sentry code removed)

# Configure Logging (Standardized)
from utils.logger import get_logger

logger = get_logger("tomehub_api")
logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))


def get_verified_uid(uid_from_jwt: Optional[str]) -> str:
    """
    Authoritative UID resolver for TomeHub.
    Requires a verified JWT-derived UID for protected endpoints.
    """
    if uid_from_jwt:
        return uid_from_jwt

    raise HTTPException(status_code=401, detail="Authentication required")


async def get_pdf_request_uid(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header:
        uid_from_jwt = await verify_firebase_token(request)
        return get_verified_uid(uid_from_jwt)

    auth_token = str(request.query_params.get("auth_token") or "").strip()
    if auth_token:
        try:
            from firebase_admin import auth as firebase_auth
        except ImportError as exc:
            logger.error("firebase-admin is not installed for PDF access: %s", exc)
            raise HTTPException(status_code=500, detail="Authentication service unavailable")

        if not settings.FIREBASE_READY:
            raise HTTPException(status_code=500, detail="Authentication service unavailable")

        try:
            decoded_token = firebase_auth.verify_id_token(auth_token)
            uid = str(decoded_token.get("uid") or "").strip()
            if not uid:
                raise HTTPException(status_code=401, detail="Invalid token claims")
            return uid
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("PDF auth_token verification failed: %s", exc)
            raise HTTPException(status_code=401, detail="Authentication verification failed")

    return get_verified_uid(None)


def _to_iso_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def _build_content_disposition(filename: str) -> str:
    safe_ascii = re.sub(r'[^A-Za-z0-9._-]+', "_", str(filename or "document.pdf")).strip("._") or "document.pdf"
    return f"inline; filename=\"{safe_ascii}\"; filename*=UTF-8''{quote(str(filename or safe_ascii))}"


def _raise_internal_server_error(
    log_message: str,
    exc: Exception,
    *,
    detail: str = "Internal server error",
) -> None:
    logger.error(log_message, extra={"error": str(exc), "traceback": traceback.format_exc()})
    raise HTTPException(status_code=500, detail=detail)


def _ensure_media_library_enabled() -> None:
    if not bool(getattr(settings, "MEDIA_LIBRARY_ENABLED", False)):
        raise HTTPException(status_code=404, detail="Media library is disabled")


def _ensure_media_resource_type_allowed(resource_type: Optional[str]) -> None:
    rt = str(resource_type or "").strip().upper()
    if rt in {"MOVIE", "SERIES"}:
        _ensure_media_library_enabled()



def _validate_cors_origins(origins: list[str]) -> list[str]:
    normalized = [o.strip() for o in origins if str(o).strip()]
    if not normalized:
        raise ValueError("ALLOWED_ORIGINS cannot be empty")
    if "*" in normalized:
        raise ValueError("SECURITY: '*' is not allowed when allow_credentials=True")

    for origin in normalized:
        if origin.startswith("https://"):
            continue
        # Allow localhost/127/0.0.0.0 regardless of environment — admin explicitly set these
        if origin.startswith(
            ("http://localhost", "http://127.0.0.1", "http://0.0.0.0")
        ):
            continue
        raise ValueError(f"Invalid CORS origin: {origin}")
    return normalized


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
                raise
            except Exception as e:
                logger.error(f"Error in metrics updater: {e}")
                await asyncio.sleep(10)

    metrics_task = asyncio.create_task(metrics_background_updater())
    app.state.metrics_task = metrics_task
    logger.info("✓ Metrics updater started (10s interval)")
    
    try:
        await pdf_async_ingestion_manager.startup()
        logger.info("Async PDF ingestion manager started")
    except Exception as e:
        logger.error(f"Failed to start async PDF ingestion manager: {e}")

    yield
    # Shutdown: Clean up
    logger.info("🛑 Shutdown: Cancelling background tasks...")
    memory_task.cancel()
    metrics_task.cancel()
    try:
        await asyncio.gather(memory_task, metrics_task, return_exceptions=True)
    except asyncio.CancelledError:
        raise
    
    try:
        await pdf_async_ingestion_manager.shutdown()
    except Exception as e:
        logger.error(f"Failed to shutdown async PDF ingestion manager cleanly: {e}")

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

# Include External API Router (isolated read-only access)
from routes import external_api_routes
app.include_router(external_api_routes.router)
logger.info("Router registered", extra={"route_count": len(external_api_routes.router.routes)})

# Prometheus Instrumentation (must be AFTER all routers are added)
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/")
async def health_check():
    """
    Basic health check endpoint to verify API availability.
    """
    return {
        "status": "online",
        "service": "TomeHub API (FastAPI)",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/realtime/poll", responses={
    204: {"description": "No content, compact poll optimization"},
    401: {"description": "Authentication required"}
})
async def realtime_poll(
    request: Request,
    since_ms: int = 0,
    limit: int = 100,
    firebase_uid: Optional[str] = None,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    """
    Fast polling endpoint for multi-device UX consistency.
    Returns coarse-grained change events since client timestamp.
    """
    verified_uid = get_verified_uid(firebase_uid_from_jwt)
    compact_poll = request.headers.get("x-th-compact-poll") == "1"
    payload = fetch_realtime_poll_payload(
        firebase_uid=verified_uid,
        since_ms=since_ms,
        limit=limit,
    )
    if compact_poll and int(payload.get("count") or 0) == 0:
        return Response(status_code=204)
    return payload



# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@app.post("/api/search", response_model=SearchResponse, responses={
    401: {"description": "Authentication required"},
    500: {"description": "Search failed or internal server error"}
})
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def search(
    request: Request,
    search_request: SearchRequest,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    logger.info(f"Using JWT-verified UID: {firebase_uid}")
    
    # Log search start
    logger.info(
        "Search started", 
        extra={"uid": firebase_uid, "question": search_request.question}
    )
    _ensure_media_resource_type_allowed(search_request.resource_type)
    
    try:
        return await execute_search_request(
            search_request=search_request,
            firebase_uid=firebase_uid,
            generate_answer_fn=generate_answer,
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Search failed", e, detail="Search failed")

@app.post("/api/chat", response_model=ChatResponse, responses={
    401: {"description": "Authentication required"},
    500: {"description": "Chat failed or internal server error"}
})
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat_endpoint(
    request: Request,
    chat_request: ChatRequest,
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    """
    Stateful Chat Endpoint (LogosChat - Layer 3).
    Orchestrates session, history, and RAG search.
    """
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    logger.info(f"Using JWT-verified UID: {firebase_uid}")
    
    logger.info(
        "Chat started",
        extra={"session_id": chat_request.session_id, "uid": firebase_uid}
    )
    _ensure_media_resource_type_allowed(chat_request.resource_type)
    
    try:
        from services.chat_history_service import (
            create_session, add_message, get_session_context, summarize_session_history
        )
        from services.memory_profile_service import get_memory_context_snippet, refresh_memory_profile
        return await execute_chat_request(
            chat_request=chat_request,
            firebase_uid=firebase_uid,
            background_tasks=background_tasks,
            generate_answer_fn=generate_answer,
            get_rag_context_fn=get_rag_context,
            generate_evaluated_answer_fn=generate_evaluated_answer,
            create_session_fn=create_session,
            add_message_fn=add_message,
            get_session_context_fn=get_session_context,
            summarize_session_history_fn=summarize_session_history,
            get_memory_context_snippet_fn=get_memory_context_snippet,
            refresh_memory_profile_fn=refresh_memory_profile,
        )
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Chat failed", e, detail="Chat failed")


@app.get("/api/analytics/ingested-books", responses={
    401: {"description": "Authentication required"},
    500: {"description": "Internal server error"}
})
async def get_ingested_books(
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    """
    Returns list of book_ids that have ingested PDF content for the user.
    """
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)

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
        _raise_internal_server_error("Ingested books endpoint failed", e, detail="Failed to fetch ingested books")


@app.get("/api/analytics/epistemic-distribution", responses={
    401: {"description": "Authentication required"}
})
async def get_epistemic_distribution_endpoint(
    book_id: Optional[str] = None,
    limit: int = 250,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: get_epistemic_distribution(firebase_uid=firebase_uid, book_id=book_id, limit=limit),
    )
    return result

@app.get("/api/analytics/concordance", responses={
    401: {"description": "Unauthorized Access"}
})
async def get_concordance(
    book_id: str,
    term: str,
    limit: int = 50,
    offset: int = 0,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
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
        _raise_internal_server_error("Concordance endpoint failed", e, detail="Failed to fetch concordance")


@app.get("/api/analytics/distribution", responses={
    401: {"description": "Unauthorized Access"}
})
async def get_distribution(
    book_id: str,
    term: str,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
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
        _raise_internal_server_error("Distribution endpoint failed", e, detail="Failed to fetch distribution")


@app.post("/api/analytics/compare", responses={
    401: {"description": "Unauthorized Access"}
})
async def get_comparative_stats_endpoint(
    request: ComparisonRequest,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
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
        _raise_internal_server_error("Comparison endpoint failed", e, detail="Failed to compare analytics")


@app.post("/api/smart-search", responses={
    401: {"description": "Authentication required"},
    500: {"description": "Smart search failed"}
})
async def perform_search(
    request: SearchRequest,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    """
    Pure weighted search (Search - Layer 2).
    """
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    
    try:
        from services.search_system.mix_policy import resolve_result_mix_policy
        from services.smart_search_service import perform_search
        from functools import partial
        visibility_scope = "all" if request.include_private_notes else request.visibility_scope
        requested_mix_policy = "lexical_then_semantic_tail" if request.search_surface == "CORE" else None
        result_mix_policy = resolve_result_mix_policy(
            requested_mix_policy,
            fusion_mode=settings.RETRIEVAL_FUSION_MODE,
            default_policy=settings.SEARCH_DEFAULT_RESULT_MIX_POLICY,
        )

        loop = asyncio.get_running_loop()
        results, metadata = await loop.run_in_executor(
            None,
            partial(
                perform_search,
                request.question, 
                firebase_uid, 
                limit=request.limit, 
                offset=request.offset,
                result_mix_policy=result_mix_policy,
                semantic_tail_cap=settings.SEARCH_SMART_SEMANTIC_TAIL_CAP,
                visibility_scope=visibility_scope,
                search_surface=request.search_surface,
                content_type=request.content_type,
                ingestion_type=request.ingestion_type,
            )
        )

        if isinstance(metadata, dict):
            metadata.setdefault("search_variant", "smart_search")
            metadata.setdefault("graph_capability", "disabled")
            metadata.setdefault("visibility_scope", visibility_scope)
            metadata.setdefault("search_surface", request.search_surface)
            metadata.setdefault("content_type_filter", request.content_type)
            metadata.setdefault("ingestion_type_filter", request.ingestion_type)
        
        return {
            "results": results,
            "total": metadata.get("total_count", len(results)),
            "query": request.question,
            "metadata": metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Smart search failed", e, detail="Smart search failed")

@app.post("/api/feedback", responses={
    401: {"description": "Authentication required"},
    500: {"description": "Feedback submission failed"}
})
async def feedback(
    request: FeedbackRequest,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    
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
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Feedback submission failed", e, detail="Failed to save feedback")

# ============================================================================
# INGESTION ENDPOINTS
# ============================================================================

@app.post("/api/extract-metadata")
async def extract_metadata_endpoint(
    file: UploadFile = File(...),
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
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
        _raise_internal_server_error("Error extracting metadata", e, detail="Failed to extract PDF metadata")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/api/reports/search", responses={
    401: {"description": "Authentication required"}
})
async def search_reports(
    topic: str,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
    limit: int = 20,
    firebase_uid: str | None = None
):
    uid = get_verified_uid(firebase_uid_from_jwt)

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
    embedding_count: Optional[int] = None,
    **extra_fields: Any,
):
    """Upsert ingestion status for a book/user."""
    if not book_id:
        return
    try:
        upsert_ingestion_status_record(
            book_id,
            firebase_uid,
            file_name=file_name,
            status=status,
            chunk_count=chunk_count,
            embedding_count=embedding_count,
            **extra_fields,
        )
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
                    **extra_fields,
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
        item_index_state = None
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
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
                        item_index_state = {
                            "index_freshness_state": row[0],
                            "total_chunks": row[1],
                            "embedded_chunks": row[2],
                            "graph_linked_chunks": row[3],
                            "vector_ready": row[4],
                            "graph_ready": row[5],
                            "fully_ready": row[6],
                            "vector_coverage_ratio": row[7],
                            "graph_coverage_ratio": row[8],
                            "last_checked_at": row[9].isoformat() if row[9] else None,
                        }
        except Exception:
            item_index_state = None

        record = fetch_ingestion_status_record(book_id, firebase_uid)
        if not record:
            return None
        record["item_index_state"] = item_index_state
        return record
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


def _fetch_library_item_title(book_id: str, firebase_uid: str) -> Optional[str]:
    if not book_id or not firebase_uid:
        return None
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT TITLE
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE ITEM_ID = :p_bid
                      AND FIREBASE_UID = :p_uid
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0]).strip() or None
    except Exception as e:
        logger.error(f"Failed to fetch library item title for PDF access fallback: {e}")
    return None


def _resolve_pdf_access_book_id(
    book_id: str,
    firebase_uid: str,
    title: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve the book id that should be used for PDF access.
    Prefers an exact ingestion row with object storage, then falls back to
    same-title PDF-like items that actually have a readable object_key.
    """
    if not book_id or not firebase_uid:
        return None

    exact_record = get_pdf_record(book_id, firebase_uid)
    if exact_record and exact_record.get("object_key"):
        return book_id

    effective_title = title or _fetch_library_item_title(book_id, firebase_uid)
    title_candidates = _normalize_title_candidates(effective_title)
    if not title_candidates:
        return None

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                like_parts = []
                params: Dict[str, Any] = {"p_uid": firebase_uid}
                for idx, candidate in enumerate(title_candidates):
                    key = f"p_title_{idx}"
                    like_parts.append(f"LOWER(c.TITLE) LIKE LOWER(:{key})")
                    params[key] = f"%{candidate}%"

                where_like = " OR ".join(like_parts)
                cursor.execute(
                    f"""
                    SELECT f.BOOK_ID, COUNT(*) AS chunk_count, MAX(f.UPDATED_AT) AS last_updated
                    FROM TOMEHUB_INGESTED_FILES f
                    JOIN TOMEHUB_CONTENT_V2 c
                      ON c.ITEM_ID = f.BOOK_ID
                     AND c.FIREBASE_UID = f.FIREBASE_UID
                    WHERE f.FIREBASE_UID = :p_uid
                      AND NVL(f.OBJECT_KEY, '') <> ''
                      AND c.CONTENT_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK')
                      AND ({where_like})
                    GROUP BY f.BOOK_ID
                    ORDER BY chunk_count DESC, last_updated DESC NULLS LAST
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    params,
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0]).strip() or None
    except Exception as e:
        logger.error(f"Failed to resolve PDF access book id by title: {e}")

    return None


def _resolve_pdf_access_record(
    book_id: str,
    firebase_uid: str,
    title: Optional[str] = None,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    access_book_id = _resolve_pdf_access_book_id(book_id, firebase_uid, title=title)
    if not access_book_id:
        return None, None
    return access_book_id, get_pdf_record(access_book_id, firebase_uid)


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


def _has_active_pdf_ingestion(book_id: str, firebase_uid: str) -> bool:
    record = fetch_ingestion_status(book_id, firebase_uid)
    if not record:
        return False
    return is_active_parse_status(record.get("status"), record.get("parse_status"))

def run_ingestion_background(temp_path: str, title: str, author: str, firebase_uid: str, book_id: str, categories: Optional[str] = None):
    """
    Background task wrapper for legacy book ingestion.

    Note:
    - PDF uploads on `/api/ingest` now use the PDF_V2 async path.
    - This wrapper remains only for legacy/manual ingestion flows that still
      call `ingest_book()`.
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
    firebase_uid: Optional[str] = Form(None),
    book_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Log ingestion start
    logger.info("Ingesting file", extra={"upload_filename": file.filename, "title": title})
    
    verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    temp_path = None
    
    try:
        # Save file
        import uuid
        original_filename = _safe_upload_filename(file)
        unique_filename = f"{uuid.uuid4()}_{original_filename}"
        temp_path = os.path.join(upload_dir, unique_filename)

        # Stream file to disk to avoid Memory Spike (OOM)
        with open(temp_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024 * 5) # 5MB chunks
                if not chunk:
                    break
                buffer.write(chunk)

        file_ext = os.path.splitext(original_filename)[1].lower()
        if file_ext == ".pdf":
            effective_book_id = book_id or unique_filename.split("_", 1)[0]
            if _has_active_pdf_ingestion(effective_book_id, verified_firebase_uid):
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                    temp_path = None
                raise HTTPException(
                    status_code=409,
                    detail="Bu kitap icin halihazirda bir PDF ingestion calisiyor. Once mevcut run tamamlanmali.",
                )
            size_bytes = os.path.getsize(temp_path)
            current_storage = get_user_storage_bytes(
                verified_firebase_uid,
                exclude_book_id=effective_book_id,
            )
            quota = get_storage_quota_summary(current_storage, size_bytes)
            storage_warning = None
            if quota["block"]:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                    temp_path = None
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"PDF storage limit yaklasti. Su an {quota['storage_used_gb']} GB / "
                        f"{quota['storage_limit_gb']} GB kullanilacak."
                    ),
                )
            if quota["warn"]:
                storage_warning = (
                    f"PDF storage kullanimı {quota['storage_used_gb']} GB / "
                    f"{quota['storage_limit_gb']} GB seviyesine yaklasti."
                )

            sha256_hex = compute_sha256(temp_path)
            upload_info = upload_pdf(temp_path, verified_firebase_uid, effective_book_id, sha256_hex)
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                temp_path = None

            upsert_ingestion_status(
                book_id=effective_book_id,
                firebase_uid=verified_firebase_uid,
                status="PROCESSING",
                file_name=original_filename,
                storage_backend="OCI_OBJECT_STORAGE",
                bucket_name=str(upload_info["bucket_name"]),
                object_key=str(upload_info["object_key"]),
                size_bytes=int(upload_info["size_bytes"]),
                storage_status="STORED",
                parse_path="PDF_V2",
                parse_status="QUEUED",
                routing_metrics_json=json.dumps({}),
                storage_warning=storage_warning,
                content_type="PDF",
                mime_type="application/pdf",
                sha256=str(upload_info["sha256"]),
                error_message=None,
            )

            try:
                await pdf_async_ingestion_manager.enqueue_pdf_processing(
                    book_id=effective_book_id,
                    firebase_uid=verified_firebase_uid,
                    title=title,
                    author=author,
                    categories=tags,
                    bucket_name=str(upload_info["bucket_name"]),
                    object_key=str(upload_info["object_key"]),
                )
            except RuntimeError:
                cleanup_pdf_artifacts(
                    str(upload_info["bucket_name"]),
                    str(upload_info["object_key"]),
                    "",
                )
                delete_ingested_file_row(effective_book_id, verified_firebase_uid)
                raise HTTPException(
                    status_code=409,
                    detail="Bu kitap icin halihazirda bir PDF ingestion calisiyor. Once mevcut run tamamlanmali.",
                )

            return {
                "success": True,
                "message": f"Ingestion started for '{title}'",
                "timestamp": datetime.now().isoformat(),
                "storage_warning": storage_warning,
                "storage_used_gb": quota["storage_used_gb"],
                "storage_limit_gb": quota["storage_limit_gb"],
                "pdf_available": True,
                "parse_status": "QUEUED",
            }

        if book_id:
            upsert_ingestion_status(
                book_id=book_id,
                firebase_uid=verified_firebase_uid,
                status="PROCESSING",
                file_name=original_filename
            )

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
             
    except HTTPException:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    except Exception as e:
        # If we failed before adding task, cleanup immediately
        if temp_path and os.path.exists(temp_path):
             os.remove(temp_path)
        _raise_internal_server_error("Ingestion setup error", e, detail="Failed to start ingestion")

@app.get("/api/books/{book_id}/ingestion-status")
async def get_ingestion_status(
    book_id: str,
    request: Request,
    firebase_uid: Optional[str] = None,
    title: Optional[str] = None,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)

    effective_book_id = book_id
    matched_by_title = False
    match_source = "exact_book_id"
    match_confidence = 1.0
    pdf_open_book_id: Optional[str] = None

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
        if row_status in {"COMPLETED", "FAILED"}:
            pdf_stats = _get_pdf_index_stats(effective_book_id, verified_firebase_uid)
            effective_chunks = int(pdf_stats.get("effective_chunks", 0) or 0)
            effective_embeddings = int(pdf_stats.get("effective_embeddings", 0) or 0)
            if row_status == "COMPLETED" and effective_chunks <= 0:
                row = None
            elif effective_chunks > 0:
                row["chunk_count"] = effective_chunks
                row["embedding_count"] = effective_embeddings
                if row_status == "FAILED":
                    row["status"] = "COMPLETED"
                    row["updated_at"] = datetime.now()
                    upsert_ingestion_status(
                        book_id=effective_book_id,
                        firebase_uid=verified_firebase_uid,
                        status="COMPLETED",
                        file_name=row.get("file_name"),
                        chunk_count=effective_chunks,
                        embedding_count=effective_embeddings,
                    )
        if row:
            pdf_open_book_id = _resolve_pdf_access_book_id(
                effective_book_id,
                verified_firebase_uid,
                title=title,
            )
            row["pdf_available"] = bool(row.get("pdf_available") or pdf_open_book_id)
            item_index_state = row.get("item_index_state") or {}
            return {
                "status": row.get("status"),
                "file_name": row.get("file_name"),
                "chunk_count": int(row["chunk_count"]) if row.get("chunk_count") is not None else None,
                "embedding_count": int(row["embedding_count"]) if row.get("embedding_count") is not None else None,
                "updated_at": _to_iso_datetime(row.get("updated_at")),
                "parse_path": row.get("parse_path"),
                "parse_status": row.get("parse_status"),
                "pdf_available": bool(row.get("pdf_available")),
                "storage_warning": row.get("storage_warning"),
                "size_bytes": int(row["size_bytes"]) if row.get("size_bytes") is not None else None,
                "storage_status": row.get("storage_status"),
                "error_message": row.get("error_message"),
                "classification_route": row.get("classification_route"),
                "parse_engine": row.get("parse_engine"),
                "fallback_engine": row.get("fallback_engine"),
                "classifier_metrics_json": row.get("classifier_metrics_json"),
                "quality_metrics_json": row.get("quality_metrics_json"),
                "routing_metrics_json": row.get("routing_metrics_json"),
                "parse_time_ms": int(row["parse_time_ms"]) if row.get("parse_time_ms") is not None else None,
                "pages": int(row["pages"]) if row.get("pages") is not None else None,
                "chars_extracted": int(row["chars_extracted"]) if row.get("chars_extracted") is not None else None,
                "garbled_ratio": float(row["garbled_ratio"]) if row.get("garbled_ratio") is not None else None,
                "avg_chunk_tokens": float(row["avg_chunk_tokens"]) if row.get("avg_chunk_tokens") is not None else None,
                "fallback_triggered": bool(row.get("fallback_triggered")) if row.get("fallback_triggered") is not None else False,
                "shard_count": int(row["shard_count"]) if row.get("shard_count") is not None else None,
                "shard_failed_count": int(row["shard_failed_count"]) if row.get("shard_failed_count") is not None else None,
                "resolved_book_id": effective_book_id,
                "pdf_open_book_id": pdf_open_book_id,
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
            pdf_open_book_id = _resolve_pdf_access_book_id(
                effective_book_id,
                verified_firebase_uid,
                title=title,
            )
            return {
                "status": "COMPLETED",
                "file_name": None,
                "chunk_count": int(pdf_stats.get("effective_chunks", 0)),
                "embedding_count": int(pdf_stats.get("effective_embeddings", 0)),
                "updated_at": datetime.now().isoformat(),
                "parse_path": None,
                "parse_status": None,
                "pdf_available": bool(pdf_open_book_id),
                "storage_warning": None,
                "size_bytes": None,
                "storage_status": None,
                "error_message": None,
                "classification_route": None,
                "parse_engine": None,
                "fallback_engine": None,
                "classifier_metrics_json": None,
                "quality_metrics_json": None,
                "routing_metrics_json": None,
                "parse_time_ms": None,
                "pages": None,
                "chars_extracted": None,
                "garbled_ratio": None,
                "avg_chunk_tokens": None,
                "fallback_triggered": False,
                "shard_count": None,
                "shard_failed_count": None,
                "resolved_book_id": effective_book_id,
                "pdf_open_book_id": pdf_open_book_id,
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
        "parse_path": None,
        "parse_status": None,
        "pdf_available": False,
        "storage_warning": None,
        "size_bytes": None,
        "storage_status": None,
        "error_message": None,
        "classification_route": None,
        "parse_engine": None,
        "fallback_engine": None,
        "classifier_metrics_json": None,
        "quality_metrics_json": None,
        "routing_metrics_json": None,
        "parse_time_ms": None,
        "pages": None,
        "chars_extracted": None,
        "garbled_ratio": None,
        "avg_chunk_tokens": None,
        "fallback_triggered": False,
        "shard_count": None,
        "shard_failed_count": None,
        "resolved_book_id": effective_book_id,
        "pdf_open_book_id": None,
        "matched_by_title": matched_by_title,
        "match_source": match_source,
        "match_confidence": match_confidence if row else (0.0 if effective_book_id == book_id else 0.3),
        "item_index_state": None,
        "index_freshness_state": freshness.get("index_freshness_state"),
        "index_freshness": freshness,
    }


@app.get("/api/books/{book_id}/pdf", responses={401: {"description": "Authentication required"}, 404: {"description": "PDF not found"}})
async def get_book_pdf_metadata(
    book_id: str,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    access_book_id, record = _resolve_pdf_access_record(book_id, verified_firebase_uid)
    if not record or not record.get("object_key"):
        raise HTTPException(status_code=404, detail="PDF not found")

    return {
        "book_id": access_book_id or book_id,
        "requested_book_id": book_id,
        "pdf_available": True,
        "file_name": record.get("file_name"),
        "size_bytes": int(record["size_bytes"]) if record.get("size_bytes") is not None else None,
        "mime_type": record.get("mime_type") or "application/pdf",
        "parse_status": record.get("parse_status"),
        "parse_path": record.get("parse_path"),
        "storage_warning": record.get("storage_warning"),
        "updated_at": _to_iso_datetime(record.get("updated_at")),
    }


@app.get("/api/books/{book_id}/pdf/content", responses={401: {"description": "Authentication required"}, 404: {"description": "PDF not found"}, 500: {"description": "Streaming failed"}})
async def stream_book_pdf_content(
    book_id: str,
    request: Request,
):
    verified_firebase_uid = await get_pdf_request_uid(request)
    title = str(request.query_params.get("title") or "").strip() or None
    access_book_id, record = _resolve_pdf_access_record(book_id, verified_firebase_uid, title=title)
    if not record or not record.get("object_key") or not record.get("bucket_name"):
        raise HTTPException(status_code=404, detail="PDF not found")

    byte_range = request.headers.get("Range")
    try:
        body_iter, object_headers = stream_object(
            str(record.get("bucket_name")),
            str(record.get("object_key")),
            byte_range=byte_range,
        )
    except ObjectStorageConfigError as exc:
        logger.error("PDF stream failed due to Object Storage config: %s", exc)
        raise HTTPException(status_code=503, detail="PDF storage is not configured")
    except Exception as exc:
        logger.error("PDF stream failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to stream PDF")

    filename = str(record.get("file_name") or f"{access_book_id or book_id}.pdf")
    response_headers = {
        "Accept-Ranges": str(object_headers.get("accept_ranges") or "bytes"),
        "Content-Disposition": _build_content_disposition(filename),
        "Cache-Control": "private, max-age=60",
    }
    if object_headers.get("content_length") is not None:
        response_headers["Content-Length"] = str(object_headers.get("content_length"))
    if object_headers.get("content_range"):
        response_headers["Content-Range"] = str(object_headers.get("content_range"))
    if object_headers.get("etag"):
        response_headers["ETag"] = str(object_headers.get("etag"))

    return StreamingResponse(
        body_iter,
        status_code=206 if byte_range else 200,
        media_type=str(object_headers.get("content_type") or record.get("mime_type") or "application/pdf"),
        headers=response_headers,
    )


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
    request: Request,
    background_tasks: BackgroundTasks,
    admin_uid: str = Depends(require_admin),
):
    """
    Triggers the graph centrality recalculation script in the background.
    Useful after bulk ingesting new books to update discovery bridges.
    """
    _ = admin_uid

    background_tasks.add_task(_run_calculate_graph_stats_background)
    return {"success": True, "message": "Graph centrality calculation started in background."}


@app.post("/api/admin/external-kb/backfill/start")
async def start_external_kb_backfill(
    request: Request,
    all_users: bool = False,
    firebase_uid: Optional[str] = None,
    admin_uid: str = Depends(require_admin),
):
    verified_uid = admin_uid

    if all_users and settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=403, detail="all_users backfill is disabled in production")

    scope_uid = None if all_users else verified_uid
    status = start_external_kb_backfill_async(scope_uid=scope_uid)
    return {"success": True, "status": status}


@app.get("/api/admin/external-kb/backfill/status")
async def external_kb_backfill_status(
    request: Request,
    firebase_uid: Optional[str] = None,
    admin_uid: str = Depends(require_admin),
):
    _ = admin_uid
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
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        parsed_types = [t.strip() for t in str(types or "").split(",") if t.strip()] if types else None
        
        start_time = time.time()
        result = list_library_items(
            verified_uid,
            limit=limit,
            cursor=cursor,
            types=parsed_types,
            include_media=bool(getattr(settings, "MEDIA_LIBRARY_ENABLED", False)),
        )
        duration = time.time() - start_time
        logger.info(f"library list completed in {duration:.4f}s for user {verified_uid}")
        
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Library list failed", e, detail="Failed to list library items")


@app.get("/api/media/search", responses={401: {"description": "Authentication required"}, 404: {"description": "Media library disabled"}})
async def media_search_endpoint(
    request: Request,
    query: str,
    kind: str = "multi",
    page: int = 1,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    _ensure_media_library_enabled()
    # Enforce same auth policy as other library endpoints.
    _ = get_verified_uid(firebase_uid_from_jwt)

    if not bool(getattr(settings, "MEDIA_TMDB_SYNC_ENABLED", True)):
        return {"success": True, "results": [], "source": "manual_only"}
    if not str(getattr(settings, "TMDB_API_KEY", "") or "").strip():
        return {
            "success": True,
            "results": [],
            "source": "tmdb_unconfigured",
            "message": "TMDb API key is not configured on server",
        }

    text = str(query or "").strip()
    if not text:
        return {"success": True, "results": [], "source": "tmdb"}

    results = search_tmdb_media(text, kind=kind, page=page, max_results=10)
    return {"success": True, "results": results, "source": "tmdb"}


@app.get("/api/media/details/{kind}/{tmdb_id}", responses={401: {"description": "Authentication required"}, 404: {"description": "Media library disabled or details not found"}})
async def media_details_endpoint(
    request: Request,
    kind: str,
    tmdb_id: int,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    _ensure_media_library_enabled()
    _ = get_verified_uid(firebase_uid_from_jwt)

    if not bool(getattr(settings, "MEDIA_TMDB_SYNC_ENABLED", True)):
        raise HTTPException(status_code=503, detail="TMDb sync is disabled")
    if not str(getattr(settings, "TMDB_API_KEY", "") or "").strip():
        raise HTTPException(status_code=503, detail="TMDb API key is not configured on server")

    details = get_tmdb_media_details(kind, tmdb_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Media details not found")
    return {"success": True, "details": details}


@app.put("/api/library/items/{item_id}", responses={401: {"description": "Authentication required"}, 404: {"description": "Media library limited or resource not found"}})
async def upsert_library_item_endpoint(
    item_id: str,
    payload: LibraryItemUpsertRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        _ensure_media_resource_type_allowed(payload.type)
        payload_data = payload.model_dump()
        result = upsert_library_item(verified_uid, item_id, payload_data)
        if str(payload.type or "").strip().upper() == "ARTICLE":
            maybe_trigger_external_enrichment_async(
                book_id=str(result.get("item_id") or item_id),
                firebase_uid=verified_uid,
                title=payload.title,
                author=payload.author,
                tags=payload.tags,
                mode_hint="INGEST",
                item_type=payload.type,
                source_url=payload.url,
            )
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Library upsert failed", e, detail="Failed to save library item")


@app.patch("/api/library/items/{item_id}", responses={401: {"description": "Authentication required"}, 404: {"description": "Item not found"}})
async def patch_library_item_endpoint(
    item_id: str,
    payload: LibraryItemPatchRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        result = patch_library_item(verified_uid, item_id, payload.patch or {})
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Library patch failed", e, detail="Failed to update library item")


@app.delete("/api/library/items/{item_id}", responses={401: {"description": "Authentication required"}, 500: {"description": "Delete failed"}})
async def delete_library_item_endpoint(
    item_id: str,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        result = delete_library_item(verified_uid, item_id)
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Delete failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Library delete failed", e, detail="Failed to delete library item")


@app.post("/api/library/items/bulk-delete", responses={401: {"description": "Authentication required"}, 500: {"description": "Bulk delete failed"}})
async def bulk_delete_library_items_endpoint(
    payload: LibraryBulkDeleteRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        result = bulk_delete_library_items(verified_uid, payload.item_ids)
        return result
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Library bulk delete failed", e, detail="Failed to bulk delete library items")


@app.get("/api/library/personal-note-folders", responses={401: {"description": "Authentication required"}, 500: {"description": "Folder list failed"}})
async def list_personal_note_folders_endpoint(
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        folders = list_personal_note_folders(verified_uid)
        return {"success": True, "folders": folders}
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Folder list failed", e, detail="Failed to list folders")


@app.put("/api/library/personal-note-folders/{folder_id}", responses={401: {"description": "Authentication required"}, 500: {"description": "Folder upsert failed"}})
async def upsert_personal_note_folder_endpoint(
    folder_id: str,
    payload: PersonalNoteFolderUpsertRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        folder = upsert_personal_note_folder(verified_uid, folder_id, payload.model_dump())
        return {"success": True, "folder": folder}
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Folder upsert failed", e, detail="Failed to save folder")


@app.patch("/api/library/personal-note-folders/{folder_id}", responses={401: {"description": "Authentication required"}, 404: {"description": "Folder not found"}})
async def patch_personal_note_folder_endpoint(
    folder_id: str,
    payload: PersonalNoteFolderPatchRequest,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        folder = patch_personal_note_folder(verified_uid, folder_id, payload.model_dump(exclude_none=True))
        return {"success": True, "folder": folder}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Folder patch failed", e, detail="Failed to update folder")


@app.delete("/api/library/personal-note-folders/{folder_id}", responses={401: {"description": "Authentication required"}, 500: {"description": "Folder delete failed"}})
async def delete_personal_note_folder_endpoint(
    folder_id: str,
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    try:
        verified_uid = get_verified_uid(firebase_uid_from_jwt)
        return delete_personal_note_folder(verified_uid, folder_id)
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Folder delete failed", e, detail="Failed to delete folder")


@app.post("/api/add-item", responses={401: {"description": "Authentication required"}, 500: {"description": "Add item failed"}})
async def add_item_endpoint(
    request: AddItemRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)
        
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
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Add item failed", e, detail="Failed to add item")


@app.post("/api/books/{book_id}/sync-highlights", responses={401: {"description": "Authentication required"}, 500: {"description": "Highlight sync failed"}})
async def sync_highlights_endpoint(
    book_id: str,
    request: HighlightSyncRequest,
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        _ensure_media_resource_type_allowed(request.resource_type)
        verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)

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
        try:
            from services.memory_profile_service import refresh_memory_profile
            background_tasks.add_task(refresh_memory_profile, verified_firebase_uid)
        except Exception as e:
            logger.warning(f"Memory profile refresh enqueue skipped after highlight sync: {e}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Highlight sync failed", e, detail="Failed to sync highlights")


@app.post("/api/items/{item_id}/sync-highlights")
async def sync_highlights_for_item_endpoint(
    item_id: str,
    request: HighlightSyncRequest,
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Backward-compatible generic alias for non-book resources (movie/series etc.).
    return await sync_highlights_endpoint(
        book_id=item_id,
        request=request,
        background_tasks=background_tasks,
        firebase_uid_from_jwt=firebase_uid_from_jwt,
    )


@app.post("/api/notes/{book_id}/sync-personal-note", responses={401: {"description": "Authentication required"}, 500: {"description": "Personal note sync failed"}})
async def sync_personal_note_endpoint(
    book_id: str,
    request: PersonalNoteSyncRequest,
    background_tasks: BackgroundTasks,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)

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
        try:
            from services.memory_profile_service import refresh_memory_profile
            background_tasks.add_task(refresh_memory_profile, verified_firebase_uid)
        except Exception as e:
            logger.warning(f"Memory profile refresh enqueue skipped after personal note sync: {e}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Personal note sync failed", e, detail="Failed to sync personal note")


@app.get("/api/memory/profile")
async def get_memory_profile_endpoint(
    request: Request,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    try:
        from functools import partial
        from services.memory_profile_service import get_memory_profile, refresh_memory_profile

        loop = asyncio.get_running_loop()
        profile = await loop.run_in_executor(None, get_memory_profile, firebase_uid)
        if not profile:
            profile = await loop.run_in_executor(
                None,
                partial(refresh_memory_profile, firebase_uid, force=False),
            )
        if not profile:
            return {
                "firebase_uid": firebase_uid,
                "profile_summary": "",
                "active_themes": [],
                "recurring_sources": [],
                "open_questions": [],
                "evidence_counts": {},
                "status": "missing",
            }
        return profile
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Memory profile get failed", e, detail="Failed to load memory profile")


@app.post("/api/memory/profile/refresh")
async def refresh_memory_profile_endpoint(
    payload: MemoryProfileRefreshRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token),
):
    firebase_uid = get_verified_uid(firebase_uid_from_jwt)
    try:
        from functools import partial
        from services.memory_profile_service import refresh_memory_profile

        loop = asyncio.get_running_loop()
        profile = await loop.run_in_executor(
            None,
            partial(refresh_memory_profile, firebase_uid, force=bool(payload.force)),
        )
        return profile
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Memory profile refresh failed", e, detail="Failed to refresh memory profile")


@app.post("/api/resources/{book_id}/purge")
async def purge_resource_endpoint(
    book_id: str,
    request: PurgeResourceRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)

        result = purge_item_content(
            firebase_uid=verified_firebase_uid,
            book_id=book_id,
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Purge failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Resource purge failed", e, detail="Failed to purge resource")


@app.post("/api/migrate_bulk")
async def migrate_bulk_endpoint(
    request: BatchMigrateRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    try:
        verified_firebase_uid = get_verified_uid(firebase_uid_from_jwt)
        
        result = process_bulk_items_logic(request.items, verified_firebase_uid)
        return {
            "success": True,
            "processed": len(request.items),
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        _raise_internal_server_error("Bulk migration failed", e, detail="Failed to run bulk migration")

if __name__ == "__main__":
    logger.info("Starting FastAPI Server on port 8000 (DIRECT)...")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
