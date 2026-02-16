"""
Bulk enrich Firestore BOOK items using backend enrich_book_async logic.

This runs the same core enrichment used by /api/ai/enrich-book and writes
results back to Firestore (summary/tags + metadata fields when available).

Usage:
  python scripts/bulk_enrich_books_firestore.py --firebase-uid <UID>
  python scripts/bulk_enrich_books_firestore.py --firebase-uid <UID> --limit 150 --concurrency 2
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import settings  # noqa: E402
from services.ai_service import enrich_book_async  # noqa: E402


def _safe_console(value: Any) -> str:
    return str(value).encode("ascii", errors="replace").decode("ascii")


def _normalize_source_hint(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"tr", "turkish", "turkce", "türkçe", "turkçe"}:
        return "tr"
    if raw in {"en", "english", "ingilizce"}:
        return "en"
    return None


def _coerce_year(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    m = re.search(r"(1[6-9]\d{2}|20\d{2}|2100)", text)
    if not m:
        return None
    return m.group(1)


def _coerce_page_count(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        num = int(float(value))
        if num > 0:
            return num
    except Exception:
        return None
    return None


def _prepare_payload(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    summary = str(doc_data.get("generalNotes") or doc_data.get("summary") or "").strip()
    tags = doc_data.get("tags") if isinstance(doc_data.get("tags"), list) else []
    return {
        "title": str(doc_data.get("title") or "").strip(),
        "author": str(doc_data.get("author") or "").strip(),
        "publisher": str(doc_data.get("publisher") or "").strip(),
        "isbn": str(doc_data.get("isbn") or "").strip(),
        "translator": str(doc_data.get("translator") or "").strip(),
        "pageCount": _coerce_page_count(doc_data.get("pageCount")),
        "publishedDate": str(doc_data.get("publicationYear") or doc_data.get("publishedDate") or "").strip(),
        "summary": summary,
        "tags": tags,
        "content_language_mode": str(doc_data.get("contentLanguageMode") or "AUTO").strip().upper(),
        "source_language_hint": _normalize_source_hint(doc_data.get("sourceLanguageHint")),
        "force_regenerate": True,
    }


def _build_patch(original: Dict[str, Any], enriched: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}

    summary = str(enriched.get("summary") or "").strip()
    if summary:
        patch["generalNotes"] = summary

    tags = enriched.get("tags")
    if isinstance(tags, list):
        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
        if clean_tags:
            patch["tags"] = clean_tags

    for source_key, target_key in (
        ("publisher", "publisher"),
        ("isbn", "isbn"),
        ("author", "author"),
        ("translator", "translator"),
    ):
        value = str(enriched.get(source_key) or "").strip()
        if value:
            patch[target_key] = value

    year = _coerce_year(enriched.get("publishedDate"))
    if year:
        patch["publicationYear"] = year

    page_count = _coerce_page_count(enriched.get("pageCount"))
    if page_count:
        patch["pageCount"] = page_count

    patch["contentLanguageMode"] = str(original.get("contentLanguageMode") or "AUTO").strip().upper() or "AUTO"

    resolved = str(enriched.get("content_language_resolved") or "").strip().lower()
    if resolved in {"tr", "en"}:
        patch["contentLanguageResolved"] = resolved

    reason = str(enriched.get("language_decision_reason") or "").strip()
    if reason:
        patch["languageDecisionReason"] = reason

    confidence = enriched.get("language_decision_confidence")
    if isinstance(confidence, (float, int)):
        patch["languageDecisionConfidence"] = float(confidence)

    source_hint = _normalize_source_hint(enriched.get("source_language_hint"))
    if source_hint:
        patch["sourceLanguageHint"] = source_hint

    return patch


async def _enrich_one(
    uid: str,
    doc: Any,
    semaphore: asyncio.Semaphore,
    delay_sec: float,
    dry_run: bool,
) -> Dict[str, Any]:
    data = doc.to_dict() or {}
    book_id = str(doc.id)
    title = str(data.get("title") or "")

    payload = _prepare_payload(data)
    if not payload["title"] or not payload["author"]:
        return {"book_id": book_id, "title": title, "status": "skipped", "reason": "missing_title_or_author"}

    async with semaphore:
        try:
            enriched = await enrich_book_async(payload)
            patch = _build_patch(data, enriched)
            if not patch:
                return {"book_id": book_id, "title": title, "status": "skipped", "reason": "empty_patch"}
            if not dry_run:
                doc.reference.set(patch, merge=True)
            await asyncio.sleep(max(0.0, delay_sec))
            return {
                "book_id": book_id,
                "title": title,
                "status": "updated",
                "fields": list(patch.keys()),
            }
        except Exception as e:
            return {
                "book_id": book_id,
                "title": title,
                "status": "failed",
                "error": str(e),
            }


async def _run(
    firebase_uid: str,
    limit: int,
    concurrency: int,
    delay_sec: float,
    dry_run: bool,
) -> int:
    if not settings.FIREBASE_READY:
        print("[ERROR] Firebase Admin SDK is not ready.")
        return 2

    from firebase_admin import firestore

    db = firestore.client()
    query = (
        db.collection("users")
        .document(firebase_uid)
        .collection("items")
        .where("type", "==", "BOOK")
    )
    docs = list(query.stream())
    docs.sort(key=lambda d: int((d.to_dict() or {}).get("addedAt") or 0))
    if limit > 0:
        docs = docs[:limit]

    total = len(docs)
    print(f"[INFO] uid={firebase_uid} total_books={total} limit={limit} concurrency={concurrency} dry_run={dry_run}")
    if total == 0:
        return 0

    semaphore = asyncio.Semaphore(max(1, concurrency))
    tasks = [
        asyncio.create_task(
            _enrich_one(
                uid=firebase_uid,
                doc=doc,
                semaphore=semaphore,
                delay_sec=delay_sec,
                dry_run=dry_run,
            )
        )
        for doc in docs
    ]

    updated = 0
    failed = 0
    skipped = 0
    errors: List[Dict[str, Any]] = []

    processed = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        processed += 1
        status = result.get("status")
        if status == "updated":
            updated += 1
        elif status == "failed":
            failed += 1
            if len(errors) < 25:
                errors.append(result)
        else:
            skipped += 1

        if processed % 10 == 0 or processed == total:
            print(f"[PROGRESS] {processed}/{total} updated={updated} failed={failed} skipped={skipped}")

    print(f"[DONE] updated={updated} failed={failed} skipped={skipped} total={total}")
    if errors:
        print("[ERRORS] sample:")
        for err in errors[:10]:
            print(
                f"  - id={_safe_console(err.get('book_id'))} "
                f"title={_safe_console(err.get('title'))} "
                f"error={_safe_console(err.get('error'))}"
            )
    return 1 if failed > 0 else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk enrich Firestore BOOK records")
    parser.add_argument("--firebase-uid", required=True, help="Target Firebase UID")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process (0=all)")
    parser.add_argument("--concurrency", type=int, default=2, help="Parallel enrich tasks")
    parser.add_argument("--delay-sec", type=float, default=0.12, help="Delay after each item write")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to Firestore")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    uid = str(args.firebase_uid or "").strip()
    if not uid:
        print("[ERROR] firebase uid is required")
        return 2
    return asyncio.run(
        _run(
            firebase_uid=uid,
            limit=max(0, int(args.limit)),
            concurrency=max(1, int(args.concurrency)),
            delay_sec=max(0.0, float(args.delay_sec)),
            dry_run=bool(args.dry_run),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

