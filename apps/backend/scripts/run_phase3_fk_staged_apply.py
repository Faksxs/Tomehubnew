#!/usr/bin/env python3
"""
Phase 3 staged FK apply to canonical `TOMEHUB_LIBRARY_ITEMS`.

Strategy:
- Add composite FK candidates to canonical key (FIREBASE_UID, ITEM_ID)
- Enable `NOVALIDATE` only for low-risk tables by default
- Keep runtime-sensitive FKs disabled unless explicitly requested

Default `--execute` behavior:
- ITEM_INDEX_STATE FK => ENABLE NOVALIDATE
- FILE_REPORTS FK => ENABLE NOVALIDATE
- CONTENT FK => DISABLE NOVALIDATE (runtime-sensitive)
- INGESTED_FILES FK => DISABLE NOVALIDATE (runtime-sensitive)
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


REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE3_FK_STAGED_APPLY_REPORT_2026-02-22.md"


@dataclass
class FkSpec:
    name: str
    table: str
    local_cols: tuple[str, ...]
    ref_table: str
    ref_cols: tuple[str, ...]
    runtime_sensitive: bool


FK_SPECS = [
    FkSpec("FK_IS_UID_IID_LI", "TOMEHUB_ITEM_INDEX_STATE", ("FIREBASE_UID", "ITEM_ID"), "TOMEHUB_LIBRARY_ITEMS", ("FIREBASE_UID", "ITEM_ID"), False),
    FkSpec("FK_FR_UID_BID_LI", "TOMEHUB_FILE_REPORTS", ("FIREBASE_UID", "BOOK_ID"), "TOMEHUB_LIBRARY_ITEMS", ("FIREBASE_UID", "ITEM_ID"), False),
    FkSpec("FK_CNT_UID_BID_LI", "TOMEHUB_CONTENT", ("FIREBASE_UID", "BOOK_ID"), "TOMEHUB_LIBRARY_ITEMS", ("FIREBASE_UID", "ITEM_ID"), True),
    FkSpec("FK_IF_UID_BID_LI", "TOMEHUB_INGESTED_FILES", ("FIREBASE_UID", "BOOK_ID"), "TOMEHUB_LIBRARY_ITEMS", ("FIREBASE_UID", "ITEM_ID"), True),
]


def _constraint_row(cursor, name: str):
    cursor.execute(
        """
        SELECT CONSTRAINT_NAME, TABLE_NAME, STATUS, VALIDATED
        FROM USER_CONSTRAINTS
        WHERE CONSTRAINT_NAME = :n
        """,
        {"n": name.upper()},
    )
    return cursor.fetchone()


def _constraint_exists(cursor, name: str) -> bool:
    return _constraint_row(cursor, name) is not None


def _count(cursor, sql: str) -> int:
    cursor.execute(sql)
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _orphan_count_for_fk(cursor, spec: FkSpec) -> int:
    l1, l2 = spec.local_cols
    r1, r2 = spec.ref_cols
    return _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM {spec.table} x
        WHERE x.{l2} IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM {spec.ref_table} p
            WHERE p.{r1} = x.{l1}
              AND p.{r2} = x.{l2}
          )
        """,
    )


def _ensure_fk(cursor, spec: FkSpec, mode: str) -> str:
    """
    mode: DISABLE_NOVALIDATE | ENABLE_NOVALIDATE | ENABLE_VALIDATE
    """
    mode_sql = {
        "DISABLE_NOVALIDATE": "DISABLE NOVALIDATE",
        "ENABLE_NOVALIDATE": "ENABLE NOVALIDATE",
        "ENABLE_VALIDATE": "ENABLE VALIDATE",
    }[mode]
    local_cols = ", ".join(spec.local_cols)
    ref_cols = ", ".join(spec.ref_cols)

    if not _constraint_exists(cursor, spec.name):
        cursor.execute(
            f"""
            ALTER TABLE {spec.table}
            ADD CONSTRAINT {spec.name}
            FOREIGN KEY ({local_cols})
            REFERENCES {spec.ref_table} ({ref_cols})
            {mode_sql}
            """
        )
    else:
        cursor.execute(f"ALTER TABLE {spec.table} MODIFY CONSTRAINT {spec.name} {mode_sql}")

    row = _constraint_row(cursor, spec.name)
    if row:
        return f"{row[2]}/{row[3]}"
    return "UNKNOWN"


def run(execute: bool, enable_runtime_fks: bool, validate_safe: bool) -> int:
    print(f"=== Phase 3 FK Staged Apply ({'EXECUTE' if execute else 'DRY-RUN'}) ===")
    print(f"[INFO] enable_runtime_fks={enable_runtime_fks} validate_safe={validate_safe}")

    results: list[tuple[str, str, str]] = []
    failures = 0

    DatabaseManager.init_pool()
    try:
        with (DatabaseManager.get_write_connection() if execute else DatabaseManager.get_read_connection()) as conn:
            with conn.cursor() as cursor:
                # precheck canonical ref key exists
                uq = _constraint_row(cursor, "UQ_LIBITEM_UID_ITEM")
                if not uq:
                    print("[FAIL] Missing UQ_LIBITEM_UID_ITEM")
                    return 2
                print(f"[OK] Ref key constraint UQ_LIBITEM_UID_ITEM = {uq[2]}/{uq[3]}")

                for spec in FK_SPECS:
                    orphans = _orphan_count_for_fk(cursor, spec)
                    results.append((spec.name + ":orphans", "OK" if orphans == 0 else "WARN", str(orphans)))
                    print(f"[{'OK' if orphans == 0 else 'WARN'}] {spec.name} orphan_count={orphans}")

                if execute:
                    for spec in FK_SPECS:
                        orphans = _orphan_count_for_fk(cursor, spec)
                        if orphans > 0:
                            results.append((spec.name + ":apply", "WARN", "skipped_due_orphans"))
                            print(f"[WARN] {spec.name} skipped (orphans={orphans})")
                            continue

                        if spec.runtime_sensitive and not enable_runtime_fks:
                            mode = "DISABLE_NOVALIDATE"
                        else:
                            if validate_safe and not spec.runtime_sensitive:
                                mode = "ENABLE_VALIDATE"
                            else:
                                mode = "ENABLE_NOVALIDATE"

                        try:
                            status = _ensure_fk(cursor, spec, mode)
                            results.append((spec.name + ":apply", "OK", f"{mode}->{status}"))
                            print(f"[OK] {spec.name} {mode} => {status}")
                        except Exception as e:
                            failures += 1
                            results.append((spec.name + ":apply", "FAIL", str(e)))
                            print(f"[FAIL] {spec.name} apply error: {e}")
                    conn.commit()

                # record final statuses
                for spec in FK_SPECS:
                    row = _constraint_row(cursor, spec.name)
                    if row:
                        results.append((spec.name + ":final", "OK", f"{row[2]}/{row[3]}"))
                    else:
                        results.append((spec.name + ":final", "WARN", "MISSING"))

                legacy = _constraint_row(cursor, "FK_CONTENT_BOOK")
                if legacy:
                    results.append(("FK_CONTENT_BOOK:legacy", "OK", f"{legacy[2]}/{legacy[3]}"))
                else:
                    results.append(("FK_CONTENT_BOOK:legacy", "WARN", "MISSING"))

    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Phase 3 FK Staged Apply Report",
        "",
        f"- **Generated (UTC):** {ts}",
        f"- **Mode:** {'EXECUTE' if execute else 'DRY-RUN'}",
        f"- **enable_runtime_fks:** {enable_runtime_fks}",
        f"- **validate_safe:** {validate_safe}",
        "",
        "| Check | Status | Value |",
        "|---|---|---|",
    ]
    for name, status, value in results:
        lines.append(f"| `{name}` | `{status}` | `{str(value).replace('|','/')}` |")
    lines += [
        "",
        "## Notes",
        "",
        "- Runtime-sensitive FKs (`TOMEHUB_CONTENT`, `TOMEHUB_INGESTED_FILES`) remain disabled by default in this stage.",
        "- Enable them only after write-path ordering is verified under load.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[INFO] Report written: {REPORT_PATH.as_posix()}")

    if failures:
        print(f"[FAIL] Phase 3 FK staged apply completed with {failures} failure(s).")
        return 2
    print("[OK] Phase 3 FK staged apply completed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 3 staged FK apply to canonical library items")
    parser.add_argument("--execute", action="store_true", help="Apply FK create/modify actions")
    parser.add_argument("--enable-runtime-fks", action="store_true", help="Enable runtime-sensitive FKs (CONTENT, INGESTED_FILES) in this run")
    parser.add_argument("--validate-safe", action="store_true", help="Use ENABLE VALIDATE for non-runtime-safe FKs instead of ENABLE NOVALIDATE")
    args = parser.parse_args()
    return run(execute=bool(args.execute), enable_runtime_fks=bool(args.enable_runtime_fks), validate_safe=bool(args.validate_safe))


if __name__ == "__main__":
    raise SystemExit(main())

