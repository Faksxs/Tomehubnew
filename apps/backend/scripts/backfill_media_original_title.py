"""
Backfill ORIGINAL_TITLE for MOVIE/SERIES library items using TMDb token stored in ISBN.

Scope:
- ITEM_TYPE IN ('MOVIE', 'SERIES')
- ORIGINAL_TITLE is NULL/blank
- ISBN matches tmdb:{movie|tv}:{id}
"""

from __future__ import annotations

import argparse
import re
import time
from typing import Optional, Tuple

from infrastructure.db_manager import DatabaseManager
from services.tmdb_service import get_tmdb_media_details
from utils.logger import get_logger

logger = get_logger("backfill_media_original_title")

_TMDB_TOKEN_RE = re.compile(r"^tmdb:(movie|tv):(\d+)$", re.IGNORECASE)


def _parse_tmdb_token(token: str) -> Optional[Tuple[str, int]]:
    raw = str(token or "").strip().lower()
    m = _TMDB_TOKEN_RE.match(raw)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill TOMEHUB_LIBRARY_ITEMS.ORIGINAL_TITLE from TMDb.")
    parser.add_argument("--uid", type=str, default=None, help="Optional FIREBASE_UID scope")
    parser.add_argument("--limit", type=int, default=5000, help="Max rows to process")
    parser.add_argument("--commit-every", type=int, default=50, help="Commit interval")
    parser.add_argument("--sleep-ms", type=int, default=50, help="Sleep between TMDb calls")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB write")
    args = parser.parse_args()

    max_rows = max(1, int(args.limit or 5000))
    commit_every = max(1, int(args.commit_every or 50))
    sleep_sec = max(0, int(args.sleep_ms or 0)) / 1000.0

    where = [
        "ITEM_TYPE IN ('MOVIE','SERIES')",
        "NVL(IS_DELETED,0) = 0",
        "(ORIGINAL_TITLE IS NULL OR TRIM(ORIGINAL_TITLE) IS NULL)",
        "REGEXP_LIKE(LOWER(TRIM(ISBN)), '^tmdb:(movie|tv):[0-9]+$')",
    ]
    binds = {"p_limit": max_rows}
    if args.uid:
        where.append("FIREBASE_UID = :p_uid")
        binds["p_uid"] = str(args.uid).strip()

    processed = 0
    updated = 0
    skipped = 0
    failed = 0
    pending_since_commit = 0

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, ISBN
                FROM TOMEHUB_LIBRARY_ITEMS
                WHERE {' AND '.join(where)}
                ORDER BY UPDATED_AT DESC NULLS LAST
                FETCH FIRST :p_limit ROWS ONLY
                """,
                binds,
            )
            rows = cur.fetchall() or []

            logger.info(f"candidate_rows={len(rows)}")

            for row in rows:
                processed += 1
                item_id = str(row[0] or "").strip()
                firebase_uid = str(row[1] or "").strip()
                title = str(row[3] or "").strip()
                token = str(row[4] or "").strip()

                parsed = _parse_tmdb_token(token)
                if not parsed:
                    skipped += 1
                    continue
                kind, tmdb_id = parsed

                try:
                    details = get_tmdb_media_details(kind, tmdb_id) or {}
                    original_title = str(details.get("originalTitle") or "").strip()
                    if not original_title:
                        skipped += 1
                        continue

                    if args.dry_run:
                        logger.info(
                            f"[DRY] item_id={item_id} uid={firebase_uid} title={title!r} original_title={original_title!r}"
                        )
                        updated += 1
                        continue

                    cur.execute(
                        """
                        UPDATE TOMEHUB_LIBRARY_ITEMS
                        SET ORIGINAL_TITLE = :p_original_title,
                            UPDATED_AT = CURRENT_TIMESTAMP
                        WHERE ITEM_ID = :p_item_id
                          AND FIREBASE_UID = :p_uid
                          AND (ORIGINAL_TITLE IS NULL OR TRIM(ORIGINAL_TITLE) IS NULL)
                        """,
                        {
                            "p_original_title": original_title,
                            "p_item_id": item_id,
                            "p_uid": firebase_uid,
                        },
                    )
                    if (cur.rowcount or 0) > 0:
                        updated += int(cur.rowcount or 0)
                        pending_since_commit += 1
                        if pending_since_commit >= commit_every:
                            conn.commit()
                            pending_since_commit = 0
                    else:
                        skipped += 1
                except Exception as e:
                    failed += 1
                    logger.warning(f"backfill_failed item_id={item_id} token={token} error={e}")

                if sleep_sec > 0:
                    time.sleep(sleep_sec)

            if not args.dry_run and pending_since_commit > 0:
                conn.commit()

    logger.info(
        f"done processed={processed} updated={updated} skipped={skipped} failed={failed} dry_run={args.dry_run}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
