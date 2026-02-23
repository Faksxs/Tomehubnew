"""
Phase 5 query plan snapshot (EXPLAIN PLAN + DBMS_XPLAN.DISPLAY).

Captures representative plans after indexing/stats work.
Default mode reads only and writes a markdown report.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


DEFAULT_REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md"


def _detect_search_logs_ts_col(cursor) -> str | None:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = 'TOMEHUB_SEARCH_LOGS'
          AND COLUMN_NAME IN ('TIMESTAMP', 'CREATED_AT')
        ORDER BY CASE WHEN COLUMN_NAME = 'TIMESTAMP' THEN 1 ELSE 2 END
        """
    )
    row = cursor.fetchone()
    return str(row[0]) if row else None


def _sample_uid_and_book(cursor, uid_override: str | None) -> tuple[str | None, str | None]:
    if uid_override:
        cursor.execute(
            """
            SELECT FIREBASE_UID, ITEM_ID
            FROM TOMEHUB_LIBRARY_ITEMS
            WHERE FIREBASE_UID = :p_uid
            FETCH FIRST 1 ROWS ONLY
            """,
            {"p_uid": uid_override},
        )
    else:
        cursor.execute(
            """
            SELECT FIREBASE_UID, ITEM_ID
            FROM TOMEHUB_LIBRARY_ITEMS
            ORDER BY UPDATED_AT DESC NULLS LAST
            FETCH FIRST 1 ROWS ONLY
            """
        )
    row = cursor.fetchone()
    if row:
        return str(row[0]), str(row[1])
    return None, None


def _xplan_for(cursor, statement_id: str, sql_text: str, binds: dict) -> str:
    try:
        cursor.execute("DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :sid", {"sid": statement_id})
    except Exception:
        # PLAN_TABLE may not be directly manageable; continue.
        pass

    cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql_text}", binds)
    cursor.execute(
        """
        SELECT PLAN_TABLE_OUTPUT
        FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', :sid, 'BASIC +PREDICATE +ALIAS +NOTE'))
        """,
        {"sid": statement_id},
    )
    return "\n".join(str(r[0]) for r in cursor.fetchall())


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture Phase 5 query plan snapshot")
    ap.add_argument("--uid", help="Optional firebase_uid for scoped queries")
    ap.add_argument("--report-path", help="Output markdown path")
    args = ap.parse_args()
    report_path = Path(args.report_path).resolve() if args.report_path else DEFAULT_REPORT_PATH

    DatabaseManager.init_pool()
    sections: list[tuple[str, str, str]] = []
    ts_col = None
    sample_uid = None
    sample_book_id = None

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            sample_uid, sample_book_id = _sample_uid_and_book(cursor, args.uid)
            ts_col = _detect_search_logs_ts_col(cursor)
            if not sample_uid or not sample_book_id:
                raise RuntimeError("Could not resolve sample FIREBASE_UID/BOOK_ID from TOMEHUB_LIBRARY_ITEMS")

            cases = [
                (
                    "content_uid_book_source_type",
                    """
                    SELECT ID
                    FROM TOMEHUB_CONTENT
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
                      AND SOURCE_TYPE = :p_source
                    FETCH FIRST 100 ROWS ONLY
                    """,
                    {"p_uid": sample_uid, "p_book_id": sample_book_id, "p_source": "HIGHLIGHT"},
                ),
                (
                    "content_uid_book_content_type",
                    """
                    SELECT ID
                    FROM TOMEHUB_CONTENT
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
                      AND CONTENT_TYPE = :p_content_type
                    FETCH FIRST 100 ROWS ONLY
                    """,
                    {"p_uid": sample_uid, "p_book_id": sample_book_id, "p_content_type": "HIGHLIGHT"},
                ),
                (
                    "ingested_files_uid_book",
                    """
                    SELECT ID, STATUS, CHUNK_COUNT
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE FIREBASE_UID = :p_uid
                      AND BOOK_ID = :p_book_id
                    """,
                    {"p_uid": sample_uid, "p_book_id": sample_book_id},
                ),
                (
                    "ingestion_status_view_uid",
                    """
                    SELECT ITEM_ID, INGESTION_STATUS, CHUNK_COUNT
                    FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM
                    WHERE FIREBASE_UID = :p_uid
                    FETCH FIRST 100 ROWS ONLY
                    """,
                    {"p_uid": sample_uid},
                ),
            ]
            if ts_col:
                cases.append(
                    (
                        "search_logs_recent_window",
                        f"""
                        SELECT ID, "{ts_col}"
                        FROM TOMEHUB_SEARCH_LOGS
                        WHERE "{ts_col}" >= SYSTIMESTAMP - INTERVAL '30' DAY
                        ORDER BY "{ts_col}" DESC
                        FETCH FIRST 200 ROWS ONLY
                        """,
                        {},
                    )
                )

            for idx, (name, sql_text, binds) in enumerate(cases, start=1):
                sid = f"P5_{idx}_{name[:20]}".upper()
                try:
                    plan = _xplan_for(cursor, sid, sql_text, binds)
                except Exception as e:
                    plan = f"[ERROR] {e}"
                sections.append((name, sql_text.strip(), plan))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 5 Query Plan Snapshot (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- Sample uid: `{sample_uid}`")
    lines.append(f"- Sample book_id: `{sample_book_id}`")
    lines.append(f"- SEARCH_LOGS time column: `{ts_col}`")
    lines.append("")
    for name, sql_text, plan in sections:
        lines.append(f"## `{name}`")
        lines.append("")
        lines.append("```sql")
        lines.append(sql_text)
        lines.append("```")
        lines.append("")
        lines.append("```text")
        lines.append(plan.rstrip())
        lines.append("```")
        lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Wrote report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

