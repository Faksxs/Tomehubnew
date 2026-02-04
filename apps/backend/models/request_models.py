from pydantic import BaseModel, Field
from typing import Optional, List, Any

class SearchRequest(BaseModel):
    question: str
    firebase_uid: str
    book_id: Optional[str] = None
    mode: Optional[str] = "STANDARD" # STANDARD or EXPLORER
    limit: Optional[int] = 20
    offset: Optional[int] = 0
    
class SearchResponse(BaseModel):
    answer: str
    sources: List[Any]
    timestamp: str
    metadata: Optional[dict] = None
    # We use dict for metadata to allow flexibility, but we must ensure
    # Pydantic doesn't strip fields if we were to use a strict model.
    # Currently it's permissive.

class FeedbackRequest(BaseModel):
    firebase_uid: str
    query: str
    answer: str
    rating: Optional[int] = None
    comment: Optional[str] = None
    search_log_id: Optional[int] = None
    book_id: Optional[str] = None

class IngestRequest(BaseModel):
    # For file uploads, Pydantic is less useful directly in the endpoint signature 
    # (FastAPI uses UploadFile), but we can use this for validation if needed.
    title: str
    author: str
    firebase_uid: str
    book_id: Optional[str] = None

class AddItemRequest(BaseModel):
    text: str
    title: str
    author: str
    type: str = "NOTE"
    firebase_uid: str
    book_id: Optional[str] = None
    page_number: Optional[int] = None
    chunk_type: Optional[str] = None
    chunk_index: Optional[int] = None
    comment: Optional[str] = None
    tags: Optional[List[str]] = None

class BatchMigrateRequest(BaseModel):
    items: List[dict]
    firebase_uid: str

# NEW: Models for AI Service
class EnrichBookRequest(BaseModel):
    title: str
    author: str
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    
    model_config = {
        "extra": "allow"
    }
class GenerateTagsRequest(BaseModel):
    note_content: str
    
class VerifyCoverRequest(BaseModel):
    title: str
    author: str
    isbn: Optional[str] = None

class AnalyzeHighlightsRequest(BaseModel):
    highlights: List[str]


class HighlightItem(BaseModel):
    id: Optional[str] = None
    text: str
    type: Optional[str] = "highlight"  # highlight | note (insight)
    comment: Optional[str] = None
    pageNumber: Optional[int] = None
    tags: Optional[List[str]] = None
    createdAt: Optional[int] = None


class HighlightSyncRequest(BaseModel):
    firebase_uid: str
    title: str
    author: str
    resource_type: Optional[str] = None
    highlights: List[HighlightItem]

# --- Memory Layer Models ---
class ChatRequest(BaseModel):
    message: str
    firebase_uid: str
    session_id: Optional[int] = None
    book_id: Optional[str] = None # Optional focus context
    resource_type: Optional[str] = None # Layer 4 Filter: BOOK, ARTICLE, WEBSITE, PERSONAL_NOTE
    mode: Optional[str] = "STANDARD" # STANDARD (Default) or EXPLORER
    limit: Optional[int] = 5
    offset: Optional[int] = 0

class ChatResponse(BaseModel):
    answer: str
    session_id: int
    sources: List[Any]
    timestamp: str
    conversation_state: Optional[dict] = None  # Structured state for Context Bar
    thinking_history: Optional[List[Any]] = None  # Process logs for UI
    metadata: Optional[dict] = None  # Degradation info and other metadata


class ComparisonRequest(BaseModel):
    firebase_uid: str
    target_book_ids: List[str]
    term: str

