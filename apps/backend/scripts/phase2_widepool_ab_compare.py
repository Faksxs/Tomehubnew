#!/usr/bin/env python3
"""
Phase-2 A/B benchmark runner for wide candidate pool policy.

Compares:
- baseline (wide pool OFF)
- wide_pool (wide pool ON)

Uses existing phase0_benchmark runner and produces:
- mode-specific benchmark JSONs
- consolidated comparison report (json + md)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
from urllib import request as urllib_request


def wait_server_ready(base_url: str, timeout_sec: int = 180) -> bool:
    deadline = time.time() + timeout_sec
    url = f"{base_url.rstrip('/')}/metrics"
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(url, timeout=1.5) as resp:
                if int(resp.getcode()) == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def snapshot_reports(report_dir: Path) -> set[str]:
    return set(glob.glob(str(report_dir / "phase0_baseline_*.json")))


def find_new_report(before: set[str], report_dir: Path) -> Path:
    after = set(glob.glob(str(report_dir / "phase0_baseline_*.json")))
    created = sorted(after - before)
    if not created:
        raise RuntimeError("No new phase0_baseline report produced")
    return Path(created[-1])


def endpoint_map(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in report.get("endpoint_summaries", []):
        key = str(row.get("endpoint_key") or "").strip()
        if key:
            out[key] = row
    return out


def safe_get(d: Dict[str, Any], path: List[str], default=0.0):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def compare_reports(base_report: Dict[str, Any], cand_report: Dict[str, Any]) -> Dict[str, Any]:
    base_eps = endpoint_map(base_report)
    cand_eps = endpoint_map(cand_report)
    endpoints = sorted(set(base_eps.keys()) | set(cand_eps.keys()))

    compare: Dict[str, Any] = {}
    for ep in endpoints:
        b = base_eps.get(ep, {})
        c = cand_eps.get(ep, {})
        compare[ep] = {
            "success_rate": {
                "baseline": safe_get(b, ["success_rate"]),
                "wide_pool": safe_get(c, ["success_rate"]),
                "delta": safe_get(c, ["success_rate"]) - safe_get(b, ["success_rate"]),
            },
            "timeout_rate": {
                "baseline": safe_get(b, ["timeout_rate"]),
                "wide_pool": safe_get(c, ["timeout_rate"]),
                "delta": safe_get(c, ["timeout_rate"]) - safe_get(b, ["timeout_rate"]),
            },
            "latency_p50_ms": {
                "baseline": safe_get(b, ["latency_ms", "p50"]),
                "wide_pool": safe_get(c, ["latency_ms", "p50"]),
                "delta": safe_get(c, ["latency_ms", "p50"]) - safe_get(b, ["latency_ms", "p50"]),
            },
            "latency_p95_ms": {
                "baseline": safe_get(b, ["latency_ms", "p95"]),
                "wide_pool": safe_get(c, ["latency_ms", "p95"]),
                "delta": safe_get(c, ["latency_ms", "p95"]) - safe_get(b, ["latency_ms", "p95"]),
            },
            "mrr_mean": {
                "baseline": safe_get(b, ["quality", "mrr_mean"]),
                "wide_pool": safe_get(c, ["quality", "mrr_mean"]),
                "delta": safe_get(c, ["quality", "mrr_mean"]) - safe_get(b, ["quality", "mrr_mean"]),
            },
            "ndcg_at_10_mean": {
                "baseline": safe_get(b, ["quality", "ndcg_at_10_mean"]),
                "wide_pool": safe_get(c, ["quality", "ndcg_at_10_mean"]),
                "delta": safe_get(c, ["quality", "ndcg_at_10_mean"]) - safe_get(b, ["quality", "ndcg_at_10_mean"]),
            },
        }

    agg_eps = [ep for ep in ("search", "smart") if ep in compare]
    q_base = 0.0
    q_cand = 0.0
    if agg_eps:
        for ep in agg_eps:
            q_base += compare[ep]["mrr_mean"]["baseline"] + compare[ep]["ndcg_at_10_mean"]["baseline"]
            q_cand += compare[ep]["mrr_mean"]["wide_pool"] + compare[ep]["ndcg_at_10_mean"]["wide_pool"]
        q_base /= (2 * len(agg_eps))
        q_cand /= (2 * len(agg_eps))

    quality_delta_pct = ((q_cand - q_base) / q_base * 100.0) if q_base > 0 else 0.0

    lat_base = 0.0
    lat_cand = 0.0
    if agg_eps:
        for ep in agg_eps:
            lat_base += compare[ep]["latency_p95_ms"]["baseline"]
            lat_cand += compare[ep]["latency_p95_ms"]["wide_pool"]
        lat_base /= len(agg_eps)
        lat_cand /= len(agg_eps)
    latency_delta_pct = ((lat_cand - lat_base) / lat_base * 100.0) if lat_base > 0 else 0.0

    decision = {
        "quality_delta_pct": quality_delta_pct,
        "latency_delta_pct": latency_delta_pct,
        "quality_guardrail_pct": 0.0,
        "latency_ceiling_pct": 8.0,
        "quality_pass": quality_delta_pct >= 0.0,
        "latency_pass": latency_delta_pct <= 8.0,
    }
    decision["recommend_wide_pool"] = bool(decision["quality_pass"] and decision["latency_pass"])

    return {
        "endpoint_compare": compare,
        "aggregate": {
            "quality_proxy_baseline": q_base,
            "quality_proxy_wide_pool": q_cand,
            "latency_p95_baseline_ms": lat_base,
            "latency_p95_wide_pool_ms": lat_cand,
        },
        "decision": decision,
    }


def write_compare_reports(
    report_dir: Path,
    ts: str,
    compare: Dict[str, Any],
    baseline_json: Path,
    wide_pool_json: Path,
) -> Tuple[Path, Path]:
    json_path = report_dir / f"phase2_widepool_ab_compare_{ts}.json"
    md_path = report_dir / f"phase2_widepool_ab_compare_{ts}.md"

    payload = {
        "generated_at": datetime.now().isoformat(),
        "baseline_report_json": str(baseline_json),
        "wide_pool_report_json": str(wide_pool_json),
        **compare,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    d = compare["decision"]
    lines = [
        f"# Phase-2 Wide Pool A/B Compare Report ({ts})",
        "",
        "## Decision",
        f"- quality_delta_pct: {d['quality_delta_pct']:.2f}",
        f"- latency_delta_pct: {d['latency_delta_pct']:.2f}",
        f"- quality_pass (>= 0%): {d['quality_pass']}",
        f"- latency_pass (<= 8%): {d['latency_pass']}",
        f"- recommend_wide_pool: {d['recommend_wide_pool']}",
        "",
        "## Endpoint Deltas (wide_pool - baseline)",
    ]
    for ep, m in compare["endpoint_compare"].items():
        lines.append(f"### {ep}")
        lines.append(f"- success_rate delta: {m['success_rate']['delta']:.4f}")
        lines.append(f"- timeout_rate delta: {m['timeout_rate']['delta']:.4f}")
        lines.append(f"- latency_p50_ms delta: {m['latency_p50_ms']['delta']:.2f}")
        lines.append(f"- latency_p95_ms delta: {m['latency_p95_ms']['delta']:.2f}")
        lines.append(f"- mrr_mean delta: {m['mrr_mean']['delta']:.4f}")
        lines.append(f"- ndcg_at_10_mean delta: {m['ndcg_at_10_mean']['delta']:.4f}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def run_mode(
    mode: str,
    py_exec: str,
    backend_dir: Path,
    report_dir: Path,
    uid: str,
    base_url: str,
    timeout_sec: float,
    max_queries: int,
    chat_sample_size: int,
    graph_probe_size: int,
    disable_chat: bool,
    disable_graph_probe: bool,
    wide_direct: int,
    wide_default: int,
    wide_semantic: int,
    enable_bm25plus: bool,
    enable_rerank: bool,
) -> Path:
    env = os.environ.copy()
    env["RETRIEVAL_FUSION_MODE"] = "concat"
    env["SEARCH_WIDE_POOL_ENABLED"] = "true" if mode == "wide_pool" else "false"
    env["SEARCH_WIDE_POOL_LIMIT_DIRECT"] = str(wide_direct)
    env["SEARCH_WIDE_POOL_LIMIT_DEFAULT"] = str(wide_default)
    env["SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT"] = str(wide_semantic)
    env["SEARCH_BM25PLUS_ENABLED"] = "true" if (mode == "wide_pool" and enable_bm25plus) else "false"
    env["SEARCH_RERANK_ENABLED"] = "true" if (mode == "wide_pool" and enable_rerank) else "false"

    server = subprocess.Popen(
        [py_exec, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "5001"],
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_server_ready(base_url=base_url, timeout_sec=180):
            raise RuntimeError(f"Server failed to start for mode={mode}")

        before = snapshot_reports(report_dir)
        cmd = [
            py_exec,
            "scripts/phase0_benchmark.py",
            "--uid",
            uid,
            "--base-url",
            base_url,
            "--timeout-sec",
            str(timeout_sec),
            "--max-queries",
            str(max_queries),
            "--chat-sample-size",
            str(chat_sample_size),
            "--graph-probe-size",
            str(graph_probe_size),
        ]
        if disable_chat:
            cmd.append("--disable-chat")
        if disable_graph_probe:
            cmd.append("--disable-graph-probe")

        subprocess.run(cmd, cwd=str(backend_dir), env=env, check=True)
        report_path = find_new_report(before, report_dir)
        return report_path
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase-2 wide pool A/B benchmark")
    parser.add_argument("--uid", required=True, help="Firebase UID to benchmark against")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001", help="Benchmark base URL")
    parser.add_argument("--timeout-sec", type=float, default=8.0)
    parser.add_argument("--max-queries", type=int, default=40)
    parser.add_argument("--chat-sample-size", type=int, default=20)
    parser.add_argument("--graph-probe-size", type=int, default=20)
    parser.add_argument("--disable-chat", action="store_true")
    parser.add_argument("--disable-graph-probe", action="store_true")
    parser.add_argument("--wide-limit-direct", type=int, default=900)
    parser.add_argument("--wide-limit-default", type=int, default=480)
    parser.add_argument("--wide-semantic-fetch-limit", type=int, default=72)
    parser.add_argument("--enable-bm25plus", action="store_true", help="Also enable BM25Plus in candidate run")
    parser.add_argument("--enable-rerank", action="store_true", help="Also enable reranker in candidate run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parents[1]
    report_dir = repo_root / "documentation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    py_exec = sys.executable
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("[Phase2-AB] Running baseline...")
    baseline_json = run_mode(
        mode="baseline",
        py_exec=py_exec,
        backend_dir=backend_dir,
        report_dir=report_dir,
        uid=args.uid,
        base_url=args.base_url,
        timeout_sec=args.timeout_sec,
        max_queries=args.max_queries,
        chat_sample_size=args.chat_sample_size,
        graph_probe_size=args.graph_probe_size,
        disable_chat=args.disable_chat,
        disable_graph_probe=args.disable_graph_probe,
        wide_direct=args.wide_limit_direct,
        wide_default=args.wide_limit_default,
        wide_semantic=args.wide_semantic_fetch_limit,
        enable_bm25plus=args.enable_bm25plus,
        enable_rerank=args.enable_rerank,
    )

    baseline_copy = report_dir / f"phase2_widepool_baseline_{ts}.json"
    baseline_copy.write_text(baseline_json.read_text(encoding="utf-8"), encoding="utf-8")

    print("[Phase2-AB] Running candidate (wide_pool)...")
    wide_json = run_mode(
        mode="wide_pool",
        py_exec=py_exec,
        backend_dir=backend_dir,
        report_dir=report_dir,
        uid=args.uid,
        base_url=args.base_url,
        timeout_sec=args.timeout_sec,
        max_queries=args.max_queries,
        chat_sample_size=args.chat_sample_size,
        graph_probe_size=args.graph_probe_size,
        disable_chat=args.disable_chat,
        disable_graph_probe=args.disable_graph_probe,
        wide_direct=args.wide_limit_direct,
        wide_default=args.wide_limit_default,
        wide_semantic=args.wide_semantic_fetch_limit,
        enable_bm25plus=args.enable_bm25plus,
        enable_rerank=args.enable_rerank,
    )

    wide_copy = report_dir / f"phase2_widepool_candidate_{ts}.json"
    wide_copy.write_text(wide_json.read_text(encoding="utf-8"), encoding="utf-8")

    compare = compare_reports(
        json.loads(baseline_copy.read_text(encoding="utf-8")),
        json.loads(wide_copy.read_text(encoding="utf-8")),
    )
    out_json, out_md = write_compare_reports(report_dir, ts, compare, baseline_copy, wide_copy)

    print(f"[Phase2-AB] baseline:  {baseline_copy}")
    print(f"[Phase2-AB] candidate: {wide_copy}")
    print(f"[Phase2-AB] compare:   {out_json}")
    print(f"[Phase2-AB] summary:   {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
