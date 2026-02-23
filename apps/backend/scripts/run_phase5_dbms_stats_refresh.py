"""
Phase 5 DBMS_STATS refresh runner (safe operational optimization).

Refreshes optimizer statistics for key tables and writes a markdown report.
Default mode is dry-run.
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


DEFAULT_REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE5_DBMS_STATS_REFRESH_2026-02-22.md"
TARGET_TABLES = [
    "TOMEHUB_CONTENT",
    "TOMEHUB_INGESTED_FILES",
    "TOMEHUB_LIBRARY_ITEMS",
    "TOMEHUB_ITEM_INDEX_STATE",
    "TOMEHUB_SEARCH_LOGS",
]


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _get_stats_snapshot(cursor, tables: list[str]) -> dict[str, dict]:
    table_set = ",".join(f"'{t}'" for t in tables)
    cursor.execute(
        f"""
        SELECT TABLE_NAME,
               TO_CHAR(LAST_ANALYZED, 'YYYY-MM-DD HH24:MI:SS'),
               NUM_ROWS,
               BLOCKS,
               SAMPLE_SIZE,
               STALE_STATS
        FROM USER_TAB_STATISTICS
        WHERE TABLE_NAME IN ({table_set})
        ORDER BY TABLE_NAME
        """
    )
    out: dict[str, dict] = {}
    for row in cursor.fetchall():
        out[str(row[0])] = {
            "last_analyzed": str(row[1]) if row[1] is not None else None,
            "num_rows": int(row[2]) if row[2] is not None else None,
            "blocks": int(row[3]) if row[3] is not None else None,
            "sample_size": int(row[4]) if row[4] is not None else None,
            "stale_stats": str(row[5]) if row[5] is not None else None,
        }
    return out


def _obj_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :n", {"n": table_name.upper()})
    return cursor.fetchone() is not None


def _gather_stats(cursor, table_name: str, degree: int | None) -> None:
    plsql = """
    BEGIN
      DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => :p_tab,
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        no_invalidate    => FALSE,
        degree           => :p_degree
      );
    END;
    """
    cursor.execute(plsql, {"p_tab": table_name.upper(), "p_degree": degree})


def _render_report(
    *,
    execute: bool,
    degree: int | None,
    before: dict[str, dict],
    after: dict[str, dict],
    row_counts: dict[str, int],
    applied: list[str],
    skipped: list[str],
    errors: list[str],
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 5 DBMS_STATS Refresh Report (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{ts}`")
    lines.append(f"- Mode: `{'EXECUTE' if execute else 'DRYRUN'}`")
    lines.append(f"- Degree: `{degree}`")
    lines.append("")
    lines.append("## Target Tables")
    lines.append("")
    for t in TARGET_TABLES:
        lines.append(f"- `{t}` row_count=`{row_counts.get(t, 'n/a')}`")
    lines.append("")
    lines.append("## Actions")
    lines.append("")
    for t in applied:
        lines.append(f"- Applied: `{t}`")
    for t in skipped:
        lines.append(f"- Skipped: `{t}`")
    for e in errors:
        lines.append(f"- Error: `{e}`")
    if not (applied or skipped or errors):
        lines.append("- None")
    lines.append("")
    lines.append("## Stats Snapshot (Before -> After)")
    lines.append("")
    for t in TARGET_TABLES:
        b = before.get(t, {})
        a = after.get(t, {})
        lines.append(f"### `{t}`")
        lines.append(f"- `last_analyzed`: `{b.get('last_analyzed')}` -> `{a.get('last_analyzed')}`")
        lines.append(f"- `num_rows`: `{b.get('num_rows')}` -> `{a.get('num_rows')}`")
        lines.append(f"- `sample_size`: `{b.get('sample_size')}` -> `{a.get('sample_size')}`")
        lines.append(f"- `stale_stats`: `{b.get('stale_stats')}` -> `{a.get('stale_stats')}`")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `cascade=>TRUE` also refreshes dependent index stats.")
    lines.append("- Use this before plan comparisons to reduce optimizer jitter from stale stats.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 5 DBMS_STATS refresh")
    ap.add_argument("--execute", action="store_true", help="Apply DBMS_STATS (default dry-run)")
    ap.add_argument("--degree", type=int, default=2, help="DBMS_STATS degree (NULL to let Oracle decide)")
    ap.add_argument("--report-path", help="Output markdown path")
    args = ap.parse_args()
    report_path = Path(args.report_path).resolve() if args.report_path else DEFAULT_REPORT_PATH

    DatabaseManager.init_pool()
    applied: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    row_counts: dict[str, int] = {}
    before: dict[str, dict] = {}
    after: dict[str, dict] = {}

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            for t in TARGET_TABLES:
                if _obj_exists(cursor, t):
                    row_counts[t] = _count(cursor, f"SELECT COUNT(*) FROM {t}")
                else:
                    row_counts[t] = -1
            before = _get_stats_snapshot(cursor, TARGET_TABLES)

            for t in TARGET_TABLES:
                if row_counts.get(t, -1) < 0:
                    skipped.append(f"{t} (table missing)")
                    continue
                if not args.execute:
                    skipped.append(f"{t} (dry-run)")
                    continue
                try:
                    _gather_stats(cursor, t, args.degree)
                    applied.append(t)
                    print(f"[APPLY] DBMS_STATS {t}")
                except Exception as e:
                    errors.append(f"{t}: {e}")
                    print(f"[ERROR] DBMS_STATS {t}: {e}")
            if args.execute:
                conn.commit()
            after = _get_stats_snapshot(cursor, TARGET_TABLES)

    report_text = _render_report(
        execute=args.execute,
        degree=args.degree,
        before=before,
        after=after,
        row_counts=row_counts,
        applied=applied,
        skipped=skipped,
        errors=errors,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    print(f"[OK] Wrote report: {report_path}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

