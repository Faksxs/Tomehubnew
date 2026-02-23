"""
Phase 5 query profiling + index candidate audit (baseline).

Non-destructive:
- measures representative query timings on live Oracle
- audits candidate index coverage
- summarizes SEARCH_LOGS volume/time distribution
- writes markdown report
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


DEFAULT_REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE5_QUERY_PROFILING_BASELINE_2026-02-22.md"


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


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _scalar(cursor, sql: str, params: dict | None = None):
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return row[0] if row else None


@dataclass
class TimingResult:
    name: str
    runs: int
    row_count: int
    p50_ms: float
    p95_ms: float
    max_ms: float


def _time_query(cursor, name: str, sql: str, params: dict, runs: int = 5) -> TimingResult:
    times_ms: list[float] = []
    row_count = 0
    for _ in range(max(1, runs)):
        t0 = time.perf_counter()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        times_ms.append(elapsed_ms)
        row_count = len(rows)
    times_sorted = sorted(times_ms)
    p50 = statistics.median(times_sorted)
    p95_idx = min(len(times_sorted) - 1, int(round(0.95 * (len(times_sorted) - 1))))
    p95 = times_sorted[p95_idx]
    return TimingResult(
        name=name,
        runs=len(times_sorted),
        row_count=row_count,
        p50_ms=round(p50, 2),
        p95_ms=round(p95, 2),
        max_ms=round(max(times_sorted), 2),
    )


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
    return str(row[0]) if row and row[0] else None


def _sample_uid_and_book(cursor, uid_override: str | None) -> tuple[str | None, str | None]:
    if uid_override:
        cursor.execute(
            """
            SELECT FIREBASE_UID, ITEM_ID
            FROM TOMEHUB_LIBRARY_ITEMS
            WHERE FIREBASE_UID = :p_uid
            ORDER BY UPDATED_AT DESC NULLS LAST
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
        return (str(row[0]), str(row[1]))

    cursor.execute(
        """
        SELECT FIREBASE_UID, BOOK_ID
        FROM TOMEHUB_CONTENT
        WHERE FIREBASE_UID IS NOT NULL AND BOOK_ID IS NOT NULL
        FETCH FIRST 1 ROWS ONLY
        """
    )
    row = cursor.fetchone()
    if row:
        return (str(row[0]), str(row[1]))
    return (None, None)


def _candidate_index_coverage(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT ic.INDEX_NAME, ic.TABLE_NAME, ic.COLUMN_POSITION, ic.COLUMN_NAME
        FROM USER_IND_COLUMNS ic
        JOIN USER_INDEXES ix ON ix.INDEX_NAME = ic.INDEX_NAME
        WHERE ic.TABLE_NAME IN ('TOMEHUB_CONTENT', 'TOMEHUB_INGESTED_FILES', 'TOMEHUB_SEARCH_LOGS')
        ORDER BY ic.TABLE_NAME, ic.INDEX_NAME, ic.COLUMN_POSITION
        """
    )
    rows = cursor.fetchall()
    by_index: dict[tuple[str, str], list[str]] = {}
    for r in rows:
        key = (str(r[1]), str(r[0]))
        by_index.setdefault(key, []).append(str(r[3]))

    targets = [
        ("TOMEHUB_CONTENT", ["FIREBASE_UID", "BOOK_ID", "SOURCE_TYPE"]),
        ("TOMEHUB_CONTENT", ["FIREBASE_UID", "BOOK_ID", "CREATED_AT"]),
        ("TOMEHUB_CONTENT", ["FIREBASE_UID", "BOOK_ID", "CONTENT_TYPE"]),
        ("TOMEHUB_INGESTED_FILES", ["FIREBASE_UID", "BOOK_ID"]),
        ("TOMEHUB_SEARCH_LOGS", ["TIMESTAMP"]),
    ]
    coverage: list[dict] = []
    for table, target_cols in targets:
        matched_indexes = []
        for (tbl, idx), cols in by_index.items():
            if tbl != table:
                continue
            if cols[: len(target_cols)] == target_cols:
                matched_indexes.append(idx)
        coverage.append(
            {
                "table": table,
                "target": ", ".join(target_cols),
                "covered": bool(matched_indexes),
                "indexes": matched_indexes,
            }
        )
    return coverage


def _build_report(
    *,
    ts_col: str | None,
    table_counts: dict[str, int],
    stats_last_analyzed: list[tuple[str, str]],
    index_coverage: list[dict],
    timings: list[TimingResult],
    search_log_days: list[tuple[str, int]],
    sample_uid: str | None,
    sample_book_id: str | None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 5 Query Profiling Baseline (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append("- Scope: non-destructive profiling + index candidate audit")
    lines.append(f"- Sample uid: `{sample_uid}`")
    lines.append(f"- Sample book_id: `{sample_book_id}`")
    lines.append(f"- SEARCH_LOGS time column: `{ts_col}`")
    lines.append("")
    lines.append("## Table Counts")
    lines.append("")
    for k, v in table_counts.items():
        lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("## Table Stats Freshness")
    lines.append("")
    if stats_last_analyzed:
        for t, d in stats_last_analyzed:
            lines.append(f"- `{t}` last_analyzed: `{d}`")
    else:
        lines.append("- No stats rows found")
    lines.append("")
    lines.append("## Candidate Index Coverage")
    lines.append("")
    for item in index_coverage:
        status = "YES" if item["covered"] else "NO"
        idxs = ", ".join(f"`{x}`" for x in item["indexes"]) if item["indexes"] else "-"
        lines.append(f"- `{item['table']}({item['target']})` covered: `{status}` | indexes: {idxs}")
    lines.append("")
    lines.append("## Representative Query Timings")
    lines.append("")
    for t in timings:
        lines.append(
            f"- `{t.name}`: rows={t.row_count}, runs={t.runs}, "
            f"p50={t.p50_ms}ms, p95={t.p95_ms}ms, max={t.max_ms}ms"
        )
    lines.append("")
    lines.append("## SEARCH_LOGS Recent Daily Volume")
    lines.append("")
    if search_log_days:
        for day, cnt in search_log_days:
            lines.append(f"- `{day}`: `{cnt}`")
    else:
        lines.append("- No rows found")
    lines.append("")
    lines.append("## Phase 5 Next Actions")
    lines.append("")
    lines.append("1. Apply missing high-ROI indexes only where coverage=NO and timings justify.")
    lines.append("2. Verify `SEARCH_LOGS(TIMESTAMP)` access path before partition migration.")
    lines.append("3. Prepare partition migration runbook (attach/backfill/retention) after baseline sign-off.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5 profiling baseline (safe).")
    parser.add_argument("--uid", help="Optional firebase_uid scope for sample selection")
    parser.add_argument("--runs", type=int, default=5, help="Timing runs per query")
    parser.add_argument(
        "--report-path",
        help="Optional output markdown path (defaults to Phase5 baseline report path)",
    )
    args = parser.parse_args()
    report_path = Path(args.report_path).resolve() if args.report_path else DEFAULT_REPORT_PATH

    DatabaseManager.init_pool()

    timings: list[TimingResult] = []
    table_counts: dict[str, int] = {}
    stats_last_analyzed: list[tuple[str, str]] = []
    search_log_days: list[tuple[str, int]] = []

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            sample_uid, sample_book_id = _sample_uid_and_book(cursor, args.uid)
            ts_col = _detect_search_logs_ts_col(cursor)

            for table in [
                "TOMEHUB_CONTENT",
                "TOMEHUB_LIBRARY_ITEMS",
                "TOMEHUB_ITEM_INDEX_STATE",
                "TOMEHUB_INGESTED_FILES",
                "TOMEHUB_SEARCH_LOGS",
            ]:
                try:
                    table_counts[table] = _count(cursor, f"SELECT COUNT(*) FROM {table}")
                    _ok(f"Count `{table}`", table_counts[table])
                except Exception as e:
                    _warn(f"Count `{table}` failed", e)
                    table_counts[table] = -1

            cursor.execute(
                """
                SELECT TABLE_NAME, TO_CHAR(LAST_ANALYZED, 'YYYY-MM-DD HH24:MI:SS')
                FROM USER_TAB_STATISTICS
                WHERE TABLE_NAME IN (
                    'TOMEHUB_CONTENT','TOMEHUB_SEARCH_LOGS','TOMEHUB_LIBRARY_ITEMS','TOMEHUB_INGESTED_FILES'
                )
                ORDER BY TABLE_NAME
                """
            )
            stats_last_analyzed = [(str(r[0]), str(r[1])) for r in cursor.fetchall()]

            index_coverage = _candidate_index_coverage(cursor)
            for c in index_coverage:
                _ok(f"Index coverage {c['table']}({c['target']})", "YES" if c["covered"] else "NO")

            if sample_uid and sample_book_id:
                timings.append(
                    _time_query(
                        cursor,
                        "content_by_uid_book_source_type",
                        """
                        SELECT ID
                        FROM TOMEHUB_CONTENT
                        WHERE FIREBASE_UID = :p_uid
                          AND BOOK_ID = :p_book_id
                          AND SOURCE_TYPE = :p_source
                        FETCH FIRST 100 ROWS ONLY
                        """,
                        {"p_uid": sample_uid, "p_book_id": sample_book_id, "p_source": "HIGHLIGHT"},
                        runs=args.runs,
                    )
                )
                timings.append(
                    _time_query(
                        cursor,
                        "content_by_uid_book_created_at",
                        """
                        SELECT ID, CREATED_AT
                        FROM TOMEHUB_CONTENT
                        WHERE FIREBASE_UID = :p_uid
                          AND BOOK_ID = :p_book_id
                        ORDER BY CREATED_AT DESC NULLS LAST
                        FETCH FIRST 100 ROWS ONLY
                        """,
                        {"p_uid": sample_uid, "p_book_id": sample_book_id},
                        runs=args.runs,
                    )
                )
                timings.append(
                    _time_query(
                        cursor,
                        "library_item_by_uid",
                        """
                        SELECT ITEM_ID, ITEM_TYPE, TITLE
                        FROM TOMEHUB_LIBRARY_ITEMS
                        WHERE FIREBASE_UID = :p_uid
                        FETCH FIRST 200 ROWS ONLY
                        """,
                        {"p_uid": sample_uid},
                        runs=args.runs,
                    )
                )
                timings.append(
                    _time_query(
                        cursor,
                        "ingestion_status_view_by_uid",
                        """
                        SELECT ITEM_ID, INGESTION_STATUS, CHUNK_COUNT
                        FROM VW_TOMEHUB_INGESTION_STATUS_BY_ITEM
                        WHERE FIREBASE_UID = :p_uid
                        FETCH FIRST 200 ROWS ONLY
                        """,
                        {"p_uid": sample_uid},
                        runs=args.runs,
                    )
                )
            else:
                _warn("Could not sample uid/book; skipping scoped timings")
                sample_uid, sample_book_id = None, None

            if ts_col:
                q = f'''
                    SELECT TO_CHAR(TRUNC("{ts_col}"), 'YYYY-MM-DD') AS d, COUNT(*)
                    FROM TOMEHUB_SEARCH_LOGS
                    GROUP BY TRUNC("{ts_col}")
                    ORDER BY TRUNC("{ts_col}") DESC
                    FETCH FIRST 14 ROWS ONLY
                '''
                cursor.execute(q)
                search_log_days = [(str(r[0]), int(r[1] or 0)) for r in cursor.fetchall()]

                timings.append(
                    _time_query(
                        cursor,
                        "search_logs_recent_window",
                        f'''
                        SELECT ID, "{ts_col}"
                        FROM TOMEHUB_SEARCH_LOGS
                        WHERE "{ts_col}" >= SYSTIMESTAMP - INTERVAL '30' DAY
                        ORDER BY "{ts_col}" DESC
                        FETCH FIRST 200 ROWS ONLY
                        ''',
                        {},
                        runs=args.runs,
                    )
                )
            else:
                _warn("SEARCH_LOGS timestamp column not found")

    report = _build_report(
        ts_col=ts_col,
        table_counts=table_counts,
        stats_last_analyzed=stats_last_analyzed,
        index_coverage=index_coverage,
        timings=timings,
        search_log_days=search_log_days,
        sample_uid=sample_uid,
        sample_book_id=sample_book_id,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    _ok("Wrote report", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
