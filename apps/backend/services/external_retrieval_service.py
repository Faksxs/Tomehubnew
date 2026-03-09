import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from config import settings
from models.external_api_models import ExternalSearchRequest
from services.search_service import get_rag_context


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_tags = value
    else:
        text = str(value or "").strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = [part.strip() for part in text.split(",") if part.strip()]
        raw_tags = payload if isinstance(payload, list) else []

    tags: list[str] = []
    seen = set()
    for item in raw_tags:
        tag = str(item or "").strip()
        if not tag:
            continue
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(tag[:64])
        if len(tags) >= settings.EXTERNAL_API_MAX_TAGS_PER_RESULT:
            break
    return tags


def run_external_search(payload: ExternalSearchRequest, owner_firebase_uid: str) -> dict[str, Any]:
    visibility_scope = "all" if payload.include_private_notes else "default"
    effective_limit = min(int(payload.limit), int(settings.EXTERNAL_API_MAX_LIMIT))

    ctx = get_rag_context(
        payload.query,
        owner_firebase_uid,
        context_book_id=payload.book_id,
        mode=payload.mode,
        resource_type=payload.resource_type,
        limit=effective_limit,
        offset=payload.offset,
        scope_mode="GLOBAL",
        apply_scope_policy=False,
        visibility_scope=visibility_scope,
        content_type=payload.content_type,
        ingestion_type=payload.ingestion_type,
    )

    if not ctx:
        return {
            "results": [],
            "timestamp": datetime.now(timezone.utc),
            "metadata": {
                "query": payload.query,
                "mode": payload.mode,
                "result_count": 0,
                "status": "empty",
            },
        }

    results: list[dict[str, Any]] = []
    source_type_counts = Counter()

    for chunk in ctx.get("chunks", [])[:effective_limit]:
        source_type = str(chunk.get("source_type") or "").strip().upper() or None
        if source_type:
            source_type_counts[source_type] += 1
        results.append(
            {
                "chunk_id": int(chunk["id"]) if chunk.get("id") is not None else None,
                "item_id": str(chunk.get("book_id") or "").strip() or None,
                "title": str(chunk.get("title") or "Unknown"),
                "snippet": _safe_text(
                    chunk.get("content_chunk") or chunk.get("content") or "",
                    int(settings.EXTERNAL_API_MAX_SNIPPET_CHARS),
                ),
                "page_number": chunk.get("page_number"),
                "source_type": source_type,
                "score": float(chunk.get("score") or chunk.get("similarity_score") or 0.0),
                "tags": _parse_tags(chunk.get("tags")),
                "summary": _safe_text(chunk.get("summary"), 400) or None,
                "comment": _safe_text(chunk.get("comment"), 400) or None,
            }
        )

    return {
        "results": results,
        "timestamp": datetime.now(timezone.utc),
        "metadata": {
            "query": payload.query,
            "mode": ctx.get("mode", payload.mode),
            "intent": ctx.get("intent"),
            "confidence": ctx.get("confidence"),
            "result_count": len(results),
            "source_type_counts": dict(source_type_counts),
            "visibility_scope": visibility_scope,
            "search_log_id": ctx.get("search_log_id"),
            "retrieval_path": ctx.get("retrieval_path"),
        },
    }
