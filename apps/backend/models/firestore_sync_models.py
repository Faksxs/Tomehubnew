from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def _strip_html(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _as_timestamp_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        iv = int(value)
        return iv if iv >= 0 else None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            iv = int(raw)
            return iv if iv >= 0 else None
    if hasattr(value, "timestamp"):
        try:
            return int(value.timestamp() * 1000)
        except Exception:
            return None
    return None


def _as_author(value: Any) -> str:
    if isinstance(value, str):
        s = value.strip()
        return s if s else "Unknown"
    if isinstance(value, list):
        items = [str(v).strip() for v in value if str(v).strip()]
        if items:
            return ", ".join(items)[:256]
    return "Unknown"


def _dedupe_labels(raw: Any, max_items: int = 50, max_len: int = 64) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen = set()
    for item in raw[:max_items]:
        tag = str(item or "").strip()
        if not tag:
            continue
        k = tag.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(tag[:max_len])
    return out


def _normalize_item_type(value: Any) -> str:
    st = str(value or "BOOK").strip().upper()
    if st in {"NOTE", "PERSONAL"}:
        return "PERSONAL_NOTE"
    if st in {"NOTES", "HIGHLIGHTS"}:
        return "HIGHLIGHT"
    if st == "INSIGHTS":
        return "INSIGHT"
    return st or "BOOK"


def _normalize_highlight_type(value: Any) -> Literal["highlight", "insight"]:
    st = str(value or "highlight").strip().lower()
    if st in {"insight", "note"}:
        return "insight"
    return "highlight"


class StrictHighlight(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: Optional[str] = Field(default=None, max_length=128)
    text: str = Field(min_length=1, max_length=6000)
    type: Literal["highlight", "insight"] = "highlight"
    comment: Optional[str] = Field(default=None, max_length=2000)
    pageNumber: Optional[int] = Field(default=None, ge=0, le=100000)
    tags: list[str] = Field(default_factory=list)
    createdAt: Optional[int] = None


class StrictFirestoreItem(BaseModel):
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
    updatedAt: Optional[int] = None

    def entity_hash(self) -> str:
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
        }
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        return sha256(payload.encode("utf-8")).hexdigest()


def normalize_and_validate_item(item_id: str, raw: dict[str, Any]) -> StrictFirestoreItem:
    title = str((raw or {}).get("title") or "").strip() or "Untitled"
    author = _as_author((raw or {}).get("author"))
    item_type = _normalize_item_type((raw or {}).get("type"))
    publisher_raw = str((raw or {}).get("publisher") or "").strip()
    tags = _dedupe_labels((raw or {}).get("tags"))
    note_text = _strip_html(str((raw or {}).get("generalNotes") or ""))
    category = str((raw or {}).get("personalNoteCategory") or "PRIVATE").strip().upper() or "PRIVATE"
    if category not in {"PRIVATE", "DAILY", "IDEAS"}:
        category = "PRIVATE"

    raw_highlights = (raw or {}).get("highlights")
    highlights: list[dict[str, Any]] = []
    if isinstance(raw_highlights, list):
        for h in raw_highlights:
            if not isinstance(h, dict):
                continue
            text = str(h.get("text") or "").strip()
            if not text:
                continue
            highlights.append(
                {
                    "id": (str(h.get("id")).strip()[:128] if h.get("id") is not None else None),
                    "text": text[:6000],
                    "type": _normalize_highlight_type(h.get("type")),
                    "comment": (str(h.get("comment")).strip()[:2000] if h.get("comment") else None),
                    "pageNumber": int(h.get("pageNumber")) if str(h.get("pageNumber", "")).strip().isdigit() else None,
                    "tags": _dedupe_labels(h.get("tags")),
                    "createdAt": _as_timestamp_ms(h.get("createdAt")),
                }
            )

    normalized = {
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
    }
    return StrictFirestoreItem.model_validate(normalized)
