"""
Phase 5 high-ROI index apply (idempotent).

Targets (from profiling baseline):
- TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CONTENT_TYPE)
- TOMEHUB_INGESTED_FILES(FIREBASE_UID, BOOK_ID)
"""

from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


INDEX_DEFS = [
    (
        "IDX_CONT_UID_BOOK_CTYPE",
        "TOMEHUB_CONTENT",
        "CREATE INDEX IDX_CONT_UID_BOOK_CTYPE ON TOMEHUB_CONTENT (FIREBASE_UID, BOOK_ID, CONTENT_TYPE)",
    ),
    (
        "IDX_INGEST_UID_BOOK",
        "TOMEHUB_INGESTED_FILES",
        "CREATE INDEX IDX_INGEST_UID_BOOK ON TOMEHUB_INGESTED_FILES (FIREBASE_UID, BOOK_ID)",
    ),
]


def _exists(cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :n",
        {"n": index_name.upper()},
    )
    return cursor.fetchone() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Phase 5 high-ROI indexes.")
    parser.add_argument("--execute", action="store_true", help="Apply indexes (default dry-run)")
    parser.add_argument("--ddl-lock-timeout", type=int, default=60, help="Seconds for Oracle DDL lock wait")
    parser.add_argument("--retries", type=int, default=3, help="Retries for transient DDL lock contention")
    args = parser.parse_args()

    DatabaseManager.init_pool()
    created = 0
    skipped = 0

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            if args.execute:
                try:
                    cursor.execute(f"ALTER SESSION SET DDL_LOCK_TIMEOUT = {int(args.ddl_lock_timeout)}")
                    print(f"[SET] DDL_LOCK_TIMEOUT={int(args.ddl_lock_timeout)}")
                except Exception as e:
                    print(f"[WARN] Could not set DDL_LOCK_TIMEOUT: {e}")
            for name, table, ddl in INDEX_DEFS:
                if _exists(cursor, name):
                    print(f"[SKIP] {name} already exists")
                    skipped += 1
                    continue
                if not args.execute:
                    print(f"[DRYRUN] {ddl}")
                    continue
                attempts = max(1, int(args.retries))
                for attempt in range(1, attempts + 1):
                    try:
                        print(f"[APPLY] {name} on {table} (attempt {attempt}/{attempts})")
                        cursor.execute(ddl)
                        created += 1
                        break
                    except Exception as e:
                        err = str(e)
                        if "ORA-00054" in err and attempt < attempts:
                            print(f"[RETRY] {name} lock contention: {e}")
                            time.sleep(min(5 * attempt, 15))
                            continue
                        raise
        if args.execute:
            conn.commit()

    mode = "EXECUTE" if args.execute else "DRYRUN"
    print(f"[{mode}] done created={created} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
