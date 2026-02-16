#!/usr/bin/env python3
"""
Phase-3 quick A/B for router modes.

Short-run comparison to avoid long benchmark cycles.
Focus: /api/smart-search only (router core path).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib import request as urllib_request
from urllib import error as urllib_error


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if p <= 0:
        return vals[0]
    if p >= 100:
        return vals[-1]
    rank = (len(vals) - 1) * (p / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return vals[lo]
    w = rank - lo
    return vals[lo] * (1 - w) + vals[hi] * w


def wait_server_ready(base_url: str, timeout_sec: int = 120) -> bool:
    deadline = time.time() + timeout_sec
    url = f"{base_url.rstrip('/')}/metrics"
    while time.time() < deadline:
        try:
            with urllib_request.urlopen(url, timeout=1.5) as resp:
                if int(resp.getcode()) == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def post_json(base_url: str, endpoint: str, payload: Dict[str, Any], timeout_sec: float) -> Tuple[int, Dict[str, Any], str]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    req = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.getcode()), json.loads(body), ""
    except urllib_error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {}
        return int(e.code), parsed, f"http_error:{e.code}"
    except Exception as e:
        return 0, {}, str(e)


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def is_relevant(doc: str, expected_terms: List[str]) -> bool:
    if not expected_terms:
        return False
    nd = _norm(doc)
    return any(_norm(t) in nd for t in expected_terms)


def mrr(binary_rels: List[int]) -> float:
    for i, rel in enumerate(binary_rels, 1):
        if rel:
            return 1.0 / i
    return 0.0


def dcg_at_k(binary_rels: List[int], k: int = 10) -> float:
    score = 0.0
    for i, rel in enumerate(binary_rels[:k], 1):
        if rel:
            score += 1.0 / math.log2(i + 1)
    return score


def ndcg_at_k(binary_rels: List[int], k: int = 10) -> float:
    if not binary_rels:
        return 0.0
    dcg = dcg_at_k(binary_rels, k)
    idcg = dcg_at_k(sorted(binary_rels, reverse=True), k)
    return (dcg / idcg) if idcg > 0 else 0.0


def load_queries(dataset_path: Path, max_queries: int) -> List[Dict[str, Any]]:
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    if max_queries > 0:
        return raw[:max_queries]
    return raw


def run_mode(
    mode: str,
    py_exec: str,
    backend_dir: Path,
    base_url: str,
    port: int,
    uid: str,
    queries: List[Dict[str, Any]],
    request_timeout_sec: float,
) -> Dict[str, Any]:
    env = os.environ.copy()
    env["SEARCH_ROUTER_MODE"] = mode
    env["RETRIEVAL_FUSION_MODE"] = "concat"
    env["CACHE_ENABLED"] = "false"

    mode_base_url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [py_exec, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(backend_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.4)
        if server.poll() is not None:
            raise RuntimeError(f"Server exited early for mode={mode} port={port}")
        if not wait_server_ready(mode_base_url, timeout_sec=150):
            raise RuntimeError(f"Server failed to start for mode={mode}")

        rows: List[Dict[str, Any]] = []
        for q in queries:
            payload = {
                "question": q.get("query", ""),
                "firebase_uid": uid,
                "limit": 20,
                "offset": 0,
            }
            t0 = time.perf_counter()
            status, body, err = post_json(mode_base_url, "/api/smart-search", payload, request_timeout_sec)
            lat_ms = (time.perf_counter() - t0) * 1000.0

            docs = []
            for r in body.get("results") or []:
                docs.append(f"{r.get('title', '')} {r.get('content_chunk', '')}")
            expected_terms = q.get("expected_terms") or []
            rels = [1 if is_relevant(d, expected_terms) else 0 for d in docs]

            meta = body.get("metadata") or {}
            rows.append(
                {
                    "qid": q.get("id"),
                    "query": q.get("query"),
                    "status": status,
                    "ok": status == 200,
                    "error": err,
                    "latency_ms": lat_ms,
                    "result_count": int(body.get("total") or len(body.get("results") or [])),
                    "mrr": mrr(rels) if expected_terms else None,
                    "ndcg_at_10": ndcg_at_k(rels, 10) if expected_terms else None,
                    "router_mode": meta.get("router_mode"),
                    "router_reason": meta.get("router_reason"),
                    "selected_buckets": meta.get("selected_buckets"),
                    "executed_strategies": meta.get("executed_strategies"),
                }
            )

        latencies = [r["latency_ms"] for r in rows]
        quality_rows = [r for r in rows if r.get("mrr") is not None and r.get("ndcg_at_10") is not None]
        summary = {
            "mode": mode,
            "query_count": len(rows),
            "success_rate": (sum(1 for r in rows if r["ok"]) / len(rows)) if rows else 0.0,
            "latency_ms": {
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
                "mean": statistics.fmean(latencies) if latencies else 0.0,
            },
            "quality": {
                "mrr_mean": (statistics.fmean([float(r["mrr"]) for r in quality_rows]) if quality_rows else 0.0),
                "ndcg_at_10_mean": (statistics.fmean([float(r["ndcg_at_10"]) for r in quality_rows]) if quality_rows else 0.0),
            },
            "rows": rows,
        }
        return summary
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()


def compare(static_sum: Dict[str, Any], rule_sum: Dict[str, Any]) -> Dict[str, Any]:
    q_static = (static_sum["quality"]["mrr_mean"] + static_sum["quality"]["ndcg_at_10_mean"]) / 2.0
    q_rule = (rule_sum["quality"]["mrr_mean"] + rule_sum["quality"]["ndcg_at_10_mean"]) / 2.0
    quality_change_pct = ((q_rule - q_static) / q_static * 100.0) if q_static > 0 else 0.0

    p95_static = float(static_sum["latency_ms"]["p95"])
    p95_rule = float(rule_sum["latency_ms"]["p95"])
    latency_gain_pct = ((p95_static - p95_rule) / p95_static * 100.0) if p95_static > 0 else 0.0

    decision = {
        "quality_change_pct": quality_change_pct,
        "latency_gain_pct": latency_gain_pct,
        "quality_guardrail_pct": -2.0,
        "latency_target_gain_pct": 2.0,
    }
    decision["quality_pass"] = quality_change_pct >= decision["quality_guardrail_pct"]
    decision["latency_pass"] = latency_gain_pct >= decision["latency_target_gain_pct"]
    decision["recommend_rule_based"] = bool(decision["quality_pass"] and decision["latency_pass"])
    return {
        "static": static_sum,
        "rule_based": rule_sum,
        "decision": decision,
    }


def write_reports(report_dir: Path, result: Dict[str, Any]) -> Tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"phase3_router_quick_compare_{ts}.json"
    md_path = report_dir / f"phase3_router_quick_compare_{ts}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")

    d = result["decision"]
    lines = [
        f"# Phase-3 Router Quick Compare ({ts})",
        "",
        "## Decision",
        f"- quality_change_pct: {d['quality_change_pct']:.2f}",
        f"- latency_gain_pct: {d['latency_gain_pct']:.2f}",
        f"- quality_pass: {d['quality_pass']}",
        f"- latency_pass: {d['latency_pass']}",
        f"- recommend_rule_based: {d['recommend_rule_based']}",
        "",
        "## Static",
        f"- success_rate: {result['static']['success_rate']:.3f}",
        f"- latency p50/p95 (ms): {result['static']['latency_ms']['p50']:.1f} / {result['static']['latency_ms']['p95']:.1f}",
        f"- mrr_mean: {result['static']['quality']['mrr_mean']:.4f}",
        f"- ndcg_at_10_mean: {result['static']['quality']['ndcg_at_10_mean']:.4f}",
        "",
        "## Rule Based",
        f"- success_rate: {result['rule_based']['success_rate']:.3f}",
        f"- latency p50/p95 (ms): {result['rule_based']['latency_ms']['p50']:.1f} / {result['rule_based']['latency_ms']['p95']:.1f}",
        f"- mrr_mean: {result['rule_based']['quality']['mrr_mean']:.4f}",
        f"- ndcg_at_10_mean: {result['rule_based']['quality']['ndcg_at_10_mean']:.4f}",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-3 quick router A/B compare")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--max-queries", type=int, default=8)
    parser.add_argument("--request-timeout-sec", type=float, default=20.0)
    parser.add_argument("--dataset", default="")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parents[1]
    report_dir = repo_root / "documentation" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    dataset_path = Path(args.dataset) if args.dataset else (backend_dir / "data" / "phase0_query_set.json")
    queries = load_queries(dataset_path, args.max_queries)
    py_exec = sys.executable

    static_sum = run_mode(
        mode="static",
        py_exec=py_exec,
        backend_dir=backend_dir,
        base_url=args.base_url,
        port=5011,
        uid=args.uid,
        queries=queries,
        request_timeout_sec=args.request_timeout_sec,
    )
    rule_sum = run_mode(
        mode="rule_based",
        py_exec=py_exec,
        backend_dir=backend_dir,
        base_url=args.base_url,
        port=5012,
        uid=args.uid,
        queries=queries,
        request_timeout_sec=args.request_timeout_sec,
    )
    result = compare(static_sum, rule_sum)
    json_path, md_path = write_reports(report_dir, result)
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] MD report:   {md_path}")


if __name__ == "__main__":
    main()
