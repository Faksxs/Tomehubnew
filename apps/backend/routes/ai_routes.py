import logging
import traceback
from io import BytesIO
from fastapi import APIRouter, Request, Depends, HTTPException, Body, UploadFile, File
from fastapi.responses import StreamingResponse

from models.request_models import (
    EnrichBookRequest, GenerateTagsRequest, VerifyCoverRequest, AnalyzeHighlightsRequest
)
from middleware.auth_middleware import verify_firebase_token
from config import settings

from services.ai_service import (
    enrich_book_async, generate_tags_async, verify_cover_async, 
    analyze_highlights_async, search_resources_async, stream_enrichment
)

logger = logging.getLogger("tomehub_api")
router = APIRouter(tags=["AI Tools"])
from slowapi import Limiter
from slowapi.util import get_remote_address

def get_rate_limit_key(request: Request):
    uid = request.headers.get("X-Firebase-UID")
    return uid if uid else get_remote_address(request)

limiter = Limiter(key_func=get_rate_limit_key, default_limits=[settings.RATE_LIMIT_GLOBAL])
# NEW AI ENDPOINTS (NOT IN FLASK, MIGRATED FROM FIREBASE)
# ============================================================================

from fastapi import Body

@router.post("/api/ai/enrich-book")
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

@router.post("/api/ai/enrich-batch")
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
        logger.error("Streaming error", extra={"error": str(e), "traceback": traceback.format_exc()})
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/ai/generate-tags")
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

@router.post("/api/ai/verify-cover")
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

@router.post("/api/ai/analyze-highlights")
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

@router.post("/api/ai/search-resources")
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


@router.post("/api/scan-isbn")
async def scan_isbn_endpoint(
    file: UploadFile = File(...),
    user_id: str = Depends(verify_firebase_token)
):
    """
    Decode a barcode (ISBN) from an uploaded image using pyzbar.
    Accepts image/jpeg, image/png, image/webp, image/heic etc.
    Returns { "isbn": "9781234567890" } or 404 if not found.
    """

    try:
        from PIL import Image as PILImage
        from pyzbar.pyzbar import decode as pyzbar_decode, ZBarSymbol
    except ImportError:
        raise HTTPException(status_code=503, detail="Barcode scanning library not available")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        img = PILImage.open(BytesIO(content))
    except Exception:
        raise HTTPException(status_code=400, detail="Cannot open image")

    # Try original image first
    symbols = [ZBarSymbol.EAN13, ZBarSymbol.EAN8, ZBarSymbol.UPCA, ZBarSymbol.UPCE, ZBarSymbol.CODE128]
    barcodes = pyzbar_decode(img, symbols=symbols)

    # If no result, try grayscale + contrast enhanced version
    if not barcodes:
        try:
            from PIL import ImageEnhance, ImageFilter
            gray = img.convert("L")
            enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
            barcodes = pyzbar_decode(enhanced, symbols=symbols)
        except Exception:
            pass

    if not barcodes:
        raise HTTPException(status_code=404, detail="No barcode found in image")

    raw = barcodes[0].data.decode("utf-8", errors="ignore").strip()
    logger.info(f"ISBN barcode scanned successfully: {raw[:6]}****")
    return {"isbn": raw}


