"""
Reconcile Oracle content with Firestore items for one user.

Goal:
- Find DB book_ids that no longer exist in Firestore `users/{uid}/items`
- Purge those stale book_ids from Oracle (content + aux tables)

Usage:
  python scripts/reconcile_deleted_items.py --firebase-uid <UID>
  python scripts/reconcile_deleted_items.py --firebase-uid <UID> --execute

Fallback (no Firebase Admin available):
  python scripts/reconcile_deleted_items.py --firebase-uid <UID> --active-book-ids "id1,id2,id3"
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Dict, Set

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager  # noqa: E402
from services.ingestion_service import purge_item_content  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile deleted items: Firestore vs Oracle DB."
    )
    parser.add_argument("--firebase-uid", required=True, help="Target Firebase UID")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply deletion. Without this, script runs as dry-run.",
    )
    parser.add_argument(
        "--active-book-ids",
        default="",
        help="Optional comma-separated active Firestore item IDs (manual override).",
    )
    parser.add_argument(
        "--show-limit",
        type=int,
        default=100,
        help="Max stale IDs to print in dry-run output.",
    )
    return parser.parse_args()


def _load_active_book_ids(firebase_uid: str, active_book_ids_csv: str) -> Set[str]:
    manual_ids = {
        x.strip() for x in str(active_book_ids_csv or "").split(",") if x.strip()
    }
    if manual_ids:
        return manual_ids

    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError(
            "Firebase Admin is not ready. Provide --active-book-ids or configure credentials."
        )

    from firebase_admin import firestore

    db = firestore.client()
    docs = (
        db.collection("users")
        .document(firebase_uid)
        .collection("items")
        .stream()
    )
    return {str(doc.id).strip() for doc in docs if str(doc.id).strip()}


def _load_db_book_id_counts(firebase_uid: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT book_id, COUNT(*)
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = :p_uid
                  AND book_id IS NOT NULL
                GROUP BY book_id
                """,
                {"p_uid": firebase_uid},
            )
            for row in cursor.fetchall():
                book_id = str(row[0] or "").strip()
                if not book_id:
                    continue
                out[book_id] = int(row[1] or 0)
    return out


def main() -> int:
    args = _parse_args()
    firebase_uid = str(args.firebase_uid or "").strip()
    if not firebase_uid:
        print("[ERROR] --firebase-uid is required")
        return 2

    DatabaseManager.init_pool()
    try:
        active_ids = _load_active_book_ids(firebase_uid, args.active_book_ids)
        db_counts = _load_db_book_id_counts(firebase_uid)

        stale_ids = sorted([book_id for book_id in db_counts.keys() if book_id not in active_ids])
        print(f"[INFO] uid={firebase_uid}")
        print(f"[INFO] Firestore active item count: {len(active_ids)}")
        print(f"[INFO] Oracle distinct book_id count: {len(db_counts)}")
        print(f"[INFO] Stale book_id count: {len(stale_ids)}")

        if stale_ids:
            print("[INFO] Sample stale IDs:")
            for book_id in stale_ids[: max(0, int(args.show_limit))]:
                print(f"  - {book_id} (rows={db_counts.get(book_id, 0)})")

        if not args.execute:
            print("[DRY-RUN] No deletion applied. Re-run with --execute.")
            return 0

        total_deleted = 0
        aux_counter: Counter = Counter()
        failed = []

        for book_id in stale_ids:
            result = purge_item_content(firebase_uid=firebase_uid, book_id=book_id)
            if not result.get("success"):
                failed.append({"book_id": book_id, "error": result.get("error", "unknown_error")})
                continue
            total_deleted += int(result.get("deleted", 0) or 0)
            for key, value in (result.get("aux_deleted") or {}).items():
                aux_counter[key] += int(value or 0)

        remaining_counts = _load_db_book_id_counts(firebase_uid)
        remaining_stale = sorted([book_id for book_id in remaining_counts.keys() if book_id not in active_ids])

        print(f"[APPLY] Purged stale ids: {len(stale_ids) - len(failed)}")
        print(f"[APPLY] Deleted rows from TOMEHUB_CONTENT: {total_deleted}")
        print(f"[APPLY] Aux deletes: {dict(aux_counter)}")
        print(f"[VERIFY] Remaining stale ids: {len(remaining_stale)}")
        if failed:
            print(f"[WARN] Failed purges: {len(failed)}")
            for item in failed[:20]:
                print(f"  - {item['book_id']}: {item['error']}")
            return 1
        return 0
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())

