#!/usr/bin/env python3
"""
Phase 1B - Compatibility views (read-only)

Creates compatibility/read-model views after Phase 1A tables exist.
Default mode is dry-run. Use --execute to create/update views.
Optional --smoke runs read-only verification queries.
"""

import argparse
import os
import sys
from typing import Iterable

import oracledb

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager  # noqa: E402


def _ora_code(exc: Exception) -> int | None:
    try:
        if isinstance(exc, oracledb.DatabaseError) and exc.args:
            err = exc.args[0]
            return int(getattr(err, "code", 0)) or None
    except Exception:
        return None
    return None


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :t",
        {"t": table_name.upper()},
    )
    return cursor.fetchone() is not None


def _view_exists(cursor, view_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM USER_VIEWS WHERE VIEW_NAME = :v",
        {"v": view_name.upper()},
    )
    return cursor.fetchone() is not None


def _required_tables() -> Iterable[str]:
    return [
        "TOMEHUB_LIBRARY_ITEMS",
        "TOMEHUB_INGESTED_FILES",
        "TOMEHUB_ITEM_INDEX_STATE",
    ]


def _view_sql_library_items_enriched() -> str:
    return """
CREATE OR REPLACE VIEW VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED AS
WITH latest_ingestion AS (
    SELECT
        f.BOOK_ID,
        f.FIREBASE_UID,
        f.STATUS AS INGESTION_STATUS,
        f.SOURCE_FILE_NAME,
        f.CHUNK_COUNT,
        f.EMBEDDING_COUNT,
        f.UPDATED_AT AS INGESTION_UPDATED_AT,
        ROW_NUMBER() OVER (
            PARTITION BY f.FIREBASE_UID, f.BOOK_ID
            ORDER BY f.UPDATED_AT DESC NULLS LAST, f.ID DESC NULLS LAST
        ) AS RN
    FROM TOMEHUB_INGESTED_FILES f
)
SELECT
    li.ITEM_ID,
    li.FIREBASE_UID,
    li.ITEM_TYPE,
    li.TITLE,
    li.AUTHOR,
    li.PUBLISHER,
    li.TRANSLATOR,
    li.PUBLICATION_YEAR,
    li.ISBN,
    li.SOURCE_URL,
    li.PAGE_COUNT,
    li.COVER_URL,
    li.SUMMARY_TEXT,
    li.TAGS_JSON,
    li.CATEGORY_JSON,
    li.INVENTORY_STATUS,
    li.READING_STATUS,
    li.PERSONAL_NOTE_CATEGORY,
    li.SEARCH_VISIBILITY,
    li.IS_FAVORITE,
    li.ORIGIN_SYSTEM,
    li.ORIGIN_COLLECTION,
    li.ORIGIN_DOC_ID,
    li.ORIGIN_SUBDOC_ID,
    li.ORIGIN_UPDATED_AT,
    li.SYNC_RUN_ID,
    li.IS_DELETED,
    li.DELETED_AT,
    li.DELETION_SOURCE,
    li.ROW_VERSION,
    li.CREATED_AT,
    li.UPDATED_AT,
    i.INGESTION_STATUS,
    i.SOURCE_FILE_NAME AS INGESTION_SOURCE_FILE_NAME,
    i.CHUNK_COUNT AS INGESTION_CHUNK_COUNT,
    i.EMBEDDING_COUNT AS INGESTION_EMBEDDING_COUNT,
    i.INGESTION_UPDATED_AT,
    s.INDEX_FRESHNESS_STATE,
    s.TOTAL_CHUNKS,
    s.EMBEDDED_CHUNKS,
    s.GRAPH_LINKED_CHUNKS,
    s.VECTOR_READY,
    s.GRAPH_READY,
    s.FULLY_READY,
    s.VECTOR_COVERAGE_RATIO,
    s.GRAPH_COVERAGE_RATIO,
    s.LAST_CHECKED_AT AS INDEX_LAST_CHECKED_AT,
    s.SOURCE_UPDATED_AT AS INDEX_SOURCE_UPDATED_AT,
    s.UPDATED_AT AS INDEX_STATE_UPDATED_AT
FROM TOMEHUB_LIBRARY_ITEMS li
LEFT JOIN latest_ingestion i
    ON i.FIREBASE_UID = li.FIREBASE_UID
   AND i.BOOK_ID = li.ITEM_ID
   AND i.RN = 1
LEFT JOIN TOMEHUB_ITEM_INDEX_STATE s
    ON s.FIREBASE_UID = li.FIREBASE_UID
   AND s.ITEM_ID = li.ITEM_ID
"""


def _view_sql_ingestion_status_by_item() -> str:
    return """
CREATE OR REPLACE VIEW VW_TOMEHUB_INGESTION_STATUS_BY_ITEM AS
WITH latest_ingestion AS (
    SELECT
        f.BOOK_ID AS ITEM_ID,
        f.FIREBASE_UID,
        f.STATUS,
        f.SOURCE_FILE_NAME,
        f.CHUNK_COUNT,
        f.EMBEDDING_COUNT,
        f.CREATED_AT,
        f.UPDATED_AT,
        ROW_NUMBER() OVER (
            PARTITION BY f.FIREBASE_UID, f.BOOK_ID
            ORDER BY f.UPDATED_AT DESC NULLS LAST, f.ID DESC NULLS LAST
        ) AS RN
    FROM TOMEHUB_INGESTED_FILES f
)
SELECT
    i.ITEM_ID,
    i.FIREBASE_UID,
    i.STATUS AS INGESTION_STATUS,
    i.SOURCE_FILE_NAME,
    i.CHUNK_COUNT,
    i.EMBEDDING_COUNT,
    i.CREATED_AT AS INGESTION_CREATED_AT,
    i.UPDATED_AT AS INGESTION_UPDATED_AT,
    s.INDEX_FRESHNESS_STATE,
    s.TOTAL_CHUNKS,
    s.EMBEDDED_CHUNKS,
    s.GRAPH_LINKED_CHUNKS,
    s.VECTOR_READY,
    s.GRAPH_READY,
    s.FULLY_READY,
    s.VECTOR_COVERAGE_RATIO,
    s.GRAPH_COVERAGE_RATIO,
    s.LAST_CHECKED_AT,
    s.SOURCE_UPDATED_AT AS INDEX_SOURCE_UPDATED_AT,
    s.UPDATED_AT AS INDEX_STATE_UPDATED_AT
FROM latest_ingestion i
LEFT JOIN TOMEHUB_ITEM_INDEX_STATE s
    ON s.FIREBASE_UID = i.FIREBASE_UID
   AND s.ITEM_ID = i.ITEM_ID
WHERE i.RN = 1
"""


def _view_sql_library_items_legacy_books_compat() -> str:
    # Read-only compatibility projection shaped like a richer BOOKS read model.
    return """
CREATE OR REPLACE VIEW VW_TOMEHUB_BOOKS_COMPAT AS
SELECT
    ITEM_ID AS ID,
    TITLE,
    AUTHOR,
    FIREBASE_UID,
    CREATED_AT,
    UPDATED_AT AS LAST_UPDATED,
    ITEM_TYPE,
    INVENTORY_STATUS,
    READING_STATUS,
    SEARCH_VISIBILITY,
    IS_DELETED
FROM TOMEHUB_LIBRARY_ITEMS
"""


def print_dry_run() -> None:
    print("=== Phase 1B Compatibility Views (DRY-RUN) ===")
    print("\n-- VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED")
    print(_view_sql_library_items_enriched())
    print("\n-- VW_TOMEHUB_INGESTION_STATUS_BY_ITEM")
    print(_view_sql_ingestion_status_by_item())
    print("\n-- VW_TOMEHUB_BOOKS_COMPAT")
    print(_view_sql_library_items_legacy_books_compat())
    print("\nDry-run complete. Use --execute to apply views.")


def _preflight_or_raise(cursor) -> None:
    missing = [t for t in _required_tables() if not _table_exists(cursor, t)]
    if missing:
        raise RuntimeError(
            "Phase 1B preflight failed. Missing required tables (run Phase 1A first): "
            + ", ".join(missing)
        )


def apply_views() -> None:
    print("=== Applying Phase 1B Compatibility Views ===")
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                _preflight_or_raise(cursor)

                view_defs = [
                    ("VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED", _view_sql_library_items_enriched()),
                    ("VW_TOMEHUB_INGESTION_STATUS_BY_ITEM", _view_sql_ingestion_status_by_item()),
                    ("VW_TOMEHUB_BOOKS_COMPAT", _view_sql_library_items_legacy_books_compat()),
                ]
                for view_name, sql in view_defs:
                    exists = _view_exists(cursor, view_name)
                    print(f"[EXEC] {'Replace' if exists else 'Create'} view {view_name}")
                    cursor.execute(sql)

                conn.commit()
        print("[OK] Phase 1B views applied.")
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def run_smoke() -> int:
    print("=== Phase 1B Compatibility Views Smoke Check ===")
    DatabaseManager.init_pool()
    failures = 0
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                smoke_queries = [
                    (
                        "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED exists/count",
                        "SELECT COUNT(*) FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED",
                    ),
                    (
                        "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM exists/count",
                        "SELECT COUNT(*) FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM",
                    ),
                    (
                        "VW_TOMEHUB_BOOKS_COMPAT exists/count",
                        "SELECT COUNT(*) FROM VW_TOMEHUB_BOOKS_COMPAT",
                    ),
                    (
                        "Books compat sample columns",
                        "SELECT ID, TITLE, FIREBASE_UID FROM VW_TOMEHUB_BOOKS_COMPAT FETCH FIRST 1 ROWS ONLY",
                    ),
                    (
                        "Enriched view sample columns",
                        """
                        SELECT ITEM_ID, FIREBASE_UID, INGESTION_STATUS, INDEX_FRESHNESS_STATE
                        FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED
                        FETCH FIRST 1 ROWS ONLY
                        """,
                    ),
                ]
                for label, sql in smoke_queries:
                    try:
                        cursor.execute(sql)
                        row = cursor.fetchone()
                        print(f"[OK] {label}: {row}")
                    except Exception as e:
                        failures += 1
                        print(f"[FAIL] {label}: {e}")
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    if failures:
        print(f"[WARN] Smoke check completed with {failures} failure(s).")
    else:
        print("[OK] Smoke check passed.")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Phase 1B compatibility views")
    parser.add_argument("--execute", action="store_true", help="Create/replace views in Oracle")
    parser.add_argument("--smoke", action="store_true", help="Run read-only smoke checks after applying (or against existing views)")
    args = parser.parse_args()

    if not args.execute:
        print_dry_run()
    else:
        apply_views()

    if args.smoke:
        failures = run_smoke()
        if failures:
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
