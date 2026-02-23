#!/usr/bin/env python3
"""
Phase 1C: Audit TOMEHUB_BOOKS write-path DML callsites.

Scans repo source files for INSERT/MERGE/UPDATE/DELETE statements targeting
TOMEHUB_BOOKS and emits a Markdown report for migration routing prep.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "documentation" / "reports" / "PHASE1C_TOMEHUB_BOOKS_DML_AUDIT_2026-02-22.md"

SCAN_ROOTS = [
    REPO_ROOT / "apps" / "backend",
    REPO_ROOT / "scripts",
]

INCLUDE_SUFFIXES = {".py", ".sql", ".md"}

PATTERNS = [
    ("MERGE", re.compile(r"\bMERGE\s+INTO\s+TOMEHUB_BOOKS\b", re.IGNORECASE)),
    ("INSERT", re.compile(r"\bINSERT\s+INTO\s+TOMEHUB_BOOKS\b", re.IGNORECASE)),
    ("UPDATE", re.compile(r"\bUPDATE\s+TOMEHUB_BOOKS\b", re.IGNORECASE)),
    ("DELETE", re.compile(r"\bDELETE\s+FROM\s+TOMEHUB_BOOKS\b", re.IGNORECASE)),
]


@dataclass
class Finding:
    op: str
    file_path: str
    line_no: int
    line_text: str
    category: str
    recommended_action: str


def _classify(path: Path) -> str:
    p = path.as_posix().lower()
    if "/apps/backend/services/" in p or p.endswith("/apps/backend/app.py"):
        return "runtime"
    if "/tests/" in p or "/test_" in p:
        return "test"
    if "/apps/backend/scripts/" in p:
        return "script"
    if "/apps/backend/" in p and any(tok in path.name.lower() for tok in ("fix_", "sync_", "revert_", "migrate_")):
        return "maintenance"
    return "other"


def _recommended_action(category: str, op: str) -> str:
    if category == "runtime":
        if op in {"INSERT", "MERGE", "UPDATE", "DELETE"}:
            return "Migrate to TOMEHUB_LIBRARY_ITEMS write path (or central abstraction) before view-based cutover"
    if category in {"maintenance", "script"}:
        return "Review for one-off usage; patch only if still operationally used in migration/cutover"
    if category == "test":
        return "Update after runtime write path changes stabilize"
    return "Manual review"


def _scan_file(path: Path) -> List[Finding]:
    findings: List[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = text.splitlines()
    category = _classify(path)
    rel = path.relative_to(REPO_ROOT).as_posix()

    for idx, line in enumerate(lines, start=1):
        for op, rx in PATTERNS:
            if rx.search(line):
                findings.append(
                    Finding(
                        op=op,
                        file_path=rel,
                        line_no=idx,
                        line_text=line.strip(),
                        category=category,
                        recommended_action=_recommended_action(category, op),
                    )
                )
    return findings


def scan_repo() -> List[Finding]:
    findings: List[Finding] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in INCLUDE_SUFFIXES:
                continue
            findings.extend(_scan_file(path))
    findings.sort(key=lambda f: (f.category, f.file_path, f.line_no))
    return findings


def _summary(findings: List[Finding]) -> dict:
    out = {
        "total": len(findings),
        "runtime": 0,
        "script": 0,
        "maintenance": 0,
        "test": 0,
        "other": 0,
        "merge": 0,
        "insert": 0,
        "update": 0,
        "delete": 0,
    }
    for f in findings:
        out[f.category] = out.get(f.category, 0) + 1
        out[f.op.lower()] = out.get(f.op.lower(), 0) + 1
    return out


def render_markdown(findings: List[Finding]) -> str:
    s = _summary(findings)
    lines: List[str] = []
    lines.append("# Phase 1C TOMEHUB_BOOKS DML Callsite Audit (2026-02-22)")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total DML callsites: `{s['total']}`")
    lines.append(f"- Runtime callsites: `{s['runtime']}`")
    lines.append(f"- Maintenance callsites: `{s['maintenance']}`")
    lines.append(f"- Script callsites: `{s['script']}`")
    lines.append(f"- Test callsites: `{s['test']}`")
    lines.append(f"- Other callsites: `{s['other']}`")
    lines.append("")
    lines.append("### By DML Type")
    lines.append("")
    lines.append(f"- `MERGE`: `{s['merge']}`")
    lines.append(f"- `INSERT`: `{s['insert']}`")
    lines.append(f"- `UPDATE`: `{s['update']}`")
    lines.append(f"- `DELETE`: `{s['delete']}`")
    lines.append("")
    lines.append("## Migration Guidance (Phase 1C Output)")
    lines.append("")
    lines.append("- Runtime write-paths must be moved off direct `TOMEHUB_BOOKS` DML before any view-based canonical cutover.")
    lines.append("- `INSTEAD OF` trigger remains fallback only; default path is backend write-path migration.")
    lines.append("- Maintenance/scripts should be reviewed and patched only if they are still used operationally.")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append("| Category | DML | File | Line | Recommended Action |")
    lines.append("|---|---|---|---:|---|")
    for f in findings:
        lines.append(
            f"| `{f.category}` | `{f.op}` | `{f.file_path}` | {f.line_no} | {f.recommended_action} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- This audit is regex-based and intended for migration routing prep.")
    lines.append("- Dynamic SQL builders should still be reviewed manually during Phase 1C implementation.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TOMEHUB_BOOKS DML callsites for Phase 1C")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Markdown report output path")
    parser.add_argument("--print", action="store_true", dest="do_print", help="Print report to stdout")
    args = parser.parse_args()

    findings = scan_repo()
    report = render_markdown(findings)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")

    print(f"[OK] Wrote report: {args.out}")
    print(f"[OK] Findings: {len(findings)}")
    if args.do_print:
        print()
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

