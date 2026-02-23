"""
Phase 6 release gate / readiness runner.

Purpose:
- Re-run critical validations from Phases 1-5
- Run targeted regression and Phase 4 smoke tests
- Check required reports/runbooks exist
- Produce a single readiness report with verdict

This script is non-destructive (validation only).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]

REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE6_RELEASE_GATE_READINESS_2026-02-22.md"


@dataclass
class StepResult:
    name: str
    status: str  # pass|warn|fail
    command: str | None
    exit_code: int | None
    notes: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""


def _run(cmd: list[str], *, env_extra: dict[str, str] | None = None, timeout_s: int = 600) -> StepResult:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )
    name = " ".join(cmd[:3]) if len(cmd) >= 3 else " ".join(cmd)
    return StepResult(
        name=name,
        status="pass" if p.returncode == 0 else "fail",
        command=" ".join(cmd),
        exit_code=p.returncode,
        stdout_tail="\n".join((p.stdout or "").splitlines()[-30:]),
        stderr_tail="\n".join((p.stderr or "").splitlines()[-30:]),
    )


def _check_file(path: Path, label: str, required: bool = True) -> StepResult:
    exists = path.exists()
    status = "pass" if exists else ("fail" if required else "warn")
    return StepResult(
        name=label,
        status=status,
        command=None,
        exit_code=None,
        notes=f"exists={exists} path={path}",
    )


def _run_validation_suite(include_phase5_reprofile: bool, uid: str | None) -> list[StepResult]:
    steps: list[StepResult] = []

    # Phase 1 checklist (script runs immediately; no --help mode)
    steps.append(_run([sys.executable, "apps/backend/scripts/run_phase1_checklist.py"], timeout_s=180))

    # Phase 2
    cmd_p2 = [sys.executable, "apps/backend/scripts/run_phase2_validation.py"]
    if uid:
        cmd_p2.extend(["--uid", uid])
    steps.append(_run(cmd_p2, timeout_s=300))

    # Phase 3 validations
    steps.append(_run([sys.executable, "apps/backend/scripts/run_phase3_integrity_hardening.py"], timeout_s=300))
    steps.append(_run([sys.executable, "apps/backend/scripts/run_phase3_highlight_parity_sweep.py"], timeout_s=600))
    steps.append(_run([sys.executable, "apps/backend/scripts/run_phase3_entity_parity_check.py"], timeout_s=600))
    steps.append(_run([sys.executable, "apps/backend/scripts/run_phase3_quarantine_retry_audit.py"], timeout_s=180))

    # Phase 4 regression + smoke
    unittest_cmd = [
        sys.executable, "-m", "unittest",
        "apps/backend/tests/test_search_exact_boundary.py",
        "apps/backend/tests/test_search_scope_filters.py",
        "apps/backend/tests/test_search_sql_safety.py",
        "apps/backend/tests/test_phase4_smoke_endpoints.py",
    ]
    steps.append(_run(unittest_cmd, env_extra={"PYTHONPATH": str(BACKEND_DIR)}, timeout_s=300))

    # Phase 5 artifacts/checks
    required_reports = [
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PROFILING_PRE_INDEX_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PROFILING_POST_INDEX_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PROFILING_POST_STATS_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_DBMS_STATS_REFRESH_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_QUERY_PLAN_SNAPSHOT_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE5_SEARCH_LOGS_PARTITION_RUNBOOK_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE6_CUTOVER_ROLLBACK_DRILL_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE6_LIVE_SMOKE_REAL_API_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE6_READ_WRITE_CUTOVER_PLAN_2026-02-22.md",
        REPO_ROOT / "documentation/reports/PHASE6_FIREBASE_WRITE_DISABLE_CHECKLIST_2026-02-22.md",
    ]
    for rp in required_reports:
        steps.append(_check_file(rp, f"artifact:{rp.name}"))

    # Optional: short re-profile for freshness during gate
    if include_phase5_reprofile:
        steps.append(
            _run(
                [
                    sys.executable,
                    "apps/backend/scripts/run_phase5_query_profiling.py",
                    "--runs",
                    "3",
                    "--report-path",
                    "documentation/reports/PHASE5_QUERY_PROFILING_GATECHECK_2026-02-22.md",
                ],
                timeout_s=300,
            )
        )

    return steps


def _manual_rollout_blockers() -> list[StepResult]:
    return [
        StepResult(
            name="manual:rollback_drill_execution",
            status="warn",
            command=None,
            exit_code=None,
            notes="Rollback runbooks exist, but full cutover rollback drill execution not performed in this runner.",
        ),
        StepResult(
            name="manual:phased_read_cutover_finalize",
            status="warn",
            command=None,
            exit_code=None,
            notes="Read cutover finalization is operational step; not executed by validation runner.",
        ),
        StepResult(
            name="manual:write_path_finalize_oracle_first",
            status="warn",
            command=None,
            exit_code=None,
            notes="Write path finalization/Firebase write disable are not executed automatically.",
        ),
    ]


def _verdict(steps: list[StepResult]) -> str:
    has_fail = any(s.status == "fail" for s in steps)
    has_warn = any(s.status == "warn" for s in steps)
    if has_fail:
        return "FAIL"
    if has_warn:
        return "CONDITIONAL_PASS"
    return "PASS"


def _render_report(steps: list[StepResult]) -> str:
    verdict = _verdict(steps)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Phase 6 Release Gate Readiness Report (2026-02-22)")
    lines.append("")
    lines.append(f"- Generated: `{ts}`")
    lines.append(f"- Verdict: `{verdict}`")
    lines.append("- Scope: Phase 1-5 validation reruns + targeted tests + artifact checks")
    lines.append("")

    lines.append("## Step Results")
    lines.append("")
    for s in steps:
        lines.append(f"### `{s.name}`")
        lines.append(f"- status: `{s.status}`")
        if s.command:
            lines.append(f"- command: `{s.command}`")
        if s.exit_code is not None:
            lines.append(f"- exit_code: `{s.exit_code}`")
        if s.notes:
            lines.append(f"- notes: {s.notes}")
        if s.stdout_tail:
            lines.append("- stdout_tail:")
            lines.append("```text")
            lines.append(s.stdout_tail)
            lines.append("```")
        if s.stderr_tail:
            lines.append("- stderr_tail:")
            lines.append("```text")
            lines.append(s.stderr_tail)
            lines.append("```")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    pass_count = sum(1 for s in steps if s.status == "pass")
    warn_count = sum(1 for s in steps if s.status == "warn")
    fail_count = sum(1 for s in steps if s.status == "fail")
    lines.append(f"- pass: `{pass_count}`")
    lines.append(f"- warn: `{warn_count}`")
    lines.append(f"- fail: `{fail_count}`")
    lines.append("")
    lines.append("## Cutover Guidance")
    lines.append("")
    if verdict == "FAIL":
        lines.append("- Do not proceed with cutover. Resolve failed checks first.")
    elif verdict == "CONDITIONAL_PASS":
        lines.append("- Technical validation checks passed, but operational/manual cutover steps remain.")
        lines.append("- Complete rollback drill + live API smoke + final cutover approvals before Firebase write disable.")
    else:
        lines.append("- Gate passed. Proceed with approved cutover runbook.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Phase 6 release gate readiness checks")
    ap.add_argument("--uid", help="Optional FIREBASE_UID for Phase 2 validation scoping")
    ap.add_argument("--skip-phase5-reprofile", action="store_true", help="Skip short Phase 5 re-profile")
    args = ap.parse_args()

    steps = _run_validation_suite(include_phase5_reprofile=not args.skip_phase5_reprofile, uid=args.uid)
    steps.extend(_manual_rollout_blockers())

    report = _render_report(steps)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"[OK] Wrote report: {REPORT_PATH}")
    verdict = _verdict(steps)
    print(f"[VERDICT] {verdict}")
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
