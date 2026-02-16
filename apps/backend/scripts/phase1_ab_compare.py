#!/usr/bin/env python3
"""
Phase-1 A/B benchmark runner for retrieval fusion modes.

Runs the existing phase0_benchmark in two modes:
- concat
- rrf

Produces:
- mode-specific benchmark reports (renamed)
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
    out = {}
    for s in report.get("endpoint_summaries", []):
        out[s["endpoint_key"]] = s
    return out


def safe_get(d: Dict[str, Any], path: List[str], default=0.0):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def compare_reports(concat_report: Dict[str, Any], rrf_report: Dict[str, Any]) -> Dict[str, Any]:
    concat_eps = endpoint_map(concat_report)
    rrf_eps = endpoint_map(rrf_report)
    endpoints = sorted(set(concat_eps.keys()) | set(rrf_eps.keys()))

    compare = {}
    for ep in endpoints:
        c = concat_eps.get(ep, {})
        r = rrf_eps.get(ep, {})
        compare[ep] = {
            "success_rate": {
                "concat": safe_get(c, ["success_rate"]),
                "rrf": safe_get(r, ["success_rate"]),
                "delta": safe_get(r, ["success_rate"]) - safe_get(c, ["success_rate"]),
            },
            "timeout_rate": {
                "concat": safe_get(c, ["timeout_rate"]),
                "rrf": safe_get(r, ["timeout_rate"]),
                "delta": safe_get(r, ["timeout_rate"]) - safe_get(c, ["timeout_rate"]),
            },
            "latency_p50_ms": {
                "concat": safe_get(c, ["latency_ms", "p50"]),
                "rrf": safe_get(r, ["latency_ms", "p50"]),
                "delta": safe_get(r, ["latency_ms", "p50"]) - safe_get(c, ["latency_ms", "p50"]),
            },
            "latency_p95_ms": {
                "concat": safe_get(c, ["latency_ms", "p95"]),
                "rrf": safe_get(r, ["latency_ms", "p95"]),
                "delta": safe_get(r, ["latency_ms", "p95"]) - safe_get(c, ["latency_ms", "p95"]),
            },
            "mrr_mean": {
                "concat": safe_get(c, ["quality", "mrr_mean"]),
                "rrf": safe_get(r, ["quality", "mrr_mean"]),
                "delta": safe_get(r, ["quality", "mrr_mean"]) - safe_get(c, ["quality", "mrr_mean"]),
            },
            "ndcg_at_10_mean": {
                "concat": safe_get(c, ["quality", "ndcg_at_10_mean"]),
                "rrf": safe_get(r, ["quality", "ndcg_at_10_mean"]),
                "delta": safe_get(r, ["quality", "ndcg_at_10_mean"]) - safe_get(c, ["quality", "ndcg_at_10_mean"]),
            },
            "explorer_avg_attempts": {
                "concat": safe_get(c, ["explorer", "avg_attempts"]),
                "rrf": safe_get(r, ["explorer", "avg_attempts"]),
                "delta": safe_get(r, ["explorer", "avg_attempts"]) - safe_get(c, ["explorer", "avg_attempts"]),
            },
            "explorer_fallback_timeout_rate": {
                "concat": safe_get(c, ["explorer", "fallback_timeout_rate"]),
                "rrf": safe_get(r, ["explorer", "fallback_timeout_rate"]),
                "delta": safe_get(r, ["explorer", "fallback_timeout_rate"]) - safe_get(c, ["explorer", "fallback_timeout_rate"]),
            },
        }

    # Aggregate quality over search+smart only (chat has no stable relevance target)
    agg_eps = [ep for ep in ("search", "smart") if ep in compare]
    q_concat = 0.0
    q_rrf = 0.0
    if agg_eps:
        for ep in agg_eps:
            q_concat += compare[ep]["mrr_mean"]["concat"] + compare[ep]["ndcg_at_10_mean"]["concat"]
            q_rrf += compare[ep]["mrr_mean"]["rrf"] + compare[ep]["ndcg_at_10_mean"]["rrf"]
        q_concat /= (2 * len(agg_eps))
        q_rrf /= (2 * len(agg_eps))

    quality_gain_pct = ((q_rrf - q_concat) / q_concat * 100.0) if q_concat > 0 else 0.0

    # Aggregate latency p95 over search+smart
    lat_concat = 0.0
    lat_rrf = 0.0
    if agg_eps:
        for ep in agg_eps:
            lat_concat += compare[ep]["latency_p95_ms"]["concat"]
            lat_rrf += compare[ep]["latency_p95_ms"]["rrf"]
        lat_concat /= len(agg_eps)
        lat_rrf /= len(agg_eps)
    latency_change_pct = ((lat_rrf - lat_concat) / lat_concat * 100.0) if lat_concat > 0 else 0.0

    decision = {
        "quality_gain_pct": quality_gain_pct,
        "latency_change_pct": latency_change_pct,
        "quality_target_pct": 5.0,
        "latency_ceiling_pct": 10.0,
        "quality_pass": quality_gain_pct >= 5.0,
        "latency_pass": latency_change_pct <= 10.0,
    }
    decision["recommend_rrf"] = bool(decision["quality_pass"] and decision["latency_pass"])

    return {
        "endpoint_compare": compare,
        "aggregate": {
            "quality_proxy_concat": q_concat,
            "quality_proxy_rrf": q_rrf,
            "latency_p95_concat_ms": lat_concat,
            "latency_p95_rrf_ms": lat_rrf,
        },
        "decision": decision,
    }


def write_compare_reports(
    report_dir: Path,
    ts: str,
    compare: Dict[str, Any],
    concat_json: Path,
    rrf_json: Path,
) -> Tuple[Path, Path]:
    json_path = report_dir / f"phase1_ab_compare_{ts}.json"
    md_path = report_dir / f"phase1_ab_compare_{ts}.md"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "concat_report_json": str(concat_json),
        "rrf_report_json": str(rrf_json),
        **compare,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    d = compare["decision"]
    lines = [
        f"# Phase-1 A/B Compare Report ({ts})",
        "",
        "## Decision",
        f"- quality_gain_pct: {d['quality_gain_pct']:.2f}",
        f"- latency_change_pct: {d['latency_change_pct']:.2f}",
        f"- quality_pass (>=5%): {d['quality_pass']}",
        f"- latency_pass (<=10%): {d['latency_pass']}",
        f"- recommend_rrf: {d['recommend_rrf']}",
        "",
        "## Endpoint Deltas (rrf - concat)",
    ]
    for ep, m in compare["endpoint_compare"].items():
        lines.append(f"### {ep}")
        lines.append(f"- success_rate delta: {m['success_rate']['delta']:.4f}")
        lines.append(f"- timeout_rate delta: {m['timeout_rate']['delta']:.4f}")
        lines.append(f"- latency_p50_ms delta: {m['latency_p50_ms']['delta']:.2f}")
        lines.append(f"- latency_p95_ms delta: {m['latency_p95_ms']['delta']:.2f}")
        lines.append(f"- mrr_mean delta: {m['mrr_mean']['delta']:.4f}")
        lines.append(f"- ndcg_at_10_mean delta: {m['ndcg_at_10_mean']['delta']:.4f}")
        lines.append(f"- explorer_avg_attempts delta: {m['explorer_avg_attempts']['delta']:.4f}")
        lines.append(f"- explorer_fallback_timeout_rate delta: {m['explorer_fallback_timeout_rate']['delta']:.4f}")
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
    dataset: str,
    timeout_sec: float,
    max_queries: int,
    chat_sample_size: int,
    graph_probe_size: int,
    disable_chat: bool,
    disable_graph_probe: bool,
) -> Path:
    env = os.environ.copy()
    env["RETRIEVAL_FUSION_MODE"] = mode

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
        if dataset:
            cmd.extend(["--dataset", dataset])
        if disable_chat:
            cmd.append("--disable-chat")
        if disable_graph_probe:
            cmd.append("--disable-graph-probe")

        res = subprocess.run(cmd, cwd=str(backend_dir), env=env, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"Benchmark failed for mode={mode} returncode={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}"
            )
        produced = find_new_report(before, report_dir)
        mode_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = report_dir / f"phase1_ab_{mode}_{mode_ts}.json"
        produced.rename(target)

        produced_md = produced.with_suffix(".md")
        if produced_md.exists():
            produced_md.rename(report_dir / f"phase1_ab_{mode}_{mode_ts}.md")
        return target
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()


def main():
    parser = argparse.ArgumentParser(description="Run Phase-1 A/B comparison for concat vs rrf.")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--dataset", default="")
    parser.add_argument("--timeout-sec", type=float, default=25.0)
    parser.add_argument("--max-queries", type=int, default=24)
    parser.add_argument("--chat-sample-size", type=int, default=12)
    parser.add_argument("--graph-probe-size", type=int, default=12)
    parser.add_argument("--disable-chat", action="store_true")
    parser.add_argument("--disable-graph-probe", action="store_true")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parents[1]
    report_dir = repo_root / "documentation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    py_exec = sys.executable

    concat_json = run_mode(
        mode="concat",
        py_exec=py_exec,
        backend_dir=backend_dir,
        report_dir=report_dir,
        uid=args.uid,
        base_url=args.base_url,
        dataset=args.dataset,
        timeout_sec=args.timeout_sec,
        max_queries=args.max_queries,
        chat_sample_size=args.chat_sample_size,
        graph_probe_size=args.graph_probe_size,
        disable_chat=args.disable_chat,
        disable_graph_probe=args.disable_graph_probe,
    )

    rrf_json = run_mode(
        mode="rrf",
        py_exec=py_exec,
        backend_dir=backend_dir,
        report_dir=report_dir,
        uid=args.uid,
        base_url=args.base_url,
        dataset=args.dataset,
        timeout_sec=args.timeout_sec,
        max_queries=args.max_queries,
        chat_sample_size=args.chat_sample_size,
        graph_probe_size=args.graph_probe_size,
        disable_chat=args.disable_chat,
        disable_graph_probe=args.disable_graph_probe,
    )

    concat_report = json.loads(concat_json.read_text(encoding="utf-8"))
    rrf_report = json.loads(rrf_json.read_text(encoding="utf-8"))
    compare = compare_reports(concat_report, rrf_report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cmp_json, cmp_md = write_compare_reports(report_dir, ts, compare, concat_json, rrf_json)
    print(f"[OK] concat report: {concat_json}")
    print(f"[OK] rrf report:    {rrf_json}")
    print(f"[OK] compare json:  {cmp_json}")
    print(f"[OK] compare md:    {cmp_md}")


if __name__ == "__main__":
    main()

