"""
Reconcile Firestore highlight/insight parity into Oracle for one user.

Purpose:
- Detect highlight/insight mismatches per item (Firestore vs Oracle)
- Optionally repair with full replace sync (`sync_highlights_for_item`)

Safety:
- Dry-run by default
- PERSONAL_NOTE items are excluded from highlight parity repair to avoid
  touching personal-note INSIGHT rows (handled by personal-note sync path)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402
from models.firestore_sync_models import StrictHighlight, normalize_and_validate_item  # noqa: E402
from services.ingestion_service import sync_highlights_for_item  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile Firestore highlight parity to Oracle")
    parser.add_argument("--firebase-uid", required=True, help="Target Firebase UID")
    parser.add_argument("--execute", action="store_true", help="Run write repairs (default dry-run)")
    parser.add_argument("--max-items", type=int, default=0, help="Process cap (0=all)")
    parser.add_argument(
        "--show-samples",
        type=int,
        default=10,
        help="How many mismatch samples to print",
    )
    return parser.parse_args()


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_tags(raw: Any) -> list[str]:
    value = raw
    if value is None:
        return []
    if not isinstance(value, str):
        value = safe_read_clob(value)
    text = str(value or "").strip()
    if not text:
        return []
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except Exception:
        # fall back to comma-separated if legacy payload exists
        parsed = [p.strip() for p in text.split(",") if p.strip()]
    if not isinstance(parsed, list):
        return []

    out: list[str] = []
    seen = set()
    for tag in parsed:
        s = _collapse_ws(str(tag or ""))
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    out.sort(key=lambda x: x.casefold())
    return out


def _fs_highlight_signature(h: StrictHighlight) -> str:
    payload = {
        "type": "insight" if str(h.type).lower() == "insight" else "highlight",
        "text": _collapse_ws(h.text),
        "comment": _collapse_ws(h.comment or "") or None,
        "pageNumber": int(h.pageNumber) if h.pageNumber is not None else None,
        "tags": sorted([_collapse_ws(t) for t in (h.tags or []) if _collapse_ws(t)], key=lambda x: x.casefold()),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _ora_highlight_signature(
    *,
    source_type: str,
    content_chunk: Any,
    comment: Any,
    page_number: Any,
    tags: Any,
) -> str:
    st = str(source_type or "").strip().upper()
    mapped_type = "insight" if st in {"INSIGHT", "NOTES"} else "highlight"
    page_val = None
    try:
        page_val = int(page_number) if page_number is not None else None
    except Exception:
        page_val = None
    payload = {
        "type": mapped_type,
        "text": _collapse_ws(safe_read_clob(content_chunk)),
        "comment": _collapse_ws(safe_read_clob(comment)) or None,
        "pageNumber": page_val,
        "tags": _normalize_tags(tags),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _load_firestore_items(firebase_uid: str) -> dict[str, dict[str, Any]]:
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError("FIREBASE_READY is false; configure Firebase Admin first.")

    from firebase_admin import firestore

    db = firestore.client()
    docs = db.collection("users").document(firebase_uid).collection("items").stream()
    out: dict[str, dict[str, Any]] = {}
    for doc in docs:
        out[str(doc.id)] = doc.to_dict() or {}
    return out


def _load_oracle_highlight_counters(firebase_uid: str) -> dict[str, Counter[str]]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT BOOK_ID, SOURCE_TYPE, CONTENT_CHUNK, "COMMENT", PAGE_NUMBER, TAGS, CHUNK_TYPE
                FROM TOMEHUB_CONTENT
                WHERE FIREBASE_UID = :p_uid
                  AND SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT', 'NOTES')
                """,
                {"p_uid": firebase_uid},
            )
            for row in cursor.fetchall():
                book_id = str(row[0] or "").strip()
                if not book_id:
                    continue
                source_type = str(row[1] or "").upper()
                chunk_type = str(row[6] or "").lower()
                # Exclude personal-note rows that may be stored as INSIGHT.
                if source_type == "INSIGHT" and chunk_type.startswith("personal_note"):
                    continue
                sig = _ora_highlight_signature(
                    source_type=source_type,
                    content_chunk=row[2],
                    comment=row[3],
                    page_number=row[4],
                    tags=row[5],
                )
                counters[book_id][sig] += 1
    return counters


@dataclass
class ItemParity:
    book_id: str
    item_type: str
    title: str
    fs_highlights: int
    ora_highlights: int
    missing_from_oracle: int
    extra_in_oracle: int


def main() -> int:
    args = _parse_args()
    uid = str(args.firebase_uid or "").strip()
    if not uid:
        print("[ERROR] firebase uid required")
        return 2

    dry_run = not bool(args.execute)
    print(f"[INFO] uid={uid} dry_run={dry_run}")

    raw_items = _load_firestore_items(uid)
    oracle_counters = _load_oracle_highlight_counters(uid)

    mismatches: list[ItemParity] = []
    scanned = 0
    validated = 0
    skipped_personal_notes = 0
    fs_total_highlights = 0
    ora_total_highlights_scoped = 0
    repaired = 0
    failed = 0

    item_ids = sorted(raw_items.keys())
    if int(args.max_items or 0) > 0:
        item_ids = item_ids[: int(args.max_items)]

    for item_id in item_ids:
        scanned += 1
        try:
            item = normalize_and_validate_item(item_id, raw_items.get(item_id) or {})
        except Exception as e:
            failed += 1
            print(f"[WARN] validation_failed item={item_id} err={e}")
            continue

        validated += 1
        if str(item.type).upper() == "PERSONAL_NOTE":
            skipped_personal_notes += 1
            continue

        fs_counter = Counter(_fs_highlight_signature(h) for h in item.highlights)
        ora_counter = oracle_counters.get(item.book_id, Counter())

        fs_count = sum(fs_counter.values())
        ora_count = sum(ora_counter.values())
        fs_total_highlights += fs_count
        ora_total_highlights_scoped += ora_count

        if fs_counter == ora_counter:
            continue

        missing = sum((fs_counter - ora_counter).values())
        extra = sum((ora_counter - fs_counter).values())
        mismatches.append(
            ItemParity(
                book_id=item.book_id,
                item_type=item.type,
                title=item.title,
                fs_highlights=fs_count,
                ora_highlights=ora_count,
                missing_from_oracle=missing,
                extra_in_oracle=extra,
            )
        )

        if dry_run:
            continue

        result = sync_highlights_for_item(
            firebase_uid=uid,
            book_id=item.book_id,
            title=item.title,
            author=item.author,
            highlights=[h.model_dump() for h in item.highlights],
        )
        if result.get("success"):
            repaired += 1
        else:
            failed += 1
            print(
                f"[WARN] repair_failed book_id={item.book_id} title={item.title} "
                f"err={result.get('error')}"
            )

    print(
        "[SUMMARY]",
        f"scanned={scanned}",
        f"validated={validated}",
        f"skipped_personal_notes={skipped_personal_notes}",
        f"mismatches={len(mismatches)}",
        f"repaired={repaired}",
        f"failed={failed}",
        f"fs_total_highlights_scoped={fs_total_highlights}",
        f"ora_total_highlights_scoped_before={ora_total_highlights_scoped}",
    )

    if mismatches:
        print(f"[SAMPLES] showing up to {max(0, int(args.show_samples))} mismatches")
        for row in mismatches[: max(0, int(args.show_samples))]:
            print(
                f" - {row.item_type} | {row.book_id} | {row.title} | "
                f"fs={row.fs_highlights} ora={row.ora_highlights} "
                f"missing={row.missing_from_oracle} extra={row.extra_in_oracle}"
            )

    # Post-check after execute
    if not dry_run:
        oracle_after = _load_oracle_highlight_counters(uid)
        remaining = 0
        for item_id in item_ids:
            try:
                item = normalize_and_validate_item(item_id, raw_items.get(item_id) or {})
            except Exception:
                continue
            if str(item.type).upper() == "PERSONAL_NOTE":
                continue
            fs_counter = Counter(_fs_highlight_signature(h) for h in item.highlights)
            ora_counter = oracle_after.get(item.book_id, Counter())
            if fs_counter != ora_counter:
                remaining += 1
        print(f"[POSTCHECK] remaining_mismatched_items={remaining}")
        return 0 if remaining == 0 and failed == 0 else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
