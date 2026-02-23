from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any

_UID_MAX = 128
_BOOK_ID_MAX = 256
_TEXT_MAX = 2000
_NOTE_MAX = 20000
_TAG_MAX = 64
_TARGET_BOOKS_MAX = 20


class SearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=_TEXT_MAX)
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    context_book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    resource_type: Optional[str] = Field(default=None, max_length=64)
    scope_mode: str = Field(default="AUTO")
    compare_mode: str = Field(default="EXPLICIT_ONLY")
    target_book_ids: Optional[List[str]] = None
    mode: str = Field(default="STANDARD")  # STANDARD or EXPLORER
    include_private_notes: bool = False
    visibility_scope: str = Field(default="default", max_length=32)
    content_type: Optional[str] = Field(default=None, max_length=64)
    ingestion_type: Optional[str] = Field(default=None, max_length=64)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("question cannot be empty or whitespace")
        return text

    @field_validator("firebase_uid")
    @classmethod
    def normalize_uid(cls, value: str) -> str:
        uid = (value or "").strip()
        if not uid:
            raise ValueError("firebase_uid cannot be empty")
        return uid

    @field_validator("book_id", "context_book_id")
    @classmethod
    def normalize_book_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        book_id = value.strip()
        return book_id or None

    @field_validator("scope_mode", mode="before")
    @classmethod
    def normalize_scope_mode(cls, value: Optional[str]) -> str:
        scope_mode = str(value or "AUTO").strip().upper()
        if scope_mode not in {"AUTO", "BOOK_FIRST", "HIGHLIGHT_FIRST", "GLOBAL"}:
            raise ValueError("scope_mode must be AUTO, BOOK_FIRST, HIGHLIGHT_FIRST, or GLOBAL")
        return scope_mode

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: Optional[str]) -> str:
        mode = str(value or "STANDARD").strip().upper()
        if mode not in {"STANDARD", "EXPLORER"}:
            raise ValueError("mode must be STANDARD or EXPLORER")
        return mode

    @field_validator("compare_mode", mode="before")
    @classmethod
    def normalize_compare_mode(cls, value: Optional[str]) -> str:
        compare_mode = str(value or "EXPLICIT_ONLY").strip().upper()
        if compare_mode not in {"EXPLICIT_ONLY", "AUTO"}:
            raise ValueError("compare_mode must be EXPLICIT_ONLY or AUTO")
        return compare_mode

    @field_validator("target_book_ids", mode="before")
    @classmethod
    def normalize_target_book_ids(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized: List[str] = []
        seen = set()
        for item in value:
            book_id = str(item or "").strip()
            if not book_id:
                continue
            truncated = book_id[:_BOOK_ID_MAX]
            if truncated in seen:
                continue
            seen.add(truncated)
            normalized.append(truncated)
            if len(normalized) >= _TARGET_BOOKS_MAX:
                break
        return normalized or None

    @field_validator("visibility_scope", mode="before")
    @classmethod
    def normalize_visibility_scope(cls, value: Optional[str]) -> str:
        scope = str(value or "default").strip().lower()
        if scope not in {"default", "all"}:
            raise ValueError("visibility_scope must be 'default' or 'all'")
        return scope

    @field_validator("content_type", "ingestion_type", mode="before")
    @classmethod
    def normalize_optional_upper_enum(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None


class SearchResponse(BaseModel):
    answer: str
    sources: List[Any]
    timestamp: str
    metadata: Optional[dict] = None


class FeedbackRequest(BaseModel):
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    query: str = Field(..., min_length=1, max_length=_TEXT_MAX)
    answer: str = Field(..., min_length=1, max_length=10000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=2000)
    search_log_id: Optional[int] = None
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)

    @field_validator("firebase_uid", "query", "answer", mode="before")
    @classmethod
    def normalize_required_text(cls, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("field cannot be empty")
        return text


class IngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)


class AddItemRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_NOTE_MAX)
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    type: str = "PERSONAL_NOTE"
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    page_number: Optional[int] = Field(default=None, ge=0, le=100000)
    chunk_type: Optional[str] = Field(default=None, max_length=64)
    chunk_index: Optional[int] = Field(default=None, ge=0, le=1000000)
    comment: Optional[str] = Field(default=None, max_length=4000)
    tags: Optional[List[str]] = None

    @field_validator("text", "title", "author", "firebase_uid", mode="before")
    @classmethod
    def normalize_required_fields(cls, value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("field cannot be empty")
        return text

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: Optional[str]) -> str:
        st = str(value or "PERSONAL_NOTE").strip().upper()
        if st in {"NOTE", "PERSONAL"}:
            return "PERSONAL_NOTE"
        if st in {"NOTES", "HIGHLIGHTS"}:
            return "HIGHLIGHT"
        if st in {"INSIGHTS"}:
            return "INSIGHT"
        return st

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        out: List[str] = []
        for item in value[:20]:
            tag = str(item or "").strip()
            if not tag:
                continue
            out.append(tag[:_TAG_MAX])
        return out or None


class BatchMigrateRequest(BaseModel):
    items: List[dict] = Field(default_factory=list, min_length=1, max_length=500)
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)


class EnrichBookRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    publisher: Optional[str] = Field(default=None, max_length=256)
    isbn: Optional[str] = Field(default=None, max_length=64)
    summary: Optional[str] = Field(default=None, max_length=4000)
    tags: Optional[List[str]] = None
    content_language_mode: Optional[str] = Field(default="AUTO", max_length=8)
    source_language_hint: Optional[str] = Field(default=None, max_length=16)
    force_regenerate: bool = False

    model_config = {
        "extra": "allow"
    }

    @field_validator("content_language_mode", mode="before")
    @classmethod
    def normalize_content_language_mode(cls, value: Optional[str]) -> str:
        mode = str(value or "AUTO").strip().upper()
        if mode in {"TR", "EN"}:
            return mode
        return "AUTO"

    @field_validator("source_language_hint", mode="before")
    @classmethod
    def normalize_source_language_hint(cls, value: Optional[str]) -> Optional[str]:
        raw = str(value or "").strip().lower()
        if not raw:
            return None
        if raw in {"tr", "turkish", "turkce", "türkçe"}:
            return "tr"
        if raw in {"en", "english", "ingilizce"}:
            return "en"
        return None


class GenerateTagsRequest(BaseModel):
    note_content: str = Field(..., min_length=1, max_length=6000)


class VerifyCoverRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    isbn: Optional[str] = Field(default=None, max_length=64)


class AnalyzeHighlightsRequest(BaseModel):
    highlights: List[str] = Field(default_factory=list, min_length=1, max_length=200)


class HighlightItem(BaseModel):
    id: Optional[str] = Field(default=None, max_length=128)
    text: str = Field(..., min_length=1, max_length=6000)
    type: Optional[str] = "highlight"  # highlight | insight (legacy: note)
    comment: Optional[str] = Field(default=None, max_length=2000)
    pageNumber: Optional[int] = Field(default=None, ge=0, le=100000)
    tags: Optional[List[str]] = None
    createdAt: Optional[int] = None

    @field_validator("type", mode="before")
    @classmethod
    def normalize_highlight_type(cls, value: Optional[str]) -> str:
        st = str(value or "highlight").strip().lower()
        if st in {"note", "insight"}:
            return "insight"
        return "highlight"


class HighlightSyncRequest(BaseModel):
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    resource_type: Optional[str] = Field(default=None, max_length=64)
    highlights: List[HighlightItem] = Field(default_factory=list, min_length=1, max_length=1000)


class PersonalNoteSyncRequest(BaseModel):
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    title: str = Field(..., min_length=1, max_length=256)
    author: str = Field(..., min_length=1, max_length=256)
    content: Optional[str] = Field(default=None, max_length=_NOTE_MAX)
    tags: Optional[List[str]] = None
    category: Optional[str] = "PRIVATE"
    delete_only: Optional[bool] = False

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: Optional[str]) -> str:
        category = str(value or "PRIVATE").strip().upper()
        if category in {"DAILY", "IDEAS"}:
            return category
        return "PRIVATE"


class PurgeResourceRequest(BaseModel):
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)

    @field_validator("firebase_uid", mode="before")
    @classmethod
    def normalize_uid(cls, value: Optional[str]) -> str:
        uid = str(value or "").strip()
        if not uid:
            raise ValueError("firebase_uid cannot be empty")
        return uid


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=_TEXT_MAX)
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    session_id: Optional[int] = None
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    context_book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    resource_type: Optional[str] = Field(default=None, max_length=64)
    scope_mode: str = Field(default="AUTO")
    compare_mode: str = Field(default="EXPLICIT_ONLY")
    target_book_ids: Optional[List[str]] = None
    mode: str = Field(default="STANDARD")
    # Retrieval candidate limit for chat context (not quote count).
    # Keep this aligned with SearchRequest defaults to avoid overly narrow context.
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("message cannot be empty or whitespace")
        return text

    @field_validator("book_id", "context_book_id", mode="before")
    @classmethod
    def normalize_chat_book_ids(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        book_id = str(value).strip()
        return book_id or None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_chat_mode(cls, value: Optional[str]) -> str:
        mode = str(value or "STANDARD").strip().upper()
        if mode not in {"STANDARD", "EXPLORER"}:
            raise ValueError("mode must be STANDARD or EXPLORER")
        return mode

    @field_validator("scope_mode", mode="before")
    @classmethod
    def normalize_scope_mode(cls, value: Optional[str]) -> str:
        scope_mode = str(value or "AUTO").strip().upper()
        if scope_mode not in {"AUTO", "BOOK_FIRST", "HIGHLIGHT_FIRST", "GLOBAL"}:
            raise ValueError("scope_mode must be AUTO, BOOK_FIRST, HIGHLIGHT_FIRST, or GLOBAL")
        return scope_mode

    @field_validator("compare_mode", mode="before")
    @classmethod
    def normalize_chat_compare_mode(cls, value: Optional[str]) -> str:
        compare_mode = str(value or "EXPLICIT_ONLY").strip().upper()
        if compare_mode not in {"EXPLICIT_ONLY", "AUTO"}:
            raise ValueError("compare_mode must be EXPLICIT_ONLY or AUTO")
        return compare_mode

    @field_validator("target_book_ids", mode="before")
    @classmethod
    def normalize_chat_target_book_ids(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None
        normalized: List[str] = []
        seen = set()
        for item in value:
            book_id = str(item or "").strip()
            if not book_id:
                continue
            truncated = book_id[:_BOOK_ID_MAX]
            if truncated in seen:
                continue
            seen.add(truncated)
            normalized.append(truncated)
            if len(normalized) >= _TARGET_BOOKS_MAX:
                break
        return normalized or None


class ChatResponse(BaseModel):
    answer: str
    session_id: int
    sources: List[Any]
    timestamp: str
    conversation_state: Optional[dict] = None
    thinking_history: Optional[List[Any]] = None
    metadata: Optional[dict] = None


class ComparisonRequest(BaseModel):
    firebase_uid: str = Field(..., min_length=1, max_length=_UID_MAX)
    target_book_ids: List[str] = Field(default_factory=list, min_length=2, max_length=20)
    term: str = Field(..., min_length=1, max_length=128)

    @field_validator("target_book_ids", mode="before")
    @classmethod
    def normalize_book_ids(cls, value: Optional[List[str]]) -> List[str]:
        if not value:
            raise ValueError("target_book_ids cannot be empty")
        normalized: List[str] = []
        for item in value:
            book_id = str(item or "").strip()
            if book_id:
                normalized.append(book_id[:_BOOK_ID_MAX])
        if len(normalized) < 2:
            raise ValueError("target_book_ids must contain at least 2 items")
        return normalized
