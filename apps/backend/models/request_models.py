from pydantic import BaseModel, Field
from typing import Optional, List, Any

class SearchRequest(BaseModel):
    question: str
    firebase_uid: str
    book_id: Optional[str] = None
    
class SearchResponse(BaseModel):
    answer: str
    sources: List[Any]
    timestamp: str

class FeedbackRequest(BaseModel):
    firebase_uid: str
    query: str
    answer: str
    rating: Optional[int] = None
    comment: Optional[str] = None

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
    # We might need to accept a whole ItemDraft-like object
    # For now keep it flexible or align with frontend types
    
class GenerateTagsRequest(BaseModel):
    note_content: str
    
class VerifyCoverRequest(BaseModel):
    title: str
    author: str
    isbn: Optional[str] = None

class AnalyzeHighlightsRequest(BaseModel):
    highlights: List[str]
