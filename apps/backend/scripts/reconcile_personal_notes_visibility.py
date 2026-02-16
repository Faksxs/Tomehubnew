"""
Reconcile personal-note visibility in Layer 3 (Oracle store).

Use-cases:
1) Dry-run legacy private candidates still present in TOMEHUB_CONTENT
2) Delete those candidates safely by user
3) Verify a specific leaked title disappears (e.g. "Dogum gunu - Self")
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Dict, List, Set

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from infrastructure.db_manager import DatabaseManager  # noqa: E402


def _build_candidate_sql(include_insight_legacy: bool) -> str:
    criteria = ["source_type = 'PERSONAL_NOTE'"]
    if include_insight_legacy:
        criteria.append(
            "(source_type = 'INSIGHT' AND LOWER(NVL(chunk_type, '')) = 'personal_note' "
            "AND LOWER(title) LIKE '% - self')"
        )
    where_clause = " OR ".join(criteria)
    return f"""
        SELECT id, book_id, source_type, title, chunk_type
        FROM TOMEHUB_CONTENT
        WHERE firebase_uid = :p_uid
          AND ({where_clause})
        ORDER BY id DESC
    """


def _fetch_candidates(firebase_uid: str, include_insight_legacy: bool) -> List[Dict]:
    sql = _build_candidate_sql(include_insight_legacy=include_insight_legacy)
    rows: List[Dict] = []

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, {"p_uid": firebase_uid})
            for row in cursor.fetchall():
                rows.append(
                    {
                        "id": int(row[0]),
                        "book_id": row[1],
                        "source_type": row[2],
                        "title": row[3],
                        "chunk_type": row[4],
                    }
                )
    return rows


def _count_title(firebase_uid: str, title_lc: str) -> int:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = :p_uid
                  AND LOWER(title) = :p_title
                """,
                {"p_uid": firebase_uid, "p_title": title_lc},
            )
            return int(cursor.fetchone()[0] or 0)


def _invalidate_user_cache(firebase_uid: str) -> None:
    try:
        from services.cache_service import get_cache

        cache = get_cache()
        if not cache:
            print("[CACHE] No global cache instance found in this process (skip).")
            return
        pattern = f"search:*:{firebase_uid}:*"
        cache.delete_pattern(pattern)
        print(f"[CACHE] Invalidated pattern: {pattern}")
    except Exception as e:
        print(f"[CACHE] Invalidation failed (non-critical): {e}")


def _delete_by_ids(firebase_uid: str, ids: List[int]) -> int:
    if not ids:
        return 0
    deleted = 0
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            for content_id in ids:
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND id = :p_id
                    """,
                    {"p_uid": firebase_uid, "p_id": content_id},
                )
                deleted += int(cursor.rowcount or 0)
        conn.commit()
    return deleted


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile personal-note visibility in Oracle.")
    parser.add_argument(
        "--firebase-uid",
        required=True,
        help="Target user UID",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply deletion. Without this flag, runs dry-run only.",
    )
    parser.add_argument(
        "--include-insight-legacy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include INSIGHT/personal_note rows with title ending '- Self' as legacy candidates.",
    )
    parser.add_argument(
        "--keep-book-ids",
        default="",
        help="Comma-separated BOOK_ID values to exclude from deletion.",
    )
    parser.add_argument(
        "--verify-title",
        default="dogum gunu - self",
        help="Lower-cased exact title to verify before/after cleanup.",
    )
    parser.add_argument(
        "--show-limit",
        type=int,
        default=100,
        help="Max dry-run rows to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    firebase_uid = args.firebase_uid.strip()
    keep_book_ids: Set[str] = {
        bid.strip() for bid in str(args.keep_book_ids or "").split(",") if bid.strip()
    }

    if not firebase_uid:
        print("[ERROR] firebase uid is required")
        return 2

    DatabaseManager.init_pool()
    try:
        before_title_count = _count_title(firebase_uid, args.verify_title.strip().lower())
        candidates = _fetch_candidates(firebase_uid, include_insight_legacy=args.include_insight_legacy)
        if keep_book_ids:
            candidates = [r for r in candidates if (r.get("book_id") or "") not in keep_book_ids]

        print(f"[INFO] UID: {firebase_uid}")
        print(f"[INFO] Candidate count: {len(candidates)}")
        print(f"[INFO] Verify title '{args.verify_title}': {before_title_count} row(s) before")

        by_type = Counter([r.get("source_type") or "UNKNOWN" for r in candidates])
        if by_type:
            print(f"[INFO] Candidate types: {dict(by_type)}")

        for row in candidates[: max(0, args.show_limit)]:
            print(
                f"  - id={row['id']}, book_id={row['book_id']}, "
                f"type={row['source_type']}, chunk_type={row['chunk_type']}, title={row['title']}"
            )

        if not args.execute:
            print("[DRY-RUN] No deletion applied. Re-run with --execute to apply.")
            return 0

        ids = [int(r["id"]) for r in candidates]
        deleted = _delete_by_ids(firebase_uid=firebase_uid, ids=ids)
        _invalidate_user_cache(firebase_uid)

        after_title_count = _count_title(firebase_uid, args.verify_title.strip().lower())
        after_candidates = _fetch_candidates(
            firebase_uid=firebase_uid,
            include_insight_legacy=args.include_insight_legacy,
        )
        if keep_book_ids:
            after_candidates = [r for r in after_candidates if (r.get("book_id") or "") not in keep_book_ids]

        print(f"[APPLY] Deleted rows: {deleted}")
        print(f"[VERIFY] Verify title '{args.verify_title}': {after_title_count} row(s) after")
        print(f"[VERIFY] Remaining candidate count: {len(after_candidates)}")
        return 0
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
