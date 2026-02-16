#!/usr/bin/env python3
"""
Phase-0 baseline benchmark runner.

Measures:
- Latency p50/p95
- Timeout rate
- Result count
- Heuristic quality (MRR, nDCG@10)
- Explorer retry/attempt profile
- Graph hit-rate probe (optional, service-level)

Run example:
  python scripts/phase0_benchmark.py --uid your_uid --base-url http://localhost:5001
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from urllib import request as urllib_request
from urllib import error as urllib_error


@dataclass
class QueryItem:
    qid: str
    category: str
    query: str
    expected_terms: List[str]


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    vals = sorted(values)
    rank = (len(vals) - 1) * (p / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return vals[int(rank)]
    weight = rank - low
    return vals[low] * (1 - weight) + vals[high] * weight


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def is_relevant(doc_text: str, expected_terms: List[str]) -> bool:
    if not expected_terms:
        return False
    text = _normalize(doc_text)
    for term in expected_terms:
        if _normalize(term) in text:
            return True
    return False


def dcg_at_k(binary_rels: List[int], k: int = 10) -> float:
    score = 0.0
    for i, rel in enumerate(binary_rels[:k], start=1):
        if rel:
            score += 1.0 / math.log2(i + 1)
    return score


def ndcg_at_k(binary_rels: List[int], k: int = 10) -> float:
    if not binary_rels:
        return 0.0
    dcg = dcg_at_k(binary_rels, k)
    ideal = sorted(binary_rels, reverse=True)
    idcg = dcg_at_k(ideal, k)
    return (dcg / idcg) if idcg > 0 else 0.0


def mrr(binary_rels: List[int]) -> float:
    for idx, rel in enumerate(binary_rels, start=1):
        if rel:
            return 1.0 / idx
    return 0.0


def load_query_set(path: Path) -> List[QueryItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: List[QueryItem] = []
    for r in raw:
        out.append(
            QueryItem(
                qid=str(r.get("id", "")),
                category=str(r.get("category", "UNKNOWN")),
                query=str(r.get("query", "")),
                expected_terms=list(r.get("expected_terms") or []),
            )
        )
    return out


def post_json(base_url: str, endpoint: str, payload: Dict[str, Any], timeout_sec: float) -> Tuple[int, Dict[str, Any], Optional[str]]:
    url = f"{base_url.rstrip('/')}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
            status = int(resp.getcode())
            body = resp.read().decode("utf-8")
            return status, json.loads(body), None
    except urllib_error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {}
        return int(e.code), parsed, f"http_error:{e.code}"
    except Exception as e:
        return 0, {}, str(e)


def extract_ranked_docs(endpoint_key: str, body: Dict[str, Any]) -> List[str]:
    docs: List[str] = []
    if endpoint_key == "search":
        for s in body.get("sources") or []:
            docs.append(f"{s.get('title', '')} {s.get('content', '')}")
    elif endpoint_key == "smart":
        for r in body.get("results") or []:
            docs.append(f"{r.get('title', '')} {r.get('content_chunk', '')}")
    elif endpoint_key == "chat_explorer":
        for s in body.get("sources") or []:
            docs.append(f"{s.get('title', '')} {s.get('content', '')}")
    return docs


def build_payload(endpoint_key: str, q: QueryItem, uid: str) -> Dict[str, Any]:
    if endpoint_key == "search":
        return {
            "question": q.query,
            "firebase_uid": uid,
            "limit": 20,
            "offset": 0,
        }
    if endpoint_key == "smart":
        return {
            "question": q.query,
            "firebase_uid": uid,
            "limit": 20,
            "offset": 0,
        }
    if endpoint_key == "chat_explorer":
        return {
            "message": q.query,
            "firebase_uid": uid,
            "mode": "EXPLORER",
            "limit": 5,
            "offset": 0,
        }
    raise ValueError(f"Unknown endpoint key: {endpoint_key}")


def result_count(endpoint_key: str, body: Dict[str, Any]) -> int:
    if endpoint_key == "search":
        return len(body.get("sources") or [])
    if endpoint_key == "smart":
        return int(body.get("total") or len(body.get("results") or []))
    if endpoint_key == "chat_explorer":
        return len(body.get("sources") or [])
    return 0


def stratified_sample(items: List[QueryItem], sample_size: int) -> List[QueryItem]:
    if sample_size <= 0 or sample_size >= len(items):
        return list(items)
    by_cat: Dict[str, List[QueryItem]] = defaultdict(list)
    for x in items:
        by_cat[x.category].append(x)
    categories = sorted(by_cat.keys())
    base = sample_size // max(1, len(categories))
    rem = sample_size % max(1, len(categories))

    sampled: List[QueryItem] = []
    for i, c in enumerate(categories):
        take = base + (1 if i < rem else 0)
        sampled.extend(by_cat[c][:take])
    return sampled[:sample_size]


def run_endpoint_benchmark(
    endpoint_key: str,
    endpoint_path: str,
    queries: List[QueryItem],
    uid: str,
    base_url: str,
    timeout_sec: float,
) -> Dict[str, Any]:
    rows = []
    for q in queries:
        payload = build_payload(endpoint_key, q, uid)
        t0 = time.perf_counter()
        status, body, err = post_json(base_url, endpoint_path, payload, timeout_sec)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        timed_out = "timed out" in (err or "").lower()
        ok = status == 200 and not timed_out
        docs = extract_ranked_docs(endpoint_key, body)
        rels = [1 if is_relevant(d, q.expected_terms) else 0 for d in docs]
        has_quality_label = len(q.expected_terms) > 0

        metadata = body.get("metadata") or {}
        rows.append(
            {
                "qid": q.qid,
                "category": q.category,
                "query": q.query,
                "status": status,
                "ok": ok,
                "timed_out": timed_out,
                "error": err,
                "latency_ms": latency_ms,
                "result_count": result_count(endpoint_key, body),
                "has_quality_label": has_quality_label,
                "mrr": mrr(rels) if has_quality_label else None,
                "ndcg_at_10": ndcg_at_k(rels, 10) if has_quality_label else None,
                "metadata_verdict": metadata.get("verdict"),
                "metadata_attempts": metadata.get("attempts"),
                "metadata_total_latency_ms": metadata.get("total_latency_ms"),
            }
        )

    latencies = [r["latency_ms"] for r in rows]
    successes = [r for r in rows if r["ok"]]
    timeouts = [r for r in rows if r["timed_out"]]
    quality_rows = [r for r in rows if r["has_quality_label"] and r["mrr"] is not None]

    chat_attempts = [float(r["metadata_attempts"]) for r in rows if isinstance(r.get("metadata_attempts"), (int, float))]
    fallback_rows = [r for r in rows if r.get("metadata_verdict") == "FALLBACK_TIMEOUT"]

    summary = {
        "endpoint_key": endpoint_key,
        "endpoint_path": endpoint_path,
        "query_count": len(rows),
        "success_count": len(successes),
        "success_rate": (len(successes) / len(rows)) if rows else 0.0,
        "timeout_count": len(timeouts),
        "timeout_rate": (len(timeouts) / len(rows)) if rows else 0.0,
        "latency_ms": {
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "mean": (sum(latencies) / len(latencies)) if latencies else 0.0,
        },
        "result_count": {
            "mean": (sum(r["result_count"] for r in rows) / len(rows)) if rows else 0.0,
            "p50": percentile([r["result_count"] for r in rows], 50) if rows else 0.0,
        },
        "quality": {
            "evaluated_query_count": len(quality_rows),
            "mrr_mean": (sum(float(r["mrr"]) for r in quality_rows) / len(quality_rows)) if quality_rows else 0.0,
            "ndcg_at_10_mean": (sum(float(r["ndcg_at_10"]) for r in quality_rows) / len(quality_rows)) if quality_rows else 0.0,
        },
        "explorer": {
            "avg_attempts": (sum(chat_attempts) / len(chat_attempts)) if chat_attempts else 0.0,
            "fallback_timeout_count": len(fallback_rows),
            "fallback_timeout_rate": (len(fallback_rows) / len(rows)) if rows else 0.0,
        },
        "rows": rows,
    }
    return summary


def run_graph_probe(queries: List[QueryItem], uid: str, limit: int, sample_size: int) -> Dict[str, Any]:
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from services.search_service import get_rag_context  # pylint: disable=import-error

    sampled = stratified_sample(queries, sample_size)
    rows = []
    for q in sampled:
        t0 = time.perf_counter()
        error = None
        graph_count = 0
        total_chunks = 0
        try:
            ctx = get_rag_context(q.query, uid, limit=limit, offset=0)
            chunks = (ctx or {}).get("chunks") or []
            total_chunks = len(chunks)
            graph_count = sum(1 for c in chunks if str(c.get("source_type", "")) == "GRAPH_RELATION")
        except Exception as e:
            error = str(e)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        rows.append(
            {
                "qid": q.qid,
                "category": q.category,
                "query": q.query,
                "graph_chunk_count": graph_count,
                "total_chunks": total_chunks,
                "latency_ms": latency_ms,
                "error": error,
            }
        )

    ok_rows = [r for r in rows if not r["error"]]
    hit_rows = [r for r in ok_rows if r["graph_chunk_count"] > 0]

    return {
        "sample_size": len(rows),
        "ok_count": len(ok_rows),
        "error_count": len(rows) - len(ok_rows),
        "graph_hit_count": len(hit_rows),
        "graph_hit_rate": (len(hit_rows) / len(ok_rows)) if ok_rows else 0.0,
        "avg_graph_chunk_count": (sum(r["graph_chunk_count"] for r in ok_rows) / len(ok_rows)) if ok_rows else 0.0,
        "latency_ms": {
            "p50": percentile([r["latency_ms"] for r in rows], 50) if rows else 0.0,
            "p95": percentile([r["latency_ms"] for r in rows], 95) if rows else 0.0,
        },
        "rows": rows,
    }


def write_reports(repo_root: Path, report: Dict[str, Any]) -> Tuple[Path, Path]:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = repo_root / "documentation" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"phase0_baseline_{ts}.json"
    md_path = out_dir / f"phase0_baseline_{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")

    lines = []
    lines.append(f"# Phase-0 Baseline Report ({ts})")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Endpoints: /api/search, /api/smart-search, /api/chat (EXPLORER)")
    lines.append("- Metrics: success/timeout, latency p50-p95, MRR, nDCG@10, graph hit-rate probe")
    lines.append("")
    lines.append("## Acceptance Targets")
    lines.append("- Quality gain target (future comparison): >= +5%")
    lines.append("- Latency increase ceiling (future comparison): <= +10%")
    lines.append("- Explorer p95 target: <= 12000ms")
    lines.append("")

    for s in report["endpoint_summaries"]:
        lines.append(f"## Endpoint: {s['endpoint_key']}")
        lines.append(f"- Query count: {s['query_count']}")
        lines.append(f"- Success rate: {s['success_rate']:.3f}")
        lines.append(f"- Timeout rate: {s['timeout_rate']:.3f}")
        lines.append(f"- Latency p50/p95 (ms): {s['latency_ms']['p50']:.1f} / {s['latency_ms']['p95']:.1f}")
        lines.append(f"- Result count mean: {s['result_count']['mean']:.2f}")
        lines.append(f"- MRR mean: {s['quality']['mrr_mean']:.4f}")
        lines.append(f"- nDCG@10 mean: {s['quality']['ndcg_at_10_mean']:.4f}")
        if s["endpoint_key"] == "chat_explorer":
            lines.append(f"- Explorer avg attempts: {s['explorer']['avg_attempts']:.2f}")
            lines.append(f"- Explorer fallback-timeout rate: {s['explorer']['fallback_timeout_rate']:.3f}")
        lines.append("")

    gp = report.get("graph_probe") or {}
    if gp:
        lines.append("## Graph Probe")
        lines.append(f"- Sample size: {gp.get('sample_size', 0)}")
        lines.append(f"- OK count: {gp.get('ok_count', 0)}")
        lines.append(f"- Graph hit-rate: {gp.get('graph_hit_rate', 0.0):.3f}")
        lines.append(f"- Avg graph chunks: {gp.get('avg_graph_chunk_count', 0.0):.2f}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="Run Phase-0 baseline benchmark.")
    parser.add_argument("--base-url", default="http://localhost:5001")
    parser.add_argument("--uid", required=True, help="Firebase UID for test requests")
    parser.add_argument("--dataset", default="", help="Path to phase0_query_set.json")
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument("--chat-sample-size", type=int, default=30, help="Explorer endpoint sample size")
    parser.add_argument("--disable-chat", action="store_true")
    parser.add_argument("--disable-graph-probe", action="store_true")
    parser.add_argument("--graph-probe-size", type=int, default=30)
    parser.add_argument("--graph-probe-limit", type=int, default=20)
    parser.add_argument("--max-queries", type=int, default=0, help="Cap query count for quick smoke runs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    repo_root = backend_dir.parents[1]
    dataset_path = Path(args.dataset) if args.dataset else (backend_dir / "data" / "phase0_query_set.json")
    queries = load_query_set(dataset_path)
    if not queries:
        raise RuntimeError(f"No queries found in {dataset_path}")
    if args.max_queries and args.max_queries > 0:
        queries = stratified_sample(queries, args.max_queries)

    if args.dry_run:
        print(f"[DRY-RUN] dataset={dataset_path}")
        by_cat = defaultdict(int)
        for q in queries:
            by_cat[q.category] += 1
        print("[DRY-RUN] query count by category:")
        for c in sorted(by_cat.keys()):
            print(f"  - {c}: {by_cat[c]}")
        print(f"[DRY-RUN] total={len(queries)}")
        return

    endpoint_summaries = []
    endpoint_summaries.append(
        run_endpoint_benchmark(
            endpoint_key="search",
            endpoint_path="/api/search",
            queries=queries,
            uid=args.uid,
            base_url=args.base_url,
            timeout_sec=args.timeout_sec,
        )
    )
    endpoint_summaries.append(
        run_endpoint_benchmark(
            endpoint_key="smart",
            endpoint_path="/api/smart-search",
            queries=queries,
            uid=args.uid,
            base_url=args.base_url,
            timeout_sec=args.timeout_sec,
        )
    )

    if not args.disable_chat:
        chat_queries = stratified_sample(queries, args.chat_sample_size)
        endpoint_summaries.append(
            run_endpoint_benchmark(
                endpoint_key="chat_explorer",
                endpoint_path="/api/chat",
                queries=chat_queries,
                uid=args.uid,
                base_url=args.base_url,
                timeout_sec=args.timeout_sec,
            )
        )

    graph_probe = None
    if not args.disable_graph_probe:
        graph_probe = run_graph_probe(
            queries=queries,
            uid=args.uid,
            limit=args.graph_probe_limit,
            sample_size=args.graph_probe_size,
        )

    report = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "base_url": args.base_url,
            "uid": args.uid,
            "dataset": str(dataset_path),
            "timeout_sec": args.timeout_sec,
            "chat_sample_size": args.chat_sample_size,
            "graph_probe_size": args.graph_probe_size,
            "max_queries": args.max_queries,
        },
        "acceptance_targets": {
            "quality_gain_target_pct": 5.0,
            "latency_increase_ceiling_pct": 10.0,
            "explorer_p95_target_ms": 12000.0,
        },
        "endpoint_summaries": endpoint_summaries,
        "graph_probe": graph_probe,
    }

    json_path, md_path = write_reports(repo_root, report)
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] MD report:   {md_path}")


if __name__ == "__main__":
    main()
