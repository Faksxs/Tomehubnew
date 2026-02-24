import os
path = 'models/firestore_sync_models.py'

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update StrictFirestoreItem
old_model = """class StrictFirestoreItem(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    book_id: str = Field(min_length=1, max_length=256)
    type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    author: str = Field(min_length=1, max_length=256)
    publisher: Optional[str] = Field(default=None, max_length=256)
    tags: list[str] = Field(default_factory=list)
    generalNotes: str = Field(default="", max_length=20000)
    highlights: list[StrictHighlight] = Field(default_factory=list)
    personalNoteCategory: str = Field(default="PRIVATE", max_length=32)
    updatedAt: Optional[int] = None"""

new_model = """class StrictFirestoreItem(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    book_id: str = Field(min_length=1, max_length=256)
    type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    author: str = Field(min_length=1, max_length=256)
    publisher: Optional[str] = Field(default=None, max_length=256)
    translator: Optional[str] = Field(default=None, max_length=256)
    publicationYear: Optional[int] = None
    isbn: Optional[str] = Field(default=None, max_length=256)
    url: Optional[str] = Field(default=None, max_length=2000)
    pageCount: Optional[int] = None
    coverUrl: Optional[str] = Field(default=None, max_length=2000)
    summary: Optional[str] = Field(default=None, max_length=20000)
    categories: Optional[list[str]] = Field(default_factory=list)
    readingStatus: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, max_length=64)
    isFavorite: Optional[bool] = None
    tags: list[str] = Field(default_factory=list)
    generalNotes: str = Field(default="", max_length=20000)
    highlights: list[StrictHighlight] = Field(default_factory=list)
    personalNoteCategory: str = Field(default="PRIVATE", max_length=32)
    updatedAt: Optional[int] = None"""

text = text.replace(old_model, new_model)

# 2. Update entity_hash
old_hash = """    def entity_hash(self) -> str:
        data = {
            "book_id": self.book_id,
            "type": self.type,
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "tags": self.tags,
            "generalNotes": self.generalNotes,
            "highlights": [h.model_dump() for h in self.highlights],
            "personalNoteCategory": self.personalNoteCategory,
            "updatedAt": self.updatedAt,
        }"""

new_hash = """    def entity_hash(self) -> str:
        data = {
            "book_id": self.book_id,
            "type": self.type,
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "translator": self.translator,
            "publicationYear": self.publicationYear,
            "isbn": self.isbn,
            "url": self.url,
            "pageCount": self.pageCount,
            "coverUrl": self.coverUrl,
            "summary": self.summary,
            "categories": self.categories,
            "readingStatus": self.readingStatus,
            "status": self.status,
            "isFavorite": self.isFavorite,
            "tags": self.tags,
            "generalNotes": self.generalNotes,
            "highlights": [h.model_dump() for h in self.highlights],
            "personalNoteCategory": self.personalNoteCategory,
            "updatedAt": self.updatedAt,
        }"""

text = text.replace(old_hash, new_hash)

# 3. Update normalize_and_validate_item dict construction
old_dict = """    normalized = {
        "book_id": str(item_id or "").strip()[:256],
        "type": item_type,
        "title": title[:256],
        "author": author[:256],
        "publisher": publisher_raw[:256] if publisher_raw else None,
        "tags": tags,
        "generalNotes": note_text[:20000],
        "highlights": highlights,
        "personalNoteCategory": category,
        "updatedAt": _as_timestamp_ms((raw or {}).get("updatedAt")),
    }"""

new_dict = """    def _safe_int(v):
        try: return int(v) if v is not None else None
        except: return None
        
    normalized = {
        "book_id": str(item_id or "").strip()[:256],
        "type": item_type,
        "title": title[:256],
        "author": author[:256],
        "publisher": publisher_raw[:256] if publisher_raw else None,
        "translator": str((raw or {}).get("translator") or "").strip()[:256] or None,
        "publicationYear": _safe_int((raw or {}).get("publicationYear")),
        "isbn": str((raw or {}).get("isbn") or "").strip()[:256] or None,
        "url": str((raw or {}).get("url") or "").strip()[:2000] or None,
        "pageCount": _safe_int((raw or {}).get("pageCount")),
        "coverUrl": str((raw or {}).get("coverUrl") or "").strip()[:2000] or None,
        "summary": str((raw or {}).get("summary") or "").strip()[:20000] or None,
        "categories": (raw or {}).get("categories", []),
        "readingStatus": str((raw or {}).get("readingStatus") or "").strip()[:64] or None,
        "status": str((raw or {}).get("status") or "").strip()[:64] or None,
        "isFavorite": bool((raw or {}).get("isFavorite")),
        "tags": tags,
        "generalNotes": note_text[:20000],
        "highlights": highlights,
        "personalNoteCategory": category,
        "updatedAt": _as_timestamp_ms((raw or {}).get("updatedAt")),
    }"""

text = text.replace(old_dict, new_dict)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("firestore_sync_models.py has been updated!")
