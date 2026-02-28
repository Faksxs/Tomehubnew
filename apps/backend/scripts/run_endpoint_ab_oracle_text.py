#!/usr/bin/env python3
"""
Endpoint-level A/B benchmark for /api/search and /api/smart-search.

Compares:
- Legacy exact path (Oracle Text OFF)
- Oracle Text exact path (Oracle Text ON)

Starts temporary uvicorn servers for each mode, runs the same query set,
and writes JSON + Markdown reports under documentation/reports.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(base_url: str, timeout_s: float = 45.0) -> bool:
    deadline = time.time() + timeout_s
    url = f"{base_url}/docs"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as resp:
                if int(resp.getcode()) >= 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _http_post_json(url: str, payload: Dict[str, Any], timeout_s: float) -> Tuple[int, Dict[str, Any], str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            return int(resp.getcode()), parsed, ""
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return int(e.code), parsed, f"http_error:{e.code}"
    except Exception as e:
        return 0, {}, str(e)


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if p <= 0:
        return vals[0]
    if p >= 100:
        return vals[-1]
    rank = (len(vals) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(vals) - 1)
    if low == high:
        return vals[low]
    weight = rank - low
    return vals[low] * (1 - weight) + vals[high] * weight


def _spawn_server(port: int, env_overrides: Dict[str, str]) -> subprocess.Popen:
    env = os.environ.copy()
    env.update(env_overrides)
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--app-dir",
        str(BACKEND_DIR),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    out_log = REPO_ROOT / "tmp_endpoint_ab_stdout.log"
    err_log = REPO_ROOT / "tmp_endpoint_ab_stderr.log"
    out_f = open(out_log, "w", encoding="utf-8", errors="replace")
    err_f = open(err_log, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=out_f, stderr=err_f)
    proc._out_f = out_f  # type: ignore[attr-defined]
    proc._err_f = err_f  # type: ignore[attr-defined]
    proc._out_log = out_log  # type: ignore[attr-defined]
    proc._err_log = err_log  # type: ignore[attr-defined]
    return proc


def _stop_server(proc: subprocess.Popen) -> Tuple[str, str]:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
            proc.wait(timeout=8)
    try:
        proc._out_f.close()  # type: ignore[attr-defined]
        proc._err_f.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    stdout_tail = ""
    stderr_tail = ""
    try:
        stdout_tail = "\n".join(Path(proc._out_log).read_text(encoding="utf-8", errors="replace").splitlines()[-50:])  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        stderr_tail = "\n".join(Path(proc._err_log).read_text(encoding="utf-8", errors="replace").splitlines()[-80:])  # type: ignore[attr-defined]
    except Exception:
        pass
    return stdout_tail, stderr_tail


def _result_count(endpoint: str, body: Dict[str, Any]) -> int:
    if endpoint == "/api/search":
        return len(body.get("sources") or [])
    return int(body.get("total") or len(body.get("results") or []))


def _first_title(endpoint: str, body: Dict[str, Any]) -> str:
    if endpoint == "/api/search":
        sources = body.get("sources") or []
        return str((sources[0] or {}).get("title") or "") if sources else ""
    results = body.get("results") or []
    return str((results[0] or {}).get("title") or "") if results else ""


def _run_mode(
    mode_name: str,
    uid: str,
    queries: List[str],
    book_id: str | None,
    timeout_s: float,
    oracle_enabled: bool,
    oracle_single_token: bool,
    oracle_min_rows: int,
) -> Dict[str, Any]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    env_overrides = {
        "ENVIRONMENT": "development",
        "DEV_UNSAFE_AUTH_BYPASS": "true",
        "GOOGLE_APPLICATION_CREDENTIALS": "__missing__.json",
        "SEARCH_EXACT_ORACLE_TEXT_ENABLED": "true" if oracle_enabled else "false",
        "SEARCH_EXACT_ORACLE_TEXT_SINGLE_TOKEN_ENABLED": "true" if oracle_single_token else "false",
        "SEARCH_EXACT_ORACLE_TEXT_MIN_ROWS": str(oracle_min_rows),
    }

    endpoints = ["/api/search", "/api/smart-search"]
    rows: List[Dict[str, Any]] = []
    proc = _spawn_server(port, env_overrides)
    stdout_tail = ""
    stderr_tail = ""
    try:
        if not _wait_ready(base_url):
            raise RuntimeError(f"Server not ready for mode={mode_name}")

        for endpoint in endpoints:
            for q in queries:
                payload: Dict[str, Any] = {
                    "question": q,
                    "firebase_uid": uid,
                    "limit": 20,
                    "offset": 0,
                }
                if book_id:
                    payload["book_id"] = book_id
                t0 = time.perf_counter()
                status, body, err = _http_post_json(f"{base_url}{endpoint}", payload, timeout_s)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                rows.append(
                    {
                        "mode": mode_name,
                        "endpoint": endpoint,
                        "query": q,
                        "status": status,
                        "ok": status == 200 and not err,
                        "error": err,
                        "latency_ms": latency_ms,
                        "result_count": _result_count(endpoint, body),
                        "first_title": _first_title(endpoint, body),
                    }
                )
    finally:
        stdout_tail, stderr_tail = _stop_server(proc)

    endpoint_summaries: List[Dict[str, Any]] = []
    for endpoint in endpoints:
        erows = [r for r in rows if r["endpoint"] == endpoint]
        lats = [float(r["latency_ms"]) for r in erows]
        counts = [int(r["result_count"]) for r in erows]
        success = sum(1 for r in erows if r["ok"])
        endpoint_summaries.append(
            {
                "endpoint": endpoint,
                "query_count": len(erows),
                "success_rate": (success / len(erows)) if erows else 0.0,
                "latency_ms": {
                    "p50": _percentile(lats, 50),
                    "p95": _percentile(lats, 95),
                    "mean": (sum(lats) / len(lats)) if lats else 0.0,
                },
                "result_count": {
                    "mean": (sum(counts) / len(counts)) if counts else 0.0,
                },
            }
        )

    return {
        "mode": mode_name,
        "oracle_enabled": oracle_enabled,
        "oracle_single_token": oracle_single_token,
        "oracle_min_rows": oracle_min_rows,
        "rows": rows,
        "endpoint_summaries": endpoint_summaries,
        "server_stderr_tail": stderr_tail,
        "server_stdout_tail": stdout_tail,
    }


def _build_diff(legacy: Dict[str, Any], oracle: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for endpoint in ["/api/search", "/api/smart-search"]:
        lsum = next((x for x in legacy["endpoint_summaries"] if x["endpoint"] == endpoint), None)
        osum = next((x for x in oracle["endpoint_summaries"] if x["endpoint"] == endpoint), None)
        if not lsum or not osum:
            continue
        l_p95 = float(lsum["latency_ms"]["p95"])
        o_p95 = float(osum["latency_ms"]["p95"])
        l_mean_count = float(lsum["result_count"]["mean"])
        o_mean_count = float(osum["result_count"]["mean"])
        latency_delta_pct = ((o_p95 - l_p95) / l_p95 * 100.0) if l_p95 > 0 else 0.0
        count_delta_pct = ((o_mean_count - l_mean_count) / l_mean_count * 100.0) if l_mean_count > 0 else 0.0
        out.append(
            {
                "endpoint": endpoint,
                "legacy_p95_ms": l_p95,
                "oracle_p95_ms": o_p95,
                "p95_delta_pct_oracle_vs_legacy": latency_delta_pct,
                "legacy_mean_result_count": l_mean_count,
                "oracle_mean_result_count": o_mean_count,
                "result_count_delta_pct_oracle_vs_legacy": count_delta_pct,
            }
        )
    return out


def _write_reports(report: Dict[str, Any]) -> Tuple[Path, Path]:
    out_dir = REPO_ROOT / "documentation" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = out_dir / f"ENDPOINT_AB_SEARCH_SMART_ORACLE_TEXT_{ts}.json"
    md_path = out_dir / f"ENDPOINT_AB_SEARCH_SMART_ORACLE_TEXT_{ts}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append(f"# Endpoint A/B Report ({ts})")
    lines.append("")
    lines.append("## Config")
    lines.append(f"- uid: `{report['config']['uid']}`")
    lines.append(f"- book_id: `{report['config']['book_id']}`")
    lines.append(f"- queries: `{', '.join(report['config']['queries'])}`")
    lines.append(f"- timeout_sec: `{report['config']['timeout_sec']}`")
    lines.append("")
    lines.append("## Summary Diff (Oracle vs Legacy)")
    for d in report["diff"]:
        lines.append(
            f"- `{d['endpoint']}`: p95 `{d['legacy_p95_ms']:.1f} -> {d['oracle_p95_ms']:.1f}` ms "
            f"({d['p95_delta_pct_oracle_vs_legacy']:+.1f}%), "
            f"mean_result_count `{d['legacy_mean_result_count']:.2f} -> {d['oracle_mean_result_count']:.2f}` "
            f"({d['result_count_delta_pct_oracle_vs_legacy']:+.1f}%)"
        )
    lines.append("")
    lines.append("## Per-Mode Endpoint Metrics")
    for mode in [report["legacy"], report["oracle"]]:
        lines.append(f"### {mode['mode']}")
        lines.append(
            f"- oracle_enabled={mode['oracle_enabled']}, "
            f"single_token={mode['oracle_single_token']}, min_rows={mode['oracle_min_rows']}"
        )
        for s in mode["endpoint_summaries"]:
            lines.append(
                f"- {s['endpoint']}: success_rate={s['success_rate']:.2f}, "
                f"p50/p95={s['latency_ms']['p50']:.1f}/{s['latency_ms']['p95']:.1f} ms, "
                f"mean_result_count={s['result_count']['mean']:.2f}"
            )
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Endpoint-level A/B benchmark for /api/search and /api/smart-search")
    parser.add_argument("--uid", required=True, help="firebase_uid")
    parser.add_argument("--book-id", default="", help="optional book_id scope")
    parser.add_argument(
        "--queries",
        default="ahlak,vicdan,sorumluluk,irade,erdem,ozgurluk,adalet",
        help="comma-separated query set",
    )
    parser.add_argument("--timeout-sec", type=float, default=90.0)
    parser.add_argument("--oracle-single-token", action="store_true", help="enable Oracle Text for single-token queries")
    parser.add_argument("--oracle-min-rows", type=int, default=40)
    args = parser.parse_args()

    queries = [q.strip() for q in str(args.queries).split(",") if q.strip()]
    if not queries:
        raise RuntimeError("No queries provided")

    legacy = _run_mode(
        mode_name="legacy",
        uid=args.uid,
        queries=queries,
        book_id=args.book_id or None,
        timeout_s=float(args.timeout_sec),
        oracle_enabled=False,
        oracle_single_token=False,
        oracle_min_rows=int(args.oracle_min_rows),
    )
    oracle = _run_mode(
        mode_name="oracle",
        uid=args.uid,
        queries=queries,
        book_id=args.book_id or None,
        timeout_s=float(args.timeout_sec),
        oracle_enabled=True,
        oracle_single_token=bool(args.oracle_single_token),
        oracle_min_rows=int(args.oracle_min_rows),
    )

    report = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "uid": args.uid,
            "book_id": args.book_id or None,
            "queries": queries,
            "timeout_sec": float(args.timeout_sec),
            "oracle_single_token": bool(args.oracle_single_token),
            "oracle_min_rows": int(args.oracle_min_rows),
        },
        "legacy": legacy,
        "oracle": oracle,
        "diff": _build_diff(legacy, oracle),
    }
    json_path, md_path = _write_reports(report)
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] MD report:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

