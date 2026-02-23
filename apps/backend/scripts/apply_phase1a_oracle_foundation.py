#!/usr/bin/env python3
"""
Phase 1A - Oracle schema foundation (additive, idempotent)

Creates new foundation tables and additive columns/indexes needed for the
canonical migration plan without changing existing read/write behavior.

Default mode is dry-run. Use --execute to apply changes.
"""

import argparse
import os
import sys
from typing import Callable, List, Tuple

import oracledb

# Add backend directory to sys.path
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


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = :t
          AND COLUMN_NAME = :c
        """,
        {"t": table_name.upper(), "c": column_name.upper()},
    )
    return cursor.fetchone() is not None


def _index_exists(cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :i",
        {"i": index_name.upper()},
    )
    return cursor.fetchone() is not None


def _execute_ddl(cursor, sql: str, description: str) -> None:
    print(f"[EXEC] {description}")
    cursor.execute(sql)


def _create_table_if_missing(cursor, table_name: str, ddl: str) -> None:
    if _table_exists(cursor, table_name):
        print(f"[SKIP] Table exists: {table_name}")
        return
    _execute_ddl(cursor, ddl, f"Create table {table_name}")


def _add_column_if_missing(cursor, table_name: str, column_name: str, col_ddl: str) -> None:
    if _column_exists(cursor, table_name, column_name):
        print(f"[SKIP] Column exists: {table_name}.{column_name}")
        return
    sql = f"ALTER TABLE {table_name} ADD ({col_ddl})"
    _execute_ddl(cursor, sql, f"Add column {table_name}.{column_name}")


def _create_index_if_missing(cursor, index_name: str, ddl: str) -> None:
    if _index_exists(cursor, index_name):
        print(f"[SKIP] Index exists: {index_name}")
        return
    _execute_ddl(cursor, ddl, f"Create index {index_name}")


def _phase1a_sql_blueprint() -> List[Tuple[str, str]]:
    ops: List[Tuple[str, str]] = []

    # New canonical master table
    ops.append((
        "table:TOMEHUB_LIBRARY_ITEMS",
        """
        CREATE TABLE TOMEHUB_LIBRARY_ITEMS (
            ITEM_ID VARCHAR2(255) PRIMARY KEY,
            FIREBASE_UID VARCHAR2(255) NOT NULL,
            ITEM_TYPE VARCHAR2(50) NOT NULL,
            TITLE VARCHAR2(1000),
            AUTHOR VARCHAR2(500),
            PUBLISHER VARCHAR2(500),
            TRANSLATOR VARCHAR2(500),
            PUBLICATION_YEAR NUMBER,
            ISBN VARCHAR2(64),
            SOURCE_URL VARCHAR2(2000),
            PAGE_COUNT NUMBER,
            COVER_URL VARCHAR2(2000),
            SUMMARY_TEXT CLOB,
            GENERAL_NOTES CLOB,
            TAGS_JSON CLOB,
            CATEGORY_JSON CLOB,
            INVENTORY_STATUS VARCHAR2(100),
            READING_STATUS VARCHAR2(100),
            PERSONAL_NOTE_CATEGORY VARCHAR2(100),
            STATUS VARCHAR2(50),
            SEARCH_VISIBILITY VARCHAR2(50) DEFAULT 'DEFAULT',
            IS_FAVORITE NUMBER(1) DEFAULT 0,
            ORIGIN_SYSTEM VARCHAR2(50),
            ORIGIN_COLLECTION VARCHAR2(100),
            ORIGIN_DOC_ID VARCHAR2(255),
            ORIGIN_SUBDOC_ID VARCHAR2(255),
            ORIGIN_UPDATED_AT TIMESTAMP,
            SYNC_RUN_ID VARCHAR2(100),
            IS_DELETED NUMBER(1) DEFAULT 0,
            DELETED_AT TIMESTAMP,
            DELETION_SOURCE VARCHAR2(100),
            ROW_VERSION NUMBER DEFAULT 1,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """.strip(),
    ))

    # Outbox / change events
    ops.append((
        "table:TOMEHUB_CHANGE_EVENTS",
        """
        CREATE TABLE TOMEHUB_CHANGE_EVENTS (
            EVENT_ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            FIREBASE_UID VARCHAR2(255),
            ITEM_ID VARCHAR2(255),
            ENTITY_TYPE VARCHAR2(50) NOT NULL,
            EVENT_TYPE VARCHAR2(100) NOT NULL,
            STATUS VARCHAR2(30) DEFAULT 'PENDING',
            PAYLOAD_JSON CLOB,
            RETRY_COUNT NUMBER DEFAULT 0,
            LAST_ERROR_CODE VARCHAR2(100),
            LAST_ERROR_MESSAGE VARCHAR2(1000),
            SOURCE_SERVICE VARCHAR2(100),
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PUBLISHED_AT TIMESTAMP
        )
        """.strip(),
    ))

    # Ingestion runs (batch/run-level tracing)
    ops.append((
        "table:TOMEHUB_INGESTION_RUNS",
        """
        CREATE TABLE TOMEHUB_INGESTION_RUNS (
            RUN_ID VARCHAR2(100) PRIMARY KEY,
            RUN_TYPE VARCHAR2(50) NOT NULL,
            STATUS VARCHAR2(30) NOT NULL,
            FIREBASE_UID VARCHAR2(255),
            STARTED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FINISHED_AT TIMESTAMP,
            TOTAL_ITEMS NUMBER DEFAULT 0,
            PROCESSED_ITEMS NUMBER DEFAULT 0,
            SUCCESS_COUNT NUMBER DEFAULT 0,
            FAILED_COUNT NUMBER DEFAULT 0,
            QUARANTINE_COUNT NUMBER DEFAULT 0,
            METADATA_JSON CLOB,
            ERROR_SUMMARY CLOB
        )
        """.strip(),
    ))

    # Ingestion events (item-level tracing)
    ops.append((
        "table:TOMEHUB_INGESTION_EVENTS",
        """
        CREATE TABLE TOMEHUB_INGESTION_EVENTS (
            EVENT_ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            RUN_ID VARCHAR2(100),
            FIREBASE_UID VARCHAR2(255),
            ITEM_ID VARCHAR2(255),
            ENTITY_TYPE VARCHAR2(50),
            EVENT_TYPE VARCHAR2(100) NOT NULL,
            STATUS VARCHAR2(30) NOT NULL,
            DETAILS_JSON CLOB,
            ERROR_CODE VARCHAR2(100),
            ERROR_MESSAGE VARCHAR2(1000),
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """.strip(),
    ))

    # Precomputed readiness summary
    ops.append((
        "table:TOMEHUB_ITEM_INDEX_STATE",
        """
        CREATE TABLE TOMEHUB_ITEM_INDEX_STATE (
            FIREBASE_UID VARCHAR2(255) NOT NULL,
            ITEM_ID VARCHAR2(255) NOT NULL,
            INDEX_FRESHNESS_STATE VARCHAR2(50),
            TOTAL_CHUNKS NUMBER DEFAULT 0,
            EMBEDDED_CHUNKS NUMBER DEFAULT 0,
            GRAPH_LINKED_CHUNKS NUMBER DEFAULT 0,
            VECTOR_READY NUMBER(1) DEFAULT 0,
            GRAPH_READY NUMBER(1) DEFAULT 0,
            FULLY_READY NUMBER(1) DEFAULT 0,
            VECTOR_COVERAGE_RATIO NUMBER(8,4),
            GRAPH_COVERAGE_RATIO NUMBER(8,4),
            LAST_CHECKED_AT TIMESTAMP,
            SOURCE_UPDATED_AT TIMESTAMP,
            UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT PK_TH_ITEM_INDEX_STATE PRIMARY KEY (FIREBASE_UID, ITEM_ID)
        )
        """.strip(),
    ))

    # Additive columns on TOMEHUB_CONTENT (Phase 1A foundation only)
    content_cols = [
        ("INGESTION_TYPE", "INGESTION_TYPE VARCHAR2(50)"),
        ("CONTENT_TYPE", "CONTENT_TYPE VARCHAR2(50)"),
        ("CONTENT_HASH", "CONTENT_HASH VARCHAR2(64)"),
        ("SEARCH_VISIBILITY", "SEARCH_VISIBILITY VARCHAR2(50)"),
        ("ORIGIN_SYSTEM", "ORIGIN_SYSTEM VARCHAR2(50)"),
        ("ORIGIN_COLLECTION", "ORIGIN_COLLECTION VARCHAR2(100)"),
        ("ORIGIN_DOC_ID", "ORIGIN_DOC_ID VARCHAR2(255)"),
        ("ORIGIN_SUBDOC_ID", "ORIGIN_SUBDOC_ID VARCHAR2(255)"),
        ("ORIGIN_UPDATED_AT", "ORIGIN_UPDATED_AT TIMESTAMP"),
        ("SYNC_RUN_ID", "SYNC_RUN_ID VARCHAR2(100)"),
        ("IS_DELETED", "IS_DELETED NUMBER(1) DEFAULT 0"),
        ("DELETED_AT", "DELETED_AT TIMESTAMP"),
        ("DELETION_SOURCE", "DELETION_SOURCE VARCHAR2(100)"),
        ("ROW_VERSION", "ROW_VERSION NUMBER DEFAULT 1"),
    ]
    for col_name, col_ddl in content_cols:
        ops.append((f"column:TOMEHUB_CONTENT.{col_name}", col_ddl))

    # Baseline indexes on new tables + additive content access paths
    index_ddls = [
        ("IDX_LIBITEM_UID_TYPE", "CREATE INDEX IDX_LIBITEM_UID_TYPE ON TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_TYPE)"),
        ("IDX_LIBITEM_UID_UPD", "CREATE INDEX IDX_LIBITEM_UID_UPD ON TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, UPDATED_AT)"),
        ("IDX_LIBITEM_UID_VIS", "CREATE INDEX IDX_LIBITEM_UID_VIS ON TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, SEARCH_VISIBILITY)"),
        ("IDX_CHGEVT_STATUS_TS", "CREATE INDEX IDX_CHGEVT_STATUS_TS ON TOMEHUB_CHANGE_EVENTS(STATUS, CREATED_AT)"),
        ("IDX_CHGEVT_UID_TS", "CREATE INDEX IDX_CHGEVT_UID_TS ON TOMEHUB_CHANGE_EVENTS(FIREBASE_UID, CREATED_AT)"),
        ("IDX_CHGEVT_ITEM_TS", "CREATE INDEX IDX_CHGEVT_ITEM_TS ON TOMEHUB_CHANGE_EVENTS(FIREBASE_UID, ITEM_ID, CREATED_AT)"),
        ("IDX_INGRUN_STATUS_TS", "CREATE INDEX IDX_INGRUN_STATUS_TS ON TOMEHUB_INGESTION_RUNS(STATUS, STARTED_AT)"),
        ("IDX_INGEVT_RUN_TS", "CREATE INDEX IDX_INGEVT_RUN_TS ON TOMEHUB_INGESTION_EVENTS(RUN_ID, CREATED_AT)"),
        ("IDX_INGEVT_ITEM_TS", "CREATE INDEX IDX_INGEVT_ITEM_TS ON TOMEHUB_INGESTION_EVENTS(FIREBASE_UID, ITEM_ID, CREATED_AT)"),
        ("IDX_IDXSTATE_UID_UPD", "CREATE INDEX IDX_IDXSTATE_UID_UPD ON TOMEHUB_ITEM_INDEX_STATE(FIREBASE_UID, UPDATED_AT)"),
        ("IDX_CONT_UID_BOOK_SRC", "CREATE INDEX IDX_CONT_UID_BOOK_SRC ON TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, SOURCE_TYPE)"),
        ("IDX_CONT_UID_BOOK_CRT", "CREATE INDEX IDX_CONT_UID_BOOK_CRT ON TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID, CREATED_AT)"),
    ]
    for idx_name, idx_sql in index_ddls:
        ops.append((f"index:{idx_name}", idx_sql))

    return ops


def print_dry_run() -> None:
    print("=== Phase 1A Oracle Foundation (DRY-RUN) ===")
    for key, sql in _phase1a_sql_blueprint():
        print(f"\n-- {key}")
        print(sql)
    print("\nDry-run complete. Re-run with --execute to apply.")


def apply_changes(skip_indexes: bool = False) -> int:
    print("=== Applying Phase 1A Oracle Foundation ===")
    DatabaseManager.init_pool()
    applied = 0

    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                ops = _phase1a_sql_blueprint()
                for key, sql in ops:
                    try:
                        if key.startswith("table:"):
                            table_name = key.split(":", 1)[1]
                            _create_table_if_missing(cursor, table_name, sql)
                            applied += 1
                            continue

                        if key.startswith("column:"):
                            table_col = key.split(":", 1)[1]
                            table_name, col_name = table_col.split(".", 1)
                            _add_column_if_missing(cursor, table_name, col_name, sql)
                            applied += 1
                            continue

                        if key.startswith("index:"):
                            if skip_indexes:
                                print(f"[SKIP] Index creation disabled: {key.split(':',1)[1]}")
                                continue
                            idx_name = key.split(":", 1)[1]
                            _create_index_if_missing(cursor, idx_name, sql)
                            applied += 1
                            continue

                        print(f"[WARN] Unknown op type: {key}")
                    except Exception as e:
                        code = _ora_code(e)
                        print(f"[ERROR] {key} failed (ORA={code}): {e}")
                        raise

                conn.commit()
        print("\n[OK] Phase 1A migration completed.")
        return applied
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Phase 1A Oracle foundation schema changes")
    parser.add_argument("--execute", action="store_true", help="Apply changes to Oracle (default is dry-run)")
    parser.add_argument("--skip-indexes", action="store_true", help="Skip baseline index creation")
    args = parser.parse_args()

    if not args.execute:
        print_dry_run()
        return 0

    apply_changes(skip_indexes=args.skip_indexes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

