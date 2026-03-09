from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


_QUERY_MAX = 2000
_BOOK_ID_MAX = 256


class ExternalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=_QUERY_MAX)
    book_id: Optional[str] = Field(default=None, max_length=_BOOK_ID_MAX)
    resource_type: Optional[str] = Field(default=None, max_length=64)
    mode: str = Field(default="STANDARD", max_length=16)
    include_private_notes: bool = False
    content_type: Optional[str] = Field(default=None, max_length=64)
    ingestion_type: Optional[str] = Field(default=None, max_length=64)
    limit: int = Field(default=8, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("query cannot be empty")
        return text

    @field_validator("book_id", mode="before")
    @classmethod
    def normalize_book_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("resource_type", "content_type", "ingestion_type", mode="before")
    @classmethod
    def normalize_upper_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None

    @field_validator("mode", mode="before")
    @classmethod
    def normalize_mode(cls, value: Optional[str]) -> str:
        mode = str(value or "STANDARD").strip().upper()
        if mode not in {"STANDARD", "EXPLORER"}:
            raise ValueError("mode must be STANDARD or EXPLORER")
        return mode


class ExternalSearchResult(BaseModel):
    chunk_id: Optional[int] = None
    item_id: Optional[str] = None
    title: str
    snippet: str
    page_number: Optional[float] = None
    source_type: Optional[str] = None
    score: float = 0.0
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    comment: Optional[str] = None


class ExternalSearchResponse(BaseModel):
    results: List[ExternalSearchResult] = Field(default_factory=list)
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)
