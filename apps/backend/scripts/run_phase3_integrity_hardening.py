#!/usr/bin/env python3
"""
Phase 3 integrity hardening runner

Scope (safe by default):
- Orphan checks against canonical `TOMEHUB_LIBRARY_ITEMS`
- Legacy/canonical parity checks for ancillary tables
- Composite uniqueness prep for future composite FK validation
- Markdown report generation

Default mode is dry-run / audit only.
Use `--execute` to apply safe hardening actions:
- create unique constraint on (FIREBASE_UID, ITEM_ID) for TOMEHUB_LIBRARY_ITEMS (if missing)
- optionally delete canonical orphans from low-risk ancillary tables (`--cleanup-orphans`)

Intentionally out of scope for this runner:
- Enabling FK constraints on write-path tables (can break current runtime before all writers migrate)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE3_INTEGRITY_HARDENING_REPORT_2026-02-22.md"


def _ok(label: str, value=None):
    if value is None:
        print(f"[OK] {label}")
    else:
        print(f"[OK] {label}: {value}")


def _warn(label: str, value=None):
    if value is None:
        print(f"[WARN] {label}")
    else:
        print(f"[WARN] {label}: {value}")


def _fail(label: str, value=None):
    if value is None:
        print(f"[FAIL] {label}")
    else:
        print(f"[FAIL] {label}: {value}")


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _obj_exists(cursor, obj_type: str, name: str) -> bool:
    if obj_type.upper() == "TABLE":
        cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :n", {"n": name.upper()})
    elif obj_type.upper() == "CONSTRAINT":
        cursor.execute("SELECT 1 FROM USER_CONSTRAINTS WHERE CONSTRAINT_NAME = :n", {"n": name.upper()})
    elif obj_type.upper() == "INDEX":
        cursor.execute("SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :n", {"n": name.upper()})
    else:
        raise ValueError(f"Unsupported obj_type={obj_type}")
    return cursor.fetchone() is not None


@dataclass
class CheckResult:
    name: str
    status: str  # ok|warn|fail
    value: str


def _preflight(cursor) -> list[CheckResult]:
    results: list[CheckResult] = []
    required = [
        "TOMEHUB_LIBRARY_ITEMS",
        "TOMEHUB_CONTENT",
        "TOMEHUB_INGESTED_FILES",
        "TOMEHUB_FILE_REPORTS",
        "TOMEHUB_ITEM_INDEX_STATE",
    ]
    for t in required:
        exists = _obj_exists(cursor, "TABLE", t)
        results.append(CheckResult(f"table_exists:{t}", "ok" if exists else "fail", str(exists)))
    return results


def _integrity_checks(cursor) -> list[CheckResult]:
    results: list[CheckResult] = []

    # Canonical orphan checks (composite key)
    checks = [
        (
            "content_orphans_vs_library_items",
            """
            SELECT COUNT(*)
            FROM TOMEHUB_CONTENT c
            WHERE c.BOOK_ID IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM TOMEHUB_LIBRARY_ITEMS li
                  WHERE li.FIREBASE_UID = c.FIREBASE_UID
                    AND li.ITEM_ID = c.BOOK_ID
              )
            """,
        ),
        (
            "ingested_files_orphans_vs_library_items",
            """
            SELECT COUNT(*)
            FROM TOMEHUB_INGESTED_FILES f
            WHERE f.BOOK_ID IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM TOMEHUB_LIBRARY_ITEMS li
                  WHERE li.FIREBASE_UID = f.FIREBASE_UID
                    AND li.ITEM_ID = f.BOOK_ID
              )
            """,
        ),
        (
            "file_reports_orphans_vs_library_items",
            """
            SELECT COUNT(*)
            FROM TOMEHUB_FILE_REPORTS r
            WHERE r.BOOK_ID IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM TOMEHUB_LIBRARY_ITEMS li
                  WHERE li.FIREBASE_UID = r.FIREBASE_UID
                    AND li.ITEM_ID = r.BOOK_ID
              )
            """,
        ),
        (
            "item_index_state_orphans_vs_library_items",
            """
            SELECT COUNT(*)
            FROM TOMEHUB_ITEM_INDEX_STATE s
            WHERE NOT EXISTS (
                SELECT 1
                FROM TOMEHUB_LIBRARY_ITEMS li
                WHERE li.FIREBASE_UID = s.FIREBASE_UID
                  AND li.ITEM_ID = s.ITEM_ID
            )
            """,
        ),
    ]
    for name, sql in checks:
        cnt = _count(cursor, sql)
        status = "ok" if cnt == 0 else "warn"
        results.append(CheckResult(name, status, str(cnt)))

    # Future FK prep: exact referenced key needed for composite FK.
    dups = _count(
        cursor,
        """
        SELECT COUNT(*)
        FROM (
          SELECT FIREBASE_UID, ITEM_ID, COUNT(*) c
          FROM TOMEHUB_LIBRARY_ITEMS
          GROUP BY FIREBASE_UID, ITEM_ID
          HAVING COUNT(*) > 1
        )
        """,
    )
    results.append(CheckResult("library_items_duplicate_uid_item", "ok" if dups == 0 else "fail", str(dups)))

    # Cross-tenant collision risk on ITEM_ID (important because current PK is ITEM_ID only)
    collisions = _count(
        cursor,
        """
        SELECT COUNT(*)
        FROM (
          SELECT ITEM_ID
          FROM TOMEHUB_LIBRARY_ITEMS
          GROUP BY ITEM_ID
          HAVING COUNT(DISTINCT FIREBASE_UID) > 1
        )
        """
    )
    # Current PK prevents collisions, but keep explicit signal.
    results.append(CheckResult("library_items_item_id_cross_uid_collision", "ok" if collisions == 0 else "fail", str(collisions)))

    # Personal note visibility consistency (library + content)
    li_bad_vis = _count(
        cursor,
        """
        SELECT COUNT(*)
        FROM TOMEHUB_LIBRARY_ITEMS
        WHERE ITEM_TYPE = 'PERSONAL_NOTE'
          AND NVL(SEARCH_VISIBILITY, 'DEFAULT') <> 'EXCLUDED_BY_DEFAULT'
        """,
    )
    c_bad_vis = _count(
        cursor,
        """
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE SOURCE_TYPE = 'PERSONAL_NOTE'
          AND NVL(SEARCH_VISIBILITY, 'DEFAULT') <> 'EXCLUDED_BY_DEFAULT'
        """,
    )
    results.append(CheckResult("library_items_personal_note_visibility", "ok" if li_bad_vis == 0 else "warn", str(li_bad_vis)))
    results.append(CheckResult("content_personal_note_visibility", "ok" if c_bad_vis == 0 else "warn", str(c_bad_vis)))

    # Legacy mirror parity signal (not strict; helps detect drift before write-path migration completes)
    legacy_mirror_missing = _count(
        cursor,
        """
        SELECT COUNT(*)
        FROM TOMEHUB_BOOKS b
        WHERE NOT EXISTS (
          SELECT 1
          FROM TOMEHUB_LIBRARY_ITEMS li
          WHERE li.FIREBASE_UID = b.FIREBASE_UID
            AND li.ITEM_ID = b.ID
        )
        """
    )
    results.append(CheckResult("legacy_books_missing_in_library_items", "ok" if legacy_mirror_missing == 0 else "warn", str(legacy_mirror_missing)))

    return results


def _constraint_status(cursor, name: str) -> str:
    cursor.execute(
        """
        SELECT STATUS || '/' || VALIDATED
        FROM USER_CONSTRAINTS
        WHERE CONSTRAINT_NAME = :n
        """,
        {"n": name.upper()},
    )
    row = cursor.fetchone()
    return str(row[0]) if row else "MISSING"


def _apply_safe_actions(cursor, cleanup_orphans: bool) -> list[CheckResult]:
    results: list[CheckResult] = []

    uq_name = "UQ_LIBITEM_UID_ITEM"
    if _obj_exists(cursor, "CONSTRAINT", uq_name):
        results.append(CheckResult("create_composite_unique_uq_libitem_uid_item", "ok", "already_exists"))
    else:
        cursor.execute(
            """
            ALTER TABLE TOMEHUB_LIBRARY_ITEMS
            ADD CONSTRAINT UQ_LIBITEM_UID_ITEM UNIQUE (FIREBASE_UID, ITEM_ID)
            """
        )
        results.append(CheckResult("create_composite_unique_uq_libitem_uid_item", "ok", _constraint_status(cursor, uq_name)))

    if cleanup_orphans:
        # Only low-risk tables: ancillary generated/derived tables.
        cleanup_statements = [
            (
                "delete_file_reports_orphans_vs_library_items",
                """
                DELETE FROM TOMEHUB_FILE_REPORTS r
                WHERE r.BOOK_ID IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM TOMEHUB_LIBRARY_ITEMS li
                      WHERE li.FIREBASE_UID = r.FIREBASE_UID
                        AND li.ITEM_ID = r.BOOK_ID
                  )
                """,
            ),
            (
                "delete_ingested_files_orphans_vs_library_items",
                """
                DELETE FROM TOMEHUB_INGESTED_FILES f
                WHERE f.BOOK_ID IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM TOMEHUB_LIBRARY_ITEMS li
                      WHERE li.FIREBASE_UID = f.FIREBASE_UID
                        AND li.ITEM_ID = f.BOOK_ID
                  )
                """,
            ),
        ]
        for name, sql in cleanup_statements:
            cursor.execute(sql)
            results.append(CheckResult(name, "ok", str(int(getattr(cursor, "rowcount", 0) or 0))))
    else:
        results.append(CheckResult("cleanup_orphans", "ok", "skipped"))

    return results


def _fk_prep_notes(cursor) -> list[CheckResult]:
    results: list[CheckResult] = []
    # Report-only: do not enforce yet
    candidate_fks = [
        (
            "FK_CNT_UID_BID_LI",
            "TOMEHUB_CONTENT(FIREBASE_UID, BOOK_ID) -> TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)",
        ),
        (
            "FK_IF_UID_BID_LI",
            "TOMEHUB_INGESTED_FILES(FIREBASE_UID, BOOK_ID) -> TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)",
        ),
        (
            "FK_FR_UID_BID_LI",
            "TOMEHUB_FILE_REPORTS(FIREBASE_UID, BOOK_ID) -> TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)",
        ),
        (
            "FK_IS_UID_IID_LI",
            "TOMEHUB_ITEM_INDEX_STATE(FIREBASE_UID, ITEM_ID) -> TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)",
        ),
    ]
    uq_status = _constraint_status(cursor, "UQ_LIBITEM_UID_ITEM")
    for fk_name, desc in candidate_fks:
        fk_status = _constraint_status(cursor, fk_name)
        if fk_status == "MISSING":
            results.append(CheckResult(f"fk_prep:{fk_name}", "warn", f"MISSING | candidate={desc} | requires phased enablement; ref_key={uq_status}"))
        else:
            results.append(CheckResult(f"fk_prep:{fk_name}", "ok", fk_status))
    return results


def _write_report(results: list[CheckResult], execute: bool, cleanup_orphans: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    ok_count = sum(1 for r in results if r.status == "ok")
    warn_count = sum(1 for r in results if r.status == "warn")
    fail_count = sum(1 for r in results if r.status == "fail")

    lines = [
        "# Phase 3 Integrity Hardening Report",
        "",
        f"- **Generated (UTC):** {ts}",
        f"- **Mode:** {'EXECUTE' if execute else 'DRY-RUN'}",
        f"- **Cleanup orphans:** {cleanup_orphans}",
        "",
        "## Summary",
        "",
        f"- OK: `{ok_count}`",
        f"- WARN: `{warn_count}`",
        f"- FAIL: `{fail_count}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Value |",
        "|---|---|---|",
    ]
    for r in results:
        lines.append(f"| `{r.name}` | `{r.status.upper()}` | `{r.value}` |")

    lines += [
        "",
        "## Notes",
        "",
        "- FK constraints are intentionally report-only in this phase runner unless write paths are fully migrated.",
        "- Composite unique key `UQ_LIBITEM_UID_ITEM` is added as safe preparation for future composite FKs.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(execute: bool, cleanup_orphans: bool) -> int:
    print(f"=== Phase 3 Integrity Hardening ({'EXECUTE' if execute else 'DRY-RUN'}) ===")
    all_results: list[CheckResult] = []
    failures = 0

    DatabaseManager.init_pool()
    try:
        with (DatabaseManager.get_write_connection() if execute else DatabaseManager.get_read_connection()) as conn:
            with conn.cursor() as cursor:
                pre = _preflight(cursor)
                all_results.extend(pre)
                if any(r.status == "fail" for r in pre):
                    for r in pre:
                        (_ok if r.status == "ok" else _fail)(r.name, r.value)
                    _write_report(all_results, execute=execute, cleanup_orphans=cleanup_orphans)
                    return 2

                integrity = _integrity_checks(cursor)
                all_results.extend(integrity)

                if execute:
                    applied = _apply_safe_actions(cursor, cleanup_orphans=cleanup_orphans)
                    all_results.extend(applied)
                    conn.commit()
                    # Re-run integrity checks after actions
                    post = _integrity_checks(cursor)
                    post = [CheckResult("post:" + r.name, r.status, r.value) for r in post]
                    all_results.extend(post)

                fk_notes = _fk_prep_notes(cursor)
                all_results.extend(fk_notes)

                for r in all_results:
                    if r.status == "ok":
                        _ok(r.name, r.value)
                    elif r.status == "warn":
                        _warn(r.name, r.value)
                    else:
                        _fail(r.name, r.value)
                        failures += 1

                _write_report(all_results, execute=execute, cleanup_orphans=cleanup_orphans)
                print(f"[INFO] Report written: {REPORT_PATH.as_posix()}")
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    if failures:
        print(f"\n[FAIL] Phase 3 integrity hardening completed with {failures} failure(s).")
        return 2
    print("\n[OK] Phase 3 integrity hardening completed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 integrity hardening runner")
    parser.add_argument("--execute", action="store_true", help="Apply safe hardening actions (default dry-run)")
    parser.add_argument("--cleanup-orphans", action="store_true", help="Delete canonical orphans in ancillary tables (only with --execute)")
    args = parser.parse_args()

    if args.cleanup_orphans and not args.execute:
        print("[WARN] --cleanup-orphans ignored without --execute")
    return run(execute=bool(args.execute), cleanup_orphans=bool(args.execute and args.cleanup_orphans))


if __name__ == "__main__":
    raise SystemExit(main())
