#!/usr/bin/env python3
"""
Phase 1 checklist verifier (1A + 1B + 1C + 1D)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


REQ_TABLES = [
    "TOMEHUB_LIBRARY_ITEMS",
    "TOMEHUB_CHANGE_EVENTS",
    "TOMEHUB_INGESTION_RUNS",
    "TOMEHUB_INGESTION_EVENTS",
    "TOMEHUB_ITEM_INDEX_STATE",
]

REQ_CONTENT_COLS = [
    "INGESTION_TYPE",
    "CONTENT_TYPE",
    "CONTENT_HASH",
    "SEARCH_VISIBILITY",
    "ORIGIN_SYSTEM",
    "ORIGIN_COLLECTION",
    "ORIGIN_DOC_ID",
    "ORIGIN_SUBDOC_ID",
    "ORIGIN_UPDATED_AT",
    "SYNC_RUN_ID",
    "IS_DELETED",
    "DELETED_AT",
    "DELETION_SOURCE",
    "ROW_VERSION",
]

REQ_INDEXES = [
    "IDX_LIBITEM_UID_TYPE",
    "IDX_LIBITEM_UID_UPD",
    "IDX_LIBITEM_UID_VIS",
    "IDX_CHGEVT_STATUS_TS",
    "IDX_CHGEVT_UID_TS",
    "IDX_CHGEVT_ITEM_TS",
    "IDX_INGRUN_STATUS_TS",
    "IDX_INGEVT_RUN_TS",
    "IDX_INGEVT_ITEM_TS",
    "IDX_IDXSTATE_UID_UPD",
    "IDX_CONT_UID_BOOK_SRC",
    "IDX_CONT_UID_BOOK_CRT",
]

REQ_VIEWS = [
    "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED",
    "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM",
    "VW_TOMEHUB_BOOKS_COMPAT",
]


def _ok(label: str, value=None):
    if value is None:
        print(f"[OK] {label}")
    else:
        print(f"[OK] {label}: {value}")


def _fail(label: str, value=None):
    if value is None:
        print(f"[FAIL] {label}")
    else:
        print(f"[FAIL] {label}: {value}")


def _query_set(cursor, sql: str, key: str) -> set[str]:
    cursor.execute(sql)
    return {str(r[0]).upper() for r in cursor.fetchall() if r and r[0] is not None}


def check_db() -> int:
    failures = 0
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                tables = _query_set(cursor, "SELECT TABLE_NAME FROM USER_TABLES", "TABLE_NAME")
                for t in REQ_TABLES:
                    if t in tables:
                        _ok(f"Table exists `{t}`")
                    else:
                        _fail(f"Table exists `{t}`")
                        failures += 1

                cursor.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM USER_TAB_COLUMNS
                    WHERE TABLE_NAME = 'TOMEHUB_CONTENT'
                    """
                )
                cols = {str(r[0]).upper() for r in cursor.fetchall()}
                for c in REQ_CONTENT_COLS:
                    if c in cols:
                        _ok(f"Column exists `TOMEHUB_CONTENT.{c}`")
                    else:
                        _fail(f"Column exists `TOMEHUB_CONTENT.{c}`")
                        failures += 1

                idxs = _query_set(cursor, "SELECT INDEX_NAME FROM USER_INDEXES", "INDEX_NAME")
                for i in REQ_INDEXES:
                    if i in idxs:
                        _ok(f"Index exists `{i}`")
                    else:
                        _fail(f"Index exists `{i}`")
                        failures += 1

                views = _query_set(cursor, "SELECT VIEW_NAME FROM USER_VIEWS", "VIEW_NAME")
                for v in REQ_VIEWS:
                    if v in views:
                        _ok(f"View exists `{v}`")
                    else:
                        _fail(f"View exists `{v}`")
                        failures += 1

                smoke_queries = [
                    ("`VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED` count", "SELECT COUNT(*) FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED"),
                    ("`VW_TOMEHUB_INGESTION_STATUS_BY_ITEM` count", "SELECT COUNT(*) FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM"),
                    ("`VW_TOMEHUB_BOOKS_COMPAT` count", "SELECT COUNT(*) FROM VW_TOMEHUB_BOOKS_COMPAT"),
                ]
                for label, sql in smoke_queries:
                    try:
                        cursor.execute(sql)
                        row = cursor.fetchone()
                        _ok(label, row[0] if row else None)
                    except Exception as e:
                        _fail(label, str(e))
                        failures += 1
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass
    return failures


def check_phase1c_report() -> int:
    failures = 0
    p = REPO_ROOT / "documentation" / "reports" / "PHASE1C_TOMEHUB_BOOKS_DML_AUDIT_2026-02-22.md"
    if not p.exists():
        _fail("Phase 1C audit report exists", str(p))
        return 1
    _ok("Phase 1C audit report exists", p.as_posix())
    text = p.read_text(encoding="utf-8", errors="ignore")
    m_total = re.search(r"Total DML callsites:\s*`(\d+)`", text)
    m_runtime = re.search(r"Runtime callsites:\s*`(\d+)`", text)
    if not m_total:
        _fail("Phase 1C audit total parsed")
        failures += 1
    else:
        _ok("Phase 1C audit total parsed", int(m_total.group(1)))
    if not m_runtime:
        _fail("Phase 1C audit runtime count parsed")
        failures += 1
    else:
        _ok("Phase 1C audit runtime count parsed", int(m_runtime.group(1)))
    return failures


def check_phase1d_code() -> int:
    failures = 0
    p = REPO_ROOT / "apps" / "backend" / "services" / "search_system" / "strategies.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    if ":p_exact_like" in txt and "ESCAPE '\\\\'" in txt:
        _ok("Phase 1D bind-safe exact LIKE present")
    else:
        _fail("Phase 1D bind-safe exact LIKE present")
        failures += 1
    if "LIKE '%{safe_term}%'" in txt:
        _fail("Phase 1D legacy exact interpolation removed")
        failures += 1
    else:
        _ok("Phase 1D legacy exact interpolation removed")
    return failures


def check_phase1c_runtime_prep() -> int:
    failures = 0
    p = REPO_ROOT / "apps" / "backend" / "services" / "ingestion_service.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    if "def _mirror_book_registry_rows(" in txt:
        _ok("Phase 1C helper `_mirror_book_registry_rows` exists")
    else:
        _fail("Phase 1C helper `_mirror_book_registry_rows` exists")
        failures += 1
    if "TOMEHUB_LIBRARY_ITEMS" in txt and "Mirrored book" in txt:
        _ok("Phase 1C runtime additive mirror logic present")
    else:
        _fail("Phase 1C runtime additive mirror logic present")
        failures += 1
    return failures


def main() -> int:
    print("=== Phase 1 Checklist (1A + 1B + 1C + 1D) ===")
    failures = 0
    failures += check_db()
    failures += check_phase1c_report()
    failures += check_phase1c_runtime_prep()
    failures += check_phase1d_code()
    if failures:
        print(f"\n[FAIL] Phase 1 checklist completed with {failures} issue(s).")
        return 2
    print("\n[OK] Phase 1 checklist passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
