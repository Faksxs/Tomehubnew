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
    FeedbackRequest, AddItemRequest, BatchMigrateRequest
)
from middleware.auth_middleware import verify_firebase_token

# Import Services (Legacy & New)
from services.search_service import generate_answer, get_rag_context
from services.dual_ai_orchestrator import generate_evaluated_answer
from services.ingestion_service import ingest_book, ingest_text_item, process_bulk_items_logic
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

# Configure Logging
logging.basicConfig(
    filename='backend_error.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger("tomehub_api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Init Helper Services
    logger.info("Starting up: Initializing DB Pool...")
    DatabaseManager.init_pool()
    
    # Initialize Cache
    if settings.CACHE_ENABLED:
        logger.info("Starting up: Initializing Cache...")
        from services.cache_service import init_cache
        cache = init_cache(
            l1_maxsize=settings.CACHE_L1_MAXSIZE,
            l1_ttl=settings.CACHE_L1_TTL,
            redis_url=settings.REDIS_URL
        )
        app.state.cache = cache
        logger.info("Cache initialized successfully")
    else:
        logger.info("Cache disabled (CACHE_ENABLED=false)")
        app.state.cache = None
    
    yield
    # Shutdown: Clean up
    logger.info("Shutting down: Closing DB Pool...")
    DatabaseManager.close_pool()

# Initialize FastAPI
app = FastAPI(
    title="TomeHub API",
    description="Unified Backend for TomeHub (Search + AI + Ingestion)",
    version="2.0.0",
    lifespan=lifespan
)

# Initialize Limiter
limiter = Limiter(key_func=get_remote_address)
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

# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@app.post("/api/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    # Log search start
    print(f"\n[SEARCH] Started for UID: {request.firebase_uid}")
    print(f"[SEARCH] Question: {request.question}")
    
    try:
        import asyncio
        from functools import partial
        loop = asyncio.get_running_loop()
        
        # Check Feature Flag
        enable_dual_ai = os.getenv("ENABLE_DUAL_AI", "false").lower() == "true"
        
        if enable_dual_ai:
            print("[SEARCH] Using Dual-AI Orchestrator Flow")
            
            # 1. Retrieve Context
            rag_ctx = await loop.run_in_executor(
                None, 
                partial(
                    get_rag_context, 
                    request.question, 
                    request.firebase_uid, 
                    request.book_id
                )
            )
            
            if not rag_ctx:
                return {
                    "answer": "Üzgünüm, ilgili içerik bulunamadı.",
                    "sources": [],
                    "timestamp": datetime.now().isoformat()
                }
                
            # 2. Evaluate & Generate
            result = await generate_evaluated_answer(
                question=request.question,
                chunks=rag_ctx['chunks'],
                answer_mode=rag_ctx['mode'],
                confidence_score=rag_ctx['confidence'],
                network_status=rag_ctx.get('network_status', 'IN_NETWORK')
            )
            
            # 3. Format Response
            sources = []
            for c in rag_ctx['chunks']:
                sources.append({
                    'title': c.get('title', 'Unknown'),
                    'page_number': c.get('page_number', 0),
                    'similarity_score': c.get('score', 0)
                })
                
            final_ans = result['final_answer']
            verdict = result['metadata'].get('verdict')
            
            if verdict == "DECLINE":
                 final_ans = f"[⚠️ Yetersiz Güvenilirlik] {final_ans}\n\n(Not: Bu cevap kalite standartlarını tam karşılamamış olabilir.)"
            
            return {
                "answer": final_ans,
                "sources": sources,
                "timestamp": datetime.now().isoformat()
            }
            
        else:
            # Legacy Flow
            answer, sources = await loop.run_in_executor(
                None, 
                partial(
                    generate_answer, 
                    request.question, 
                    request.firebase_uid, 
                    context_book_id=request.book_id
                )
            )
            
            print(f"[SEARCH] Finished. Sources found: {len(sources) if sources else 0}")
            
            if answer is None:
                return {
                    "answer": "I couldn't find any relevant information.",
                    "sources": [],
                    "timestamp": datetime.now().isoformat()
                }
                
            return {
                "answer": answer,
                "sources": sources or [],
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        print(f"[ERROR] Search failed: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/smart-search")
def smart_search(request: SearchRequest):
    """
    Pure weighted search (Layer 2).
    """
    try:
        from services.smart_search_service import perform_smart_search
        results = perform_smart_search(request.question, request.firebase_uid)
        
        return {
            "results": results,
            "total": len(results),
            "query": request.question
        }
    except Exception as e:
        print(f"[ERROR] Smart search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/feedback")
def feedback(request: FeedbackRequest):
    try:
        # Pydantic model dump
        data = request.model_dump()
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
async def extract_metadata_endpoint(file: UploadFile = File(...)):
    # ... (keep async as it uses await file.read())
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

def run_ingestion_background(temp_path: str, title: str, author: str, firebase_uid: str, book_id: str):
    """
    Background task wrapper for book ingestion.
    """
    try:
        logger.info(f"Starting background ingestion for: {title}")
        success = ingest_book(temp_path, title, author, firebase_uid, book_id)
        
        if success:
            logger.info(f"Background ingestion success: {title}")
        else:
            logger.error(f"Background ingestion failed: {title}")
            
    except Exception as e:
        logger.error(f"Background ingestion exception: {e}")
        # Note: We rely on ingest_book's internal logic for file cleanup (Task 1.3 will fix that logic next)

@app.post("/api/ingest")
async def ingest_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(...),
    firebase_uid: str = Form(...),
    book_id: Optional[str] = Form(None)
):
    # ... (keep async, awaits file.read)
    upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    
    # Save file
    import uuid
    from werkzeug.utils import secure_filename
    original_filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4()}_{original_filename}"
    temp_path = os.path.join(upload_dir, unique_filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        # Add to background tasks
        background_tasks.add_task(
            run_ingestion_background, 
            temp_path, 
            title, 
            author, 
            firebase_uid, 
            book_id
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


@app.post("/api/add-item")
def add_item_endpoint(request: AddItemRequest):
    try:
        success = ingest_text_item(
            text=request.text,
            title=request.title,
            author=request.author,
            source_type=request.type,
            firebase_uid=request.firebase_uid
        )
        if success:
            return {"success": True, "message": "Item added"}
        raise HTTPException(status_code=500, detail="Failed to add item")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/migrate_bulk")
def migrate_bulk_endpoint(request: BatchMigrateRequest):
    try:
        result = process_bulk_items_logic(request.items, request.firebase_uid)
        return {
            "success": True,
            "processed": len(request.items),
            "results": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ingested-books")
def get_ingested_books_endpoint(firebase_uid: str):
    try:
        with DatabaseManager.get_connection() as connection:
            with connection.cursor() as cursor:
                query = """
                SELECT DISTINCT title, book_id
                FROM TOMEHUB_CONTENT 
                WHERE firebase_uid = :p_uid AND source_type = 'PDF'
                """
                cursor.execute(query, {"p_uid": firebase_uid})
                rows = cursor.fetchall()
                
                books = []
                for row in rows:
                    raw_title = row[0]
                    # Simple split logic from old app.py
                    title_parts = raw_title.split(" - ")
                    title = title_parts[0]
                    author = title_parts[1] if len(title_parts) > 1 else "Unknown"
                    
                    books.append({
                        'title': title,
                        'author': author,
                        'book_id': row[1]
                    })
            
                return {"books": books}
        
    except Exception as e:
        print(f"Error fetching books: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# NEW AI ENDPOINTS (NOT IN FLASK, MIGRATED FROM FIREBASE)
# ============================================================================

from fastapi import Body

@app.post("/api/ai/enrich-book")
@limiter.limit("10/minute")
async def enrich_book_endpoint(
    request: Request,
    enrich_request: EnrichBookRequest,
    user_id: str = Depends(verify_firebase_token)
):
    """
    Enrich a single book with metadata (Summary, Tags, etc.)
    """
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
             
        # Use StreamingResponse for SSE
        return StreamingResponse(
            stream_enrichment(books),
            media_type="text/event-stream"
        )
    except Exception as e:
        print(f"Streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/generate-tags")
@limiter.limit("10/minute")
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
@limiter.limit("20/minute")
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
@limiter.limit("5/minute")
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
@limiter.limit("10/minute")
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
    print("[INFO] Starting FastAPI Server on port 5000...")
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
