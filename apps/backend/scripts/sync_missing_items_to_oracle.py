"""
Sync active Firestore items that are missing in Oracle for one user.

This script is safe by default:
- It only targets Firestore item IDs that are NOT present in Oracle (TOMEHUB_CONTENT.book_id)
- It does not delete existing Oracle rows

Usage:
  python scripts/sync_missing_items_to_oracle.py --firebase-uid <UID>
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Set

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager  # noqa: E402
from services.ingestion_service import (  # noqa: E402
    ingest_text_item,
    sync_highlights_for_item,
    sync_personal_note_for_item,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync missing Firestore items to Oracle")
    parser.add_argument("--firebase-uid", required=True, help="Target Firebase UID")
    parser.add_argument(
        "--show-limit",
        type=int,
        default=30,
        help="Max sample missing items printed before sync",
    )
    return parser.parse_args()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _safe_console(text: Any) -> str:
    return str(text).encode("ascii", errors="replace").decode("ascii")


def _load_firestore_items(firebase_uid: str) -> Dict[str, Dict[str, Any]]:
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError("FIREBASE_READY is false; configure Firebase Admin first.")

    from firebase_admin import firestore

    db = firestore.client()
    docs = (
        db.collection("users")
        .document(firebase_uid)
        .collection("items")
        .stream()
    )
    out: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        data = doc.to_dict() or {}
        out[str(doc.id)] = data
    return out


def _load_oracle_book_ids(firebase_uid: str) -> Set[str]:
    out: Set[str] = set()
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT book_id
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = :p_uid
                  AND book_id IS NOT NULL
                """,
                {"p_uid": firebase_uid},
            )
            for row in cursor.fetchall():
                bid = str(row[0] or "").strip()
                if bid:
                    out.add(bid)
    return out


def _build_text(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    title = str(item.get("title") or "").strip()
    author = str(item.get("author") or "").strip()
    if title:
        parts.append(f"Title: {title}")
    if author:
        parts.append(f"Author: {author}")
    publisher = str(item.get("publisher") or "").strip()
    if publisher:
        parts.append(f"Publisher: {publisher}")
    tags = item.get("tags") or []
    if isinstance(tags, list) and tags:
        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
        if clean_tags:
            parts.append(f"Tags: {', '.join(clean_tags)}")
    notes = _strip_html(str(item.get("generalNotes") or ""))
    if notes:
        parts.append(f"Content/Notes: {notes}")
    return "\n".join(parts).strip()


def _normalize_highlights(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for h in raw:
        if not isinstance(h, dict):
            continue
        text = str(h.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "id": h.get("id"),
                "text": text,
                "type": h.get("type", "highlight"),
                "comment": h.get("comment"),
                "pageNumber": h.get("pageNumber"),
                "tags": h.get("tags") or [],
                "createdAt": h.get("createdAt"),
            }
        )
    return out


def main() -> int:
    args = _parse_args()
    uid = str(args.firebase_uid or "").strip()
    if not uid:
        print("[ERROR] firebase uid required")
        return 2

    firestore_items = _load_firestore_items(uid)
    fs_ids = set(firestore_items.keys())

    DatabaseManager.init_pool()
    try:
        oracle_ids = _load_oracle_book_ids(uid)
        missing_ids = sorted(fs_ids - oracle_ids)

        print(f"[INFO] uid={uid}")
        print(f"[INFO] Firestore active items: {len(fs_ids)}")
        print(f"[INFO] Oracle represented items: {len(oracle_ids)}")
        print(f"[INFO] Missing items to sync: {len(missing_ids)}")

        type_counter = Counter(
            str((firestore_items.get(item_id) or {}).get("type") or "UNKNOWN").upper()
            for item_id in missing_ids
        )
        if type_counter:
            print(f"[INFO] Missing-by-type: {dict(type_counter)}")

        for item_id in missing_ids[: max(0, int(args.show_limit))]:
            item = firestore_items[item_id]
            print(
                f"  - id={_safe_console(item_id)} | type={_safe_console(item.get('type') or '')} | title={_safe_console(item.get('title') or '')}"
            )

        synced = 0
        failed = 0
        highlight_synced = 0
        skipped_non_ideas_notes = 0

        expected_present_ids: Set[str] = set()
        for item_id, item in firestore_items.items():
            item_type = str(item.get("type") or "").strip().upper()
            if item_type != "PERSONAL_NOTE":
                expected_present_ids.add(item_id)
                continue
            category = str(item.get("personalNoteCategory") or "PRIVATE").strip().upper() or "PRIVATE"
            if category == "IDEAS":
                expected_present_ids.add(item_id)

        for item_id in missing_ids:
            item = firestore_items[item_id]
            item_type = str(item.get("type") or "").strip().upper()
            title = str(item.get("title") or "Untitled").strip() or "Untitled"
            author = str(item.get("author") or "Unknown").strip() or "Unknown"
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []

            try:
                if item_type == "PERSONAL_NOTE":
                    category = str(item.get("personalNoteCategory") or "PRIVATE").strip().upper() or "PRIVATE"
                    if category != "IDEAS":
                        skipped_non_ideas_notes += 1
                        continue
                    content = _strip_html(str(item.get("generalNotes") or ""))
                    result = sync_personal_note_for_item(
                        firebase_uid=uid,
                        book_id=item_id,
                        title=title,
                        author=author,
                        content=content,
                        tags=tags,
                        category=category,
                        delete_only=False,
                    )
                    if not result.get("success"):
                        raise RuntimeError(result.get("error", "sync_personal_note_failed"))
                else:
                    text = _build_text(item)
                    if len(text) < 12:
                        text = f"Title: {title}\nAuthor: {author}"
                    ok = ingest_text_item(
                        text=text,
                        title=title,
                        author=author,
                        source_type=item_type or "BOOK",
                        firebase_uid=uid,
                        book_id=item_id,
                        tags=tags,
                    )
                    if not ok:
                        raise RuntimeError("ingest_text_item_failed")

                highlights = _normalize_highlights(item.get("highlights"))
                if highlights:
                    h_result = sync_highlights_for_item(
                        firebase_uid=uid,
                        book_id=item_id,
                        title=title,
                        author=author,
                        highlights=highlights,
                    )
                    if h_result.get("success"):
                        highlight_synced += 1

                synced += 1
            except Exception as e:
                failed += 1
                print(f"[WARN] sync failed id={_safe_console(item_id)} title={_safe_console(title)}: {_safe_console(e)}")

        remaining_ids = _load_oracle_book_ids(uid)
        still_missing = len(expected_present_ids - remaining_ids)
        print(
            f"[DONE] Synced: {synced}, Failed: {failed}, Highlight-synced: {highlight_synced}, "
            f"Skipped non-IDEAS personal notes: {skipped_non_ideas_notes}"
        )
        print(f"[VERIFY] Remaining missing items (policy-aware): {still_missing}")
        return 0 if still_missing == 0 else 1
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
