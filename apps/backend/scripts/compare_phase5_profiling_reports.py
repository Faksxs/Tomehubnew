"""
Compare two Phase 5 profiling markdown reports and print timing/index deltas.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TIMING_RE = re.compile(
    r"- `(?P<name>[^`]+)`: rows=(?P<rows>\d+), runs=(?P<runs>\d+), "
    r"p50=(?P<p50>[0-9.]+)ms, p95=(?P<p95>[0-9.]+)ms, max=(?P<max>[0-9.]+)ms"
)
IDX_RE = re.compile(
    r"- `(?P<target>[^`]+)` covered: `(?P<covered>YES|NO)` \| indexes: (?P<idxs>.*)$"
)


def _parse(path: Path) -> tuple[dict, dict]:
    timings = {}
    coverage = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = TIMING_RE.match(line.strip())
        if m:
            timings[m.group("name")] = {
                "rows": int(m.group("rows")),
                "runs": int(m.group("runs")),
                "p50": float(m.group("p50")),
                "p95": float(m.group("p95")),
                "max": float(m.group("max")),
            }
            continue
        m = IDX_RE.match(line.strip())
        if m:
            coverage[m.group("target")] = {
                "covered": m.group("covered"),
                "indexes": m.group("idxs").strip(),
            }
    return timings, coverage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("before")
    ap.add_argument("after")
    args = ap.parse_args()

    before = Path(args.before)
    after = Path(args.after)
    t_before, c_before = _parse(before)
    t_after, c_after = _parse(after)

    print(f"[COMPARE] before={before}")
    print(f"[COMPARE] after={after}")

    print("\n[Index Coverage]")
    for target in sorted(set(c_before) | set(c_after)):
        b = c_before.get(target)
        a = c_after.get(target)
        if not b or not a:
            print(f"- {target}: missing in one report")
            continue
        changed = (b["covered"] != a["covered"]) or (b["indexes"] != a["indexes"])
        marker = "*" if changed else "="
        print(f"{marker} {target}: {b['covered']} -> {a['covered']} | {b['indexes']} -> {a['indexes']}")

    print("\n[Timings]")
    for name in sorted(set(t_before) | set(t_after)):
        b = t_before.get(name)
        a = t_after.get(name)
        if not b or not a:
            print(f"- {name}: missing in one report")
            continue
        dp50 = round(a["p50"] - b["p50"], 2)
        dp95 = round(a["p95"] - b["p95"], 2)
        dmax = round(a["max"] - b["max"], 2)
        print(
            f"- {name}: p50 {b['p50']} -> {a['p50']} ({dp50:+}ms), "
            f"p95 {b['p95']} -> {a['p95']} ({dp95:+}ms), max {b['max']} -> {a['max']} ({dmax:+}ms)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

