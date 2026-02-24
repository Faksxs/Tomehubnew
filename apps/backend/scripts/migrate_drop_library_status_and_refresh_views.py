"""
One-time Oracle migration:
- Drop redundant TOMEHUB_LIBRARY_ITEMS.STATUS (after parity check with INVENTORY_STATUS)
- Refresh compatibility views to current schema (GENERAL_NOTES/STATUS-free enriched view)
- Report legacy NOTES content-type rows (expected 0)

Safe defaults:
- Dry-run by default
- Apply only with --execute
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
from scripts.apply_phase1b_compat_views import (  # noqa: E402
    _view_sql_ingestion_status_by_item,
    _view_sql_library_items_enriched,
    _view_sql_library_items_legacy_books_compat,
)


LIB_TABLE = "TOMEHUB_LIBRARY_ITEMS"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Drop redundant LIBRARY_ITEMS.STATUS and refresh compat views")
    p.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    p.add_argument("--force", action="store_true", help="Allow drop even if STATUS/INVENTORY_STATUS mismatch rows exist")
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
        f"DROP_LIBRARY_STATUS_AND_REFRESH_VIEWS_{mode}_{date_str}.json",
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


def _view_status(cur, view_name: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT STATUS
        FROM USER_OBJECTS
        WHERE OBJECT_TYPE = 'VIEW'
          AND OBJECT_NAME = :p_name
        """,
        {"p_name": view_name.upper()},
    )
    row = cur.fetchone()
    return {"exists": bool(row), "status": str(row[0]) if row else None}


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
            report["precheck"]["status_exists"] = "STATUS" in lib_cols
            report["precheck"]["inventory_status_exists"] = "INVENTORY_STATUS" in lib_cols
            report["precheck"]["content_table"] = content_table

            if content_table:
                ct_cols = _columns(cur, content_table)
                type_col = "CONTENT_TYPE" if "CONTENT_TYPE" in ct_cols else ("SOURCE_TYPE" if "SOURCE_TYPE" in ct_cols else None)
                report["precheck"]["content_type_col"] = type_col
                if type_col:
                    report["precheck"]["content_notes_rows"] = _scalar(
                        cur,
                        f"SELECT COUNT(*) FROM {content_table} WHERE UPPER({type_col}) = 'NOTES'",
                    )

            if "STATUS" in lib_cols and "INVENTORY_STATUS" in lib_cols:
                report["precheck"]["status_nonnull_rows"] = _scalar(
                    cur,
                    f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE STATUS IS NOT NULL",
                )
                report["precheck"]["inventory_status_nonnull_rows"] = _scalar(
                    cur,
                    f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE INVENTORY_STATUS IS NOT NULL",
                )
                report["precheck"]["status_mismatch_rows"] = _scalar(
                    cur,
                    f"""
                    SELECT COUNT(*)
                    FROM {LIB_TABLE}
                    WHERE NVL(TRIM(STATUS), '__NULL__') <> NVL(TRIM(INVENTORY_STATUS), '__NULL__')
                    """,
                )

            report["precheck"]["views"] = {
                "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED": _view_status(cur, "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED"),
                "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM": _view_status(cur, "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM"),
                "VW_TOMEHUB_BOOKS_COMPAT": _view_status(cur, "VW_TOMEHUB_BOOKS_COMPAT"),
            }

            mismatch_rows = int(report["precheck"].get("status_mismatch_rows", 0))
            if mismatch_rows > 0 and not args.force:
                raise RuntimeError(
                    f"Refusing to drop {LIB_TABLE}.STATUS: {mismatch_rows} rows differ from INVENTORY_STATUS. Use --force after review."
                )

            if dry_run:
                report["steps"].append("Dry-run only; no ALTER/CREATE VIEW executed.")
                conn.rollback()
            else:
                if "STATUS" in lib_cols:
                    cur.execute(f"ALTER TABLE {LIB_TABLE} DROP COLUMN STATUS")
                    report["actions"]["dropped_column"] = f"{LIB_TABLE}.STATUS"
                else:
                    report["steps"].append("STATUS column already absent.")

                # Refresh compat views using current definitions (GENERAL_NOTES/STATUS removed from enriched view).
                cur.execute(_view_sql_library_items_enriched())
                cur.execute(_view_sql_ingestion_status_by_item())
                cur.execute(_view_sql_library_items_legacy_books_compat())
                report["actions"]["refreshed_views"] = [
                    "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED",
                    "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM",
                    "VW_TOMEHUB_BOOKS_COMPAT",
                ]
                conn.commit()
                report["steps"].append("Dropped STATUS and refreshed compatibility views.")

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            lib_cols_after = _columns(cur, LIB_TABLE)
            report["postcheck"]["library_columns"] = sorted(lib_cols_after)
            report["postcheck"]["status_exists"] = "STATUS" in lib_cols_after
            report["postcheck"]["inventory_status_exists"] = "INVENTORY_STATUS" in lib_cols_after
            report["postcheck"]["views"] = {
                "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED": _view_status(cur, "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED"),
                "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM": _view_status(cur, "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM"),
                "VW_TOMEHUB_BOOKS_COMPAT": _view_status(cur, "VW_TOMEHUB_BOOKS_COMPAT"),
            }

            # Optional smoke counts if view is valid.
            try:
                report["postcheck"]["enriched_view_count"] = _scalar(cur, "SELECT COUNT(*) FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED")
            except Exception as e:
                report["postcheck"]["enriched_view_count_error"] = str(e)

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
