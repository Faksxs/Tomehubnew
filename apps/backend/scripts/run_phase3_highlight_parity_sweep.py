#!/usr/bin/env python3
"""
Phase 3 highlight/insight parity sweep (Firestore vs Oracle)

Wrapper around `reconcile_highlight_parity_to_oracle.py` for multiple users.

Default behavior:
- scans distinct FIREBASE_UIDs from TOMEHUB_CONTENT
- skips test-like users (`test_` prefix) unless `--include-test-users`
- runs dry-run parity check per user

Optional:
- `--execute-fix` reruns mismatched users with `--execute`
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager  # noqa: E402


REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE3_HIGHLIGHT_PARITY_SWEEP_2026-02-22.md"
SCRIPT_PATH = CURRENT_FILE.parent / "reconcile_highlight_parity_to_oracle.py"


SUMMARY_RE = re.compile(
    r"\[SUMMARY\].*?mismatches=(\d+).*?repaired=(\d+).*?failed=(\d+).*?fs_total_highlights_scoped=(\d+).*?ora_total_highlights_scoped_before=(\d+)",
    re.DOTALL,
)
POSTCHECK_RE = re.compile(r"\[POSTCHECK\]\s+remaining_mismatched_items=(\d+)")


@dataclass
class SweepRow:
    uid: str
    dry_exit: int
    dry_mismatches: int | None
    dry_failed: int | None
    dry_fs_total: int | None
    dry_ora_total: int | None
    executed: bool
    exec_exit: int | None = None
    exec_remaining: int | None = None
    note: str = ""


def _list_uids(include_test_users: bool) -> list[str]:
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT FIREBASE_UID
                    FROM TOMEHUB_CONTENT
                    WHERE FIREBASE_UID IS NOT NULL
                    ORDER BY FIREBASE_UID
                    """
                )
                rows = [str(r[0]) for r in cursor.fetchall() if r and r[0]]
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass
    if include_test_users:
        return rows
    return [u for u in rows if not u.startswith("test_")]


def _run_single(uid: str, execute: bool) -> tuple[int, str]:
    cmd = [sys.executable, str(SCRIPT_PATH), "--firebase-uid", uid]
    if execute:
        cmd.append("--execute")
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return int(proc.returncode), out


def _parse_summary(output: str) -> dict[str, int] | None:
    m = SUMMARY_RE.search(output)
    if not m:
        return None
    return {
        "mismatches": int(m.group(1)),
        "repaired": int(m.group(2)),
        "failed": int(m.group(3)),
        "fs_total": int(m.group(4)),
        "ora_total": int(m.group(5)),
    }


def _parse_postcheck(output: str) -> int | None:
    m = POSTCHECK_RE.search(output)
    return int(m.group(1)) if m else None


def _write_report(rows: list[SweepRow], include_test_users: bool, execute_fix: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Phase 3 Highlight Parity Sweep Report",
        "",
        f"- **Generated (UTC):** {ts}",
        f"- **Include test users:** {include_test_users}",
        f"- **Execute fix:** {execute_fix}",
        "",
        "## Results",
        "",
        "| UID | Dry Exit | Dry Mismatches | Dry Failed | FS Total | ORA Total | Executed | Exec Exit | Exec Remaining | Note |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r.uid}` | {r.dry_exit} | {'' if r.dry_mismatches is None else r.dry_mismatches} | "
            f"{'' if r.dry_failed is None else r.dry_failed} | {'' if r.dry_fs_total is None else r.dry_fs_total} | "
            f"{'' if r.dry_ora_total is None else r.dry_ora_total} | {str(r.executed)} | "
            f"{'' if r.exec_exit is None else r.exec_exit} | {'' if r.exec_remaining is None else r.exec_remaining} | "
            f"{r.note.replace('|', '/')} |"
        )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(include_test_users: bool, execute_fix: bool) -> int:
    uids = _list_uids(include_test_users=include_test_users)
    print("=== Phase 3 Highlight Parity Sweep ===")
    print(f"[INFO] users={len(uids)} include_test_users={include_test_users} execute_fix={execute_fix}")

    rows: list[SweepRow] = []
    fatal_failures = 0

    for uid in uids:
        print(f"\n[RUN] dry-run parity uid={uid}")
        dry_exit, dry_out = _run_single(uid=uid, execute=False)
        summary = _parse_summary(dry_out)
        row = SweepRow(
            uid=uid,
            dry_exit=dry_exit,
            dry_mismatches=(summary or {}).get("mismatches"),
            dry_failed=(summary or {}).get("failed"),
            dry_fs_total=(summary or {}).get("fs_total"),
            dry_ora_total=(summary or {}).get("ora_total"),
            executed=False,
        )

        if summary is None:
            row.note = "summary_parse_failed_or_script_error"
            print(dry_out.strip()[-800:])
            # treat as warning for test users, failure otherwise
            if not uid.startswith("test_"):
                fatal_failures += 1
        else:
            print(
                f"[INFO] uid={uid} mismatches={summary['mismatches']} failed={summary['failed']} "
                f"fs_total={summary['fs_total']} ora_total={summary['ora_total']}"
            )
            if execute_fix and summary["mismatches"] > 0:
                print(f"[RUN] execute repair uid={uid}")
                exec_exit, exec_out = _run_single(uid=uid, execute=True)
                row.executed = True
                row.exec_exit = exec_exit
                row.exec_remaining = _parse_postcheck(exec_out)
                exec_summary = _parse_summary(exec_out)
                if exec_summary:
                    row.note = (
                        f"repaired={exec_summary['repaired']}, failed={exec_summary['failed']}, "
                        f"remaining={row.exec_remaining}"
                    )
                else:
                    row.note = "execute_summary_parse_failed"
                print(exec_out.strip()[-1200:])
                if exec_exit != 0 or (row.exec_remaining is not None and row.exec_remaining != 0):
                    fatal_failures += 1

        rows.append(row)

    _write_report(rows, include_test_users=include_test_users, execute_fix=execute_fix)
    print(f"\n[INFO] Report written: {REPORT_PATH.as_posix()}")
    if fatal_failures:
        print(f"[FAIL] Phase 3 highlight parity sweep completed with {fatal_failures} failure(s).")
        return 2
    print("[OK] Phase 3 highlight parity sweep completed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run highlight/insight parity sweep across users")
    parser.add_argument("--include-test-users", action="store_true", help="Include test_* UIDs")
    parser.add_argument("--execute-fix", action="store_true", help="Repair mismatches after dry-run")
    args = parser.parse_args()
    return run(include_test_users=bool(args.include_test_users), execute_fix=bool(args.execute_fix))


if __name__ == "__main__":
    raise SystemExit(main())

