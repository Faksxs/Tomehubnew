"""
One-time Oracle migration:
- Move TOMEHUB_LIBRARY_ITEMS.GENERAL_NOTES -> SUMMARY_TEXT for non-personal items (if SUMMARY_TEXT is empty)
- Clear GENERAL_NOTES values (all item types)
- Drop TOMEHUB_LIBRARY_ITEMS.GENERAL_NOTES column

Also reports legacy TOMEHUB_CONTENT(_V2) CONTENT_TYPE='NOTES' row count (expected 0).

Safe defaults:
- Dry-run by default
- Writes only with --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from infrastructure.db_manager import DatabaseManager  # noqa: E402
from services.library_service import resolve_active_content_table  # noqa: E402


LIB_TABLE = "TOMEHUB_LIBRARY_ITEMS"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Remove GENERAL_NOTES column and legacy NOTES concept usage")
    p.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    p.add_argument("--report", help="Optional JSON report path")
    return p.parse_args()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _default_report_path(dry_run: bool) -> str:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    mode = "DRY_RUN" if dry_run else "APPLY"
    return os.path.join(
        ROOT,
        "..",
        "..",
        "documentation",
        "reports",
        f"REMOVE_GENERAL_NOTES_AND_LEGACY_NOTES_{mode}_{date_str}.json",
    )


def _columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT COLUMN_NAME
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = :p_table
        """,
        {"p_table": table_name.upper()},
    )
    return {str(r[0]).upper() for r in cur.fetchall()}


def _content_shape(cur, table_name: str) -> tuple[str | None, str | None]:
    cols = _columns(cur, table_name)
    item_col = "ITEM_ID" if "ITEM_ID" in cols else ("BOOK_ID" if "BOOK_ID" in cols else None)
    type_col = "CONTENT_TYPE" if "CONTENT_TYPE" in cols else ("SOURCE_TYPE" if "SOURCE_TYPE" in cols else None)
    return item_col, type_col


def _scalar(cur, sql: str, binds: dict[str, Any] | None = None) -> int:
    cur.execute(sql, binds or {})
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)


def main() -> int:
    args = _parse_args()
    dry_run = not bool(args.execute)

    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "dry_run": dry_run,
        "steps": [],
        "precheck": {},
        "actions": {},
        "postcheck": {},
        "errors": [],
    }

    content_table = resolve_active_content_table()

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            for stmt in (
                "ALTER SESSION DISABLE PARALLEL QUERY",
                "ALTER SESSION DISABLE PARALLEL DML",
            ):
                try:
                    cur.execute(stmt)
                except Exception:
                    pass
            lib_cols = _columns(cur, LIB_TABLE)
            report["precheck"]["library_columns"] = sorted(lib_cols)
            report["precheck"]["general_notes_exists"] = "GENERAL_NOTES" in lib_cols
            report["precheck"]["summary_text_exists"] = "SUMMARY_TEXT" in lib_cols
            report["precheck"]["content_table"] = content_table

            if content_table:
                item_col, type_col = _content_shape(cur, content_table)
                report["precheck"]["content_table_item_col"] = item_col
                report["precheck"]["content_table_type_col"] = type_col
                if type_col:
                    report["precheck"]["content_notes_rows"] = _scalar(
                        cur,
                        f"SELECT COUNT(*) FROM {content_table} WHERE UPPER({type_col}) = 'NOTES'",
                    )
                    report["precheck"]["content_personal_note_rows"] = _scalar(
                        cur,
                        f"SELECT COUNT(*) FROM {content_table} WHERE UPPER({type_col}) = 'PERSONAL_NOTE'",
                    )

            if "GENERAL_NOTES" in lib_cols:
                report["precheck"]["lib_non_note_general_notes_rows"] = _scalar(
                    cur,
                    f"""
                    SELECT COUNT(*)
                    FROM {LIB_TABLE}
                    WHERE ITEM_TYPE IN ('BOOK','ARTICLE','WEBSITE')
                      AND GENERAL_NOTES IS NOT NULL
                    """,
                )
                if "SUMMARY_TEXT" in lib_cols:
                    report["precheck"]["lib_non_note_general_notes_to_migrate"] = _scalar(
                        cur,
                        f"""
                        SELECT COUNT(*)
                        FROM {LIB_TABLE}
                        WHERE ITEM_TYPE IN ('BOOK','ARTICLE','WEBSITE')
                          AND GENERAL_NOTES IS NOT NULL
                          AND SUMMARY_TEXT IS NULL
                        """,
                    )
                report["precheck"]["lib_personal_note_general_notes_rows"] = _scalar(
                    cur,
                    f"""
                    SELECT COUNT(*)
                    FROM {LIB_TABLE}
                    WHERE ITEM_TYPE = 'PERSONAL_NOTE'
                      AND GENERAL_NOTES IS NOT NULL
                    """,
                )
                report["precheck"]["lib_general_notes_total_rows"] = _scalar(
                    cur,
                    f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE GENERAL_NOTES IS NOT NULL",
                )

            if "GENERAL_NOTES" not in lib_cols:
                report["steps"].append("GENERAL_NOTES column already absent; nothing to drop.")
                conn.rollback()
            elif "SUMMARY_TEXT" not in lib_cols:
                raise RuntimeError("SUMMARY_TEXT column is missing; refusing to migrate/drop GENERAL_NOTES.")
            else:
                migrate_sql = f"""
                    UPDATE /*+ NO_PARALLEL */ {LIB_TABLE}
                    SET SUMMARY_TEXT = GENERAL_NOTES
                    WHERE ITEM_TYPE IN ('BOOK','ARTICLE','WEBSITE')
                      AND GENERAL_NOTES IS NOT NULL
                      AND SUMMARY_TEXT IS NULL
                """
                clear_sql = f"""
                    UPDATE /*+ NO_PARALLEL */ {LIB_TABLE}
                    SET GENERAL_NOTES = NULL
                    WHERE GENERAL_NOTES IS NOT NULL
                """

                if dry_run:
                    report["steps"].append("Dry-run only; no UPDATE/ALTER executed.")
                    conn.rollback()
                else:
                    cur.execute(migrate_sql)
                    report["actions"]["migrated_non_note_general_notes_to_summary_text"] = int(cur.rowcount or 0)
                    cur.execute(clear_sql)
                    report["actions"]["cleared_general_notes_rows"] = int(cur.rowcount or 0)
                    cur.execute(f"ALTER TABLE {LIB_TABLE} DROP COLUMN GENERAL_NOTES")
                    report["actions"]["dropped_column"] = "GENERAL_NOTES"
                    conn.commit()
                    report["steps"].append("Applied migration, cleared GENERAL_NOTES values, dropped column.")

        # fresh read after commit/rollback
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            lib_cols_after = _columns(cur, LIB_TABLE)
            report["postcheck"]["library_columns"] = sorted(lib_cols_after)
            report["postcheck"]["general_notes_exists"] = "GENERAL_NOTES" in lib_cols_after
            if "SUMMARY_TEXT" in lib_cols_after:
                report["postcheck"]["summary_text_non_note_rows"] = _scalar(
                    cur,
                    f"""
                    SELECT COUNT(*)
                    FROM {LIB_TABLE}
                    WHERE ITEM_TYPE IN ('BOOK','ARTICLE','WEBSITE')
                      AND SUMMARY_TEXT IS NOT NULL
                    """,
                )

    report["finished_at"] = _now_iso()
    out_path = args.report or _default_report_path(dry_run=dry_run)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(report), f, ensure_ascii=False, indent=2)
    print(f"[OK] Report written: {out_path}")
    print(json.dumps(_json_safe(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
