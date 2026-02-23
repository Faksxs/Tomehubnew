#!/usr/bin/env python3
"""
Phase 3 quarantine/retry audit

Operationalizes the "quarantine/retry standardization" part of Phase 3 by producing
a consistent report over `TOMEHUB_INGESTION_RUNS` and `TOMEHUB_INGESTION_EVENTS`.

This script is read-only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE3_QUARANTINE_RETRY_AUDIT_2026-02-22.md"


def _fetch_rows(cursor, sql: str, params: dict | None = None):
    cursor.execute(sql, params or {})
    return cursor.fetchall()


def run() -> int:
    print("=== Phase 3 Quarantine/Retry Audit ===")
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as c:
                run_counts = _fetch_rows(
                    c,
                    """
                    SELECT NVL(STATUS, 'NULL') AS STATUS, COUNT(*)
                    FROM TOMEHUB_INGESTION_RUNS
                    GROUP BY NVL(STATUS, 'NULL')
                    ORDER BY COUNT(*) DESC, STATUS
                    """,
                )
                open_runs = _fetch_rows(
                    c,
                    """
                    SELECT RUN_ID, RUN_TYPE, STATUS, FIREBASE_UID, STARTED_AT, FINISHED_AT,
                           TOTAL_ITEMS, PROCESSED_ITEMS, SUCCESS_COUNT, FAILED_COUNT, QUARANTINE_COUNT
                    FROM TOMEHUB_INGESTION_RUNS
                    WHERE STATUS NOT IN ('COMPLETED', 'DRY_RUN')
                       OR FINISHED_AT IS NULL
                    ORDER BY STARTED_AT DESC
                    FETCH FIRST 50 ROWS ONLY
                    """,
                )
                quarantined_runs = _fetch_rows(
                    c,
                    """
                    SELECT RUN_ID, RUN_TYPE, STATUS, FIREBASE_UID, QUARANTINE_COUNT, FAILED_COUNT, STARTED_AT, FINISHED_AT
                    FROM TOMEHUB_INGESTION_RUNS
                    WHERE NVL(QUARANTINE_COUNT,0) > 0
                       OR NVL(FAILED_COUNT,0) > 0
                    ORDER BY STARTED_AT DESC
                    FETCH FIRST 100 ROWS ONLY
                    """,
                )
                event_status_counts = _fetch_rows(
                    c,
                    """
                    SELECT NVL(STATUS,'NULL') AS STATUS, COUNT(*)
                    FROM TOMEHUB_INGESTION_EVENTS
                    GROUP BY NVL(STATUS,'NULL')
                    ORDER BY COUNT(*) DESC, STATUS
                    """,
                )
                event_failures = _fetch_rows(
                    c,
                    """
                    SELECT RUN_ID, FIREBASE_UID, ITEM_ID, ENTITY_TYPE, EVENT_TYPE, STATUS, ERROR_CODE, ERROR_MESSAGE, CREATED_AT
                    FROM TOMEHUB_INGESTION_EVENTS
                    WHERE STATUS IN ('FAILED', 'ERROR', 'QUARANTINED')
                       OR ERROR_CODE IS NOT NULL
                    ORDER BY CREATED_AT DESC
                    FETCH FIRST 100 ROWS ONLY
                    """,
                )
                retry_candidates = _fetch_rows(
                    c,
                    """
                    SELECT EVENT_TYPE,
                           NVL(ERROR_CODE, 'NO_CODE') AS ERROR_CODE,
                           COUNT(*) AS CNT
                    FROM TOMEHUB_INGESTION_EVENTS
                    WHERE STATUS IN ('FAILED', 'ERROR', 'QUARANTINED')
                       OR ERROR_CODE IS NOT NULL
                    GROUP BY EVENT_TYPE, NVL(ERROR_CODE, 'NO_CODE')
                    ORDER BY CNT DESC, EVENT_TYPE, ERROR_CODE
                    """,
                )

    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Phase 3 Quarantine/Retry Audit",
        "",
        f"- **Generated (UTC):** {ts}",
        "",
        "## Ingestion Run Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, cnt in run_counts:
        lines.append(f"| `{status}` | {int(cnt)} |")

    lines += [
        "",
        "## Open or Incomplete Runs (Top 50)",
        "",
        "| RUN_ID | RUN_TYPE | STATUS | UID | STARTED_AT | FINISHED_AT | TOTAL | PROCESSED | SUCCESS | FAILED | QUARANTINE |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in open_runs:
        lines.append(
            f"| `{r[0]}` | `{r[1]}` | `{r[2]}` | `{r[3]}` | `{r[4]}` | `{r[5]}` | "
            f"{int(r[6] or 0)} | {int(r[7] or 0)} | {int(r[8] or 0)} | {int(r[9] or 0)} | {int(r[10] or 0)} |"
        )

    lines += [
        "",
        "## Runs With Failures/Quarantine (Top 100)",
        "",
        "| RUN_ID | RUN_TYPE | STATUS | UID | QUARANTINE | FAILED | STARTED_AT | FINISHED_AT |",
        "|---|---|---|---|---:|---:|---|---|",
    ]
    for r in quarantined_runs:
        lines.append(
            f"| `{r[0]}` | `{r[1]}` | `{r[2]}` | `{r[3]}` | {int(r[4] or 0)} | {int(r[5] or 0)} | `{r[6]}` | `{r[7]}` |"
        )

    lines += [
        "",
        "## Ingestion Event Status Counts",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status, cnt in event_status_counts:
        lines.append(f"| `{status}` | {int(cnt)} |")

    lines += [
        "",
        "## Retry Candidate Buckets",
        "",
        "| EVENT_TYPE | ERROR_CODE | Count |",
        "|---|---|---:|",
    ]
    for event_type, error_code, cnt in retry_candidates:
        lines.append(f"| `{event_type}` | `{error_code}` | {int(cnt)} |")

    lines += [
        "",
        "## Recent Failed/Quarantined Events (Top 100)",
        "",
        "| RUN_ID | UID | ITEM_ID | ENTITY_TYPE | EVENT_TYPE | STATUS | ERROR_CODE | CREATED_AT |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in event_failures:
        lines.append(
            f"| `{r[0]}` | `{r[1]}` | `{r[2]}` | `{r[3]}` | `{r[4]}` | `{r[5]}` | `{r[6]}` | `{r[8]}` |"
        )

    lines += [
        "",
        "## Standardization Notes",
        "",
        "- Treat `FAILED`, `ERROR`, `QUARANTINED` event statuses as retry candidates unless `ERROR_CODE` is classified terminal.",
        "- Future retry worker should be idempotent and keyed by `(RUN_ID, ITEM_ID, EVENT_TYPE)` or explicit event idempotency key.",
        "- Quarantine decisions should persist `ERROR_CODE` + normalized reason in `DETAILS_JSON` for deterministic retry routing.",
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Report written: {REPORT_PATH.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

