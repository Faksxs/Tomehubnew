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
import uvicorn
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional, List
import traceback

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Models
from models.request_models import (
    SearchRequest, SearchResponse, IngestRequest, 
    FeedbackRequest, AddItemRequest, BatchMigrateRequest,
    FeedbackRequest, AddItemRequest, BatchMigrateRequest,
    ChatRequest, ChatResponse, HighlightSyncRequest, ComparisonRequest
)
from middleware.auth_middleware import verify_firebase_token

# Import Services (Legacy & New)
from services.search_service import generate_answer, get_rag_context
from services.dual_ai_orchestrator import generate_evaluated_answer
from services.ingestion_service import ingest_book, ingest_text_item, process_bulk_items_logic, sync_highlights_for_item
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
from models.request_models import (
    EnrichBookRequest, GenerateTagsRequest, VerifyCoverRequest, AnalyzeHighlightsRequest
)
from fastapi.responses import StreamingResponse

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.cache_service import get_cache, generate_cache_key
from services.monitoring import DB_POOL_UTILIZATION, CIRCUIT_BREAKER_STATE
from services.memory_monitor_service import MemoryMonitor
from services.embedding_service import get_circuit_breaker_status

# Configure Sentry - REPLACED BY LOKI (Standard Logging)
# (Sentry code removed)

# Configure Logging (Structured JSON)
from pythonjsonlogger import jsonlogger

logger = logging.getLogger("tomehub_api")
logger.setLevel(logging.INFO)

# Console Handler (Stdout for Docker)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# File Handler (Legacy support)
fileHandler = logging.FileHandler('backend_error.log')
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)

# Remove default handlers to avoid duplicates
logging.getLogger().handlers = []
logging.getLogger().addHandler(logHandler)
logging.getLogger().addHandler(fileHandler)

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
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Layer 4 Flow Routes (MUST BE BEFORE Instrumentator)
# We import explicitly to fail fast if there's an issue
print("[FLOW] Importing flow_routes...")
# Include Flow Router (Layer 4)
from routes import flow_routes
app.include_router(flow_routes.router)
print(f"[FLOW] Router registered with {len(flow_routes.router.routes)} routes")

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
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/cache/status")
async def cache_status():
    """Check cache status and statistics."""
    try:
        from services.cache_service import get_cache
        cache = get_cache()
        
        if not cache:
            return {
                "status": "disabled",
                "message": "Cache is not initialized or disabled"
            }
        
        status = {
            "status": "enabled",
            "l1": {
                "size": cache.l1.size(),
                "maxsize": cache.l1.cache.maxsize,
                "ttl": cache.l1.cache.ttl
            },
            "l2": {
                "available": cache.l2.is_available(),
                "type": "redis" if cache.l2.is_available() else "none"
            }
        }
        
        return status
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/api/health/circuit-breaker")
async def circuit_breaker_status():
    """Check circuit breaker status for embedding API."""
    try:
        from services.embedding_service import get_circuit_breaker_status
        status = get_circuit_breaker_status()
        
        return {
            "status": "ok",
            "circuit_breaker": status
        }
    except Exception as e:
        logger.error(f"Error getting circuit breaker status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/api/health/memory")
async def health_memory():
    """Get memory usage statistics and health status (Task A2)."""
    try:
        from services.memory_monitor_service import MemoryMonitor
        
        stats = MemoryMonitor.get_memory_stats()
        status = MemoryMonitor.check_memory_health()
        
        return {
            "status": "ok",
            "memory": stats,
            "health": status,
            "health_emoji": MemoryMonitor.get_status_emoji(status)
        }
    except Exception as e:
        logger.error(f"Error getting memory health: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

@app.get("/api/health/restart")
async def health_restart():
    """Get auto-restart status and memory pressure state (Task A2)."""
    try:
        from services.auto_restart_service import auto_restart_manager
        
        status = await auto_restart_manager.get_status()
        
        return status
    except Exception as e:
        logger.error(f"Error getting restart status: {e}")
        return {
            "status": "error",
            "error": str(e)
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
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            logger.error("SECURITY: Auth failed but ENVIRONMENT != development. Rejecting request.")
            raise HTTPException(status_code=401, detail="Authentication required")
    
    # Log search start
    print(f"\n[SEARCH] Started for UID: {firebase_uid}")
    print(f"[SEARCH] Question: {search_request.question}")
    
    try:
        import asyncio
        from functools import partial
        
        loop = asyncio.get_running_loop()

        # Analytic short-circuit (Layer-3)
        if is_analytic_word_count(search_request.question):
            term = extract_target_term(search_request.question)
            resolved_book_id = search_request.book_id
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
            }
            
            print(f"[DEBUG] Contexts count: {len(metadata_dict['analytics']['contexts'])}")
            
            return {
                "answer": f"\"{term}\" kelimesi bu kitapta toplam {count} kez geçiyor.",
                "sources": [],
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata_dict
            }
        
        # Run synchronous RAG search in thread pool
        result = await loop.run_in_executor(
            None, 
            partial(
                generate_answer, 
                search_request.question, 
                firebase_uid, 
                search_request.book_id,
                None, # chat_history
                "", # session_summary
                search_request.limit,
                search_request.offset,
                None # session_id
            )
        )
        
        # Unpack result (answer, sources, metadata)
        answer, sources, metadata = result
        print(f"[SEARCH] Finished. Answer length: {len(answer)}, Sources: {len(sources) if sources else 0}")
        if sources:
             print(f"[SEARCH] First source: {sources[0].get('title')} Score: {sources[0].get('similarity_score')}")
        print(f"[SEARCH] Metadata: {metadata}")
        
        return {
            "answer": answer,
            "sources": sources or [],
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata
        }
    except Exception as e:
        print(f"[ERROR] Search failed: {e}")
        traceback.print_exc()
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
    Stateful Chat Endpoint (LagosChat - Layer 3).
    Orchestrates session, history, and RAG search.
    """
    # Determine authoritative UID (JWT or request body in dev mode)
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
        logger.info(f"Using JWT-verified UID: {firebase_uid}")
    else:
        firebase_uid = chat_request.firebase_uid
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            logger.error("SECURITY: Auth failed but ENVIRONMENT != development. Rejecting request.")
            raise HTTPException(status_code=401, detail="Authentication required")
    
    print(f"\n[CHAT] Started for Session: {chat_request.session_id} UID: {firebase_uid}")
    
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
                        "all_notes_count": all_notes_count,
                        "match": "lemma",
                        "scope": "book_chunks",
                        "resolved_book_id": resolved_book_id,
                        "contexts": contexts
                    },
                },
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
        
        if use_explorer_mode:
            # EXPLORER Mode: Dual-AI Orchestrator with conversation state
            from services.chat_history_service import get_conversation_state
            
            # Get structured conversation state for context
            if session_id:
                conversation_state = await loop.run_in_executor(
                    None, get_conversation_state, session_id
                )
            else:
                conversation_state = {}

            # 1. Retrieve Context
            rag_ctx = await loop.run_in_executor(
                None, 
                partial(
                    get_rag_context,
                    chat_request.message, 
                    firebase_uid, 
                    chat_history=ctx_data['recent_messages'],
                    mode='EXPLORER',
                    resource_type=chat_request.resource_type,
                    limit=chat_request.limit,
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
                    conversation_state=conversation_state  # Pass structured state
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
                    chat_request.book_id,
                    ctx_data['recent_messages'],
                    ctx_data['summary'] or "",
                    chat_request.limit,
                    chat_request.offset,
                    session_id
                )
            )
            
            if answer_result:
                answer = answer_result
                sources = sources_result or []
                final_metadata = meta_result or {}
        
        # 5. Save Assistant Message
        await loop.run_in_executor(None, add_message, session_id, 'assistant', answer, sources)
        
        # 6. Periodic Summarization (Background)
        background_tasks.add_task(summarize_session_history, session_id)
        
        # 7. Format Response
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
        print(f"[ERROR] Chat failed: {e}")
        traceback.print_exc()
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
        print(f"[ERROR] Concordance endpoint failed: {e}")
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
        print(f"[ERROR] Distribution endpoint failed: {e}")
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
        print(f"[ERROR] Comparison endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/smart-search")
def perform_search(
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
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        from services.smart_search_service import perform_search
        results, metadata = perform_search(
            request.question, 
            firebase_uid, 
            limit=request.limit, 
            offset=request.offset
        )
        
        return {
            "results": results,
            "total": metadata.get("total_count", len(results)),
            "query": request.question,
            "metadata": metadata
        }
    except Exception as e:
        print(f"[ERROR] Smart search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback")
def feedback(
    request: FeedbackRequest,
    firebase_uid_from_jwt: str | None = Depends(verify_firebase_token)
):
    # Determine authoritative UID
    if firebase_uid_from_jwt:
        firebase_uid = firebase_uid_from_jwt
    else:
        firebase_uid = request.firebase_uid
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from request body: {firebase_uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        # Pydantic model dump
        data = request.model_dump()
        data['firebase_uid'] = firebase_uid  # Ensure verified UID is used
        success = submit_feedback(data)
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
    if not file.filename.lower().endswith(".pdf"):
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
        print(f"Error extracting metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/api/reports/search")
def search_reports(
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
        if settings.ENVIRONMENT == "development":
            logger.warning(f"⚠️ Dev mode: Using unverified UID from query: {uid}")
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    results = search_reports_by_topic(uid, topic, limit)
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
    except Exception as e:
        logger.error(f"Failed to upsert ingestion status: {e}")

def fetch_ingestion_status(book_id: str, firebase_uid: str):
    """Fetch ingestion status for a book/user."""
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT STATUS, SOURCE_FILE_NAME, CHUNK_COUNT, EMBEDDING_COUNT, UPDATED_AT
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid}
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to fetch ingestion status: {e}")
        return None

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
                                FROM TOMEHUB_CONTENT
                                WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
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
    print(f"Ingesting file: {file.filename} Title: {title}")
    
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
    
    # Save file
    import uuid
    from werkzeug.utils import secure_filename
    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{original_filename}"
    temp_path = os.path.join(upload_dir, unique_filename)
    
    try:
        # Upsert ingestion status as PROCESSING (if book_id provided)
        if book_id:
            upsert_ingestion_status(
                book_id=book_id,
                firebase_uid=verified_firebase_uid,
                status="PROCESSING",
                file_name=original_filename
            )

        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
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
        print(f"Ingestion setup error: {e}")
        # If we failed before adding task, cleanup immediately
        if os.path.exists(temp_path):
             os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/books/{book_id}/ingestion-status")
async def get_ingestion_status(
    book_id: str,
    request: Request,
    firebase_uid: Optional[str] = None,
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

    row = fetch_ingestion_status(book_id, verified_firebase_uid)
    if row:
        status, file_name, chunk_count, embedding_count, updated_at = row
        return {
            "status": status,
            "file_name": file_name,
            "chunk_count": int(chunk_count) if chunk_count is not None else None,
            "embedding_count": int(embedding_count) if embedding_count is not None else None,
            "updated_at": updated_at.isoformat() if updated_at else None
        }

    # Fallback: check if content exists for this book
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) as chunk_count,
                           SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END) as embedding_count
                    FROM TOMEHUB_CONTENT
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": verified_firebase_uid}
                )
                row = cursor.fetchone()
                chunk_count = row[0] if row else 0
                embedding_count = row[1] if row and row[1] is not None else 0
                if chunk_count > 0:
                    return {
                        "status": "COMPLETED",
                        "file_name": None,
                        "chunk_count": int(chunk_count),
                        "embedding_count": int(embedding_count),
                        "updated_at": datetime.now().isoformat()
                    }
    except Exception as e:
        logger.error(f"Fallback ingestion status check failed: {e}")

    return {
        "status": "NOT_FOUND",
        "file_name": None,
        "chunk_count": None,
        "embedding_count": None,
        "updated_at": None
    }


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
            return {"success": True, "message": "Item added"}
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



# ============================================================================
# NEW AI ENDPOINTS (NOT IN FLASK, MIGRATED FROM FIREBASE)
# ============================================================================

from fastapi import Body

@app.post("/api/ai/enrich-book")
@limiter.limit(settings.RATE_LIMIT_AI_ENRICH)
async def enrich_book_endpoint(
    request: Request,
    enrich_request: EnrichBookRequest,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Enrich a single book with metadata (Summary, Tags, etc.)
    """
    logger.info(f"AI Enrichment requested for: {enrich_request.title}")
    try:
        # data = request.model_dump()
        # Passing dictionary as expected by service
        result = await enrich_book_async(enrich_request.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/enrich-batch")
async def enrich_batch_endpoint(
    request: Request,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Stream enriched books back to client using SSE.
    Expects JSON body: { "books": [...] }
    """
    try:
        data = await request.json()
        books = data.get('books', [])
        
        if not books:
             raise HTTPException(status_code=400, detail="No books provided")
             
        if len(books) > 50:
             logger.warning(f"Large batch enrichment requested ({len(books)}). Capping at 50.")
             books = books[:50]
             
        # Use StreamingResponse for SSE
        return StreamingResponse(
            stream_enrichment(books),
            media_type="text/event-stream"
        )
    except Exception as e:
        print(f"Streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/generate-tags")
@limiter.limit(settings.RATE_LIMIT_AI_ENRICH)
async def generate_tags_endpoint(
    request: Request,
    tags_request: GenerateTagsRequest,
    user_id: str = Depends(verify_firebase_token)
):
    try:
        tags = await generate_tags_async(tags_request.note_content)
        return {"tags": tags}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/verify-cover")
@limiter.limit(settings.RATE_LIMIT_AI_COVER)
async def verify_cover_endpoint(
    request: Request,
    cover_request: VerifyCoverRequest,
    user_id: str = Depends(verify_firebase_token)
):
    try:
        url = await verify_cover_async(cover_request.title, cover_request.author, cover_request.isbn)
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/analyze-highlights")
@limiter.limit(settings.RATE_LIMIT_AI_ANALYZE)
async def analyze_highlights_endpoint(
    request: Request,
    highlights_request: AnalyzeHighlightsRequest,
    user_id: str = Depends(verify_firebase_token)
):
    try:
        summary = await analyze_highlights_async(highlights_request.highlights)
        return {"summary": summary}
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/search-resources")
@limiter.limit(settings.RATE_LIMIT_AI_ENRICH)
async def search_resources_endpoint(
    request: Request,
    query: str = Body(...), 
    type: str = Body(...),
    user_id: str = Depends(verify_firebase_token)
):
    try:
        results = await search_resources_async(query, type)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




if __name__ == "__main__":
    print("[INFO] Starting FastAPI Server on port 5000 (DIRECT)...")
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
