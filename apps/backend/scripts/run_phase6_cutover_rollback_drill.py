"""
Phase 6 cutover + rollback drill (dry-run / rehearsal).

Does not perform destructive DB changes.
Validates prerequisites, generates a sequenced rehearsal report, and marks
which steps remain manual for production cutover.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


DEFAULT_REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE6_CUTOVER_ROLLBACK_DRILL_2026-02-22.md"


@dataclass
class Item:
    step: str
    status: str  # pass|warn|fail
    notes: str


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _exists(cursor, kind: str, name: str) -> bool:
    if kind == "TABLE":
        cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :n", {"n": name.upper()})
    elif kind == "VIEW":
        cursor.execute("SELECT 1 FROM USER_VIEWS WHERE VIEW_NAME = :n", {"n": name.upper()})
    elif kind == "INDEX":
        cursor.execute("SELECT 1 FROM USER_INDEXES WHERE INDEX_NAME = :n", {"n": name.upper()})
    else:
        raise ValueError(kind)
    return cursor.fetchone() is not None


def _artifact(path: Path, label: str, required: bool = True) -> Item:
    exists = path.exists()
    status = "pass" if exists else ("fail" if required else "warn")
    return Item(label, status, f"exists={exists} path={path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 6 cutover/rollback drill rehearsal")
    ap.add_argument("--report-path", help="Output markdown path")
    args = ap.parse_args()
    report_path = Path(args.report_path).resolve() if args.report_path else DEFAULT_REPORT_PATH

    items: list[Item] = []
    DatabaseManager.init_pool()

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            # Core prereqs
            for t in ["TOMEHUB_LIBRARY_ITEMS", "TOMEHUB_CONTENT", "TOMEHUB_ITEM_INDEX_STATE", "TOMEHUB_SEARCH_LOGS"]:
                items.append(Item(f"db_table:{t}", "pass" if _exists(cursor, "TABLE", t) else "fail", "required for cutover"))
            for v in ["VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED", "VW_TOMEHUB_BOOKS_COMPAT", "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM"]:
                items.append(Item(f"db_view:{v}", "pass" if _exists(cursor, "VIEW", v) else "fail", "compatibility rollout surface"))

            # Key integrity/parity snapshots (non-destructive)
            content_orphans = _count(
                cursor,
                """
                SELECT COUNT(*)
                FROM TOMEHUB_CONTENT c
                WHERE c.BOOK_ID IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM TOMEHUB_LIBRARY_ITEMS li
                      WHERE li.FIREBASE_UID = c.FIREBASE_UID
                        AND li.ITEM_ID = c.BOOK_ID
                  )
                """,
            )
            items.append(Item("integrity:content_orphans_vs_library_items", "pass" if content_orphans == 0 else "fail", f"count={content_orphans}"))

            li_dups = _count(
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
            items.append(Item("integrity:library_items_duplicate_uid_item", "pass" if li_dups == 0 else "fail", f"count={li_dups}"))

            change_events_count = _count(cursor, "SELECT COUNT(*) FROM TOMEHUB_CHANGE_EVENTS")
            items.append(Item("ops:outbox_table_present", "pass", f"rows={change_events_count}"))

    # Artifacts from previous phases
    required_reports = [
        REPO_ROOT / "documentation/reports/PHASE3_ENTITY_PARITY_CHECK_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE3_HIGHLIGHT_PARITY_SWEEP_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md",
    ]
    for rp in required_reports:
        items.append(_artifact(rp, f"artifact:{rp.name}"))

    # Manual drill steps are rehearsed but not executed
    manual_steps = [
        "read_cutover_toggle_enable (compat views -> canonical reads)",
        "write_path_finalize (Oracle-first authoritative writes)",
        "firebase_write_disable",
        "rollback_rename_or_featureflag_revert",
    ]
    for step in manual_steps:
        items.append(Item(f"manual_rehearsed:{step}", "warn", "Runbook/checklist prepared; execution deferred"))

    verdict = "PASS" if not any(i.status == "fail" for i in items) else "FAIL"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 6 Cutover + Rollback Drill Report (Dry-Run) (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{now}`")
    lines.append(f"- Verdict: `{verdict}`")
    lines.append("- Mode: `DRY-RUN / REHEARSAL` (no destructive DB changes)")
    lines.append("")
    lines.append("## Checklist Results")
    lines.append("")
    for item in items:
        lines.append(f"- `{item.step}`: `{item.status}` - {item.notes}")
    lines.append("")
    lines.append("## Cutover Sequence (Rehearsed)")
    lines.append("")
    lines.append("1. Confirm latest release gate report is at least CONDITIONAL_PASS.")
    lines.append("2. Enable read cutover to canonical/view-first path in approved order.")
    lines.append("3. Run live smoke against /api/search, /api/smart-search, /api/realtime/poll, ingestion-status.")
    lines.append("4. Finalize Oracle-first write path and monitor outbox + ingestion health.")
    lines.append("5. Disable Firebase writes only after monitoring window is green.")
    lines.append("6. If regression detected, execute rollback checklist (toggle/rename reversion) immediately.")
    lines.append("")
    lines.append("## Rollback Sequence (Rehearsed)")
    lines.append("")
    lines.append("1. Pause/disable new write path toggle.")
    lines.append("2. Restore previous read path toggle.")
    lines.append("3. Verify core endpoints and search parity smoke.")
    lines.append("4. Keep Oracle data; do not destructive-reset during rollback.")
    lines.append("5. Document incident and diff before reattempt.")
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] Wrote report: {report_path}")
    print(f"[VERDICT] {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

