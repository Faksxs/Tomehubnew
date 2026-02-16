#!/usr/bin/env python3
"""
Phase-2 freshness probe.

Polls /api/books/{book_id}/ingestion-status and reports:
- status transitions (PROCESSING -> COMPLETED)
- index_freshness_state transitions (not_ready -> vector_ready -> fully_ready)
- first seen times for vector_ready / graph_ready / fully_ready
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import request as urllib_request
from urllib import parse as urllib_parse


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str, timeout_sec: float) -> Tuple[int, Dict[str, Any], Optional[str]]:
    req = urllib_request.Request(url, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.getcode()), json.loads(body), None
    except Exception as e:
        return 0, {}, str(e)


def build_status_url(base_url: str, uid: str, book_id: str) -> str:
    qs = urllib_parse.urlencode({"firebase_uid": uid})
    return f"{base_url.rstrip('/')}/api/books/{book_id}/ingestion-status?{qs}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-2 freshness probe runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--timeout-sec", type=float, default=600.0)
    parser.add_argument("--interval-sec", type=float, default=2.0)
    parser.add_argument("--http-timeout-sec", type=float, default=10.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    started_monotonic = time.monotonic()
    started_at = now_iso()
    status_url = build_status_url(args.base_url, args.uid, args.book_id)

    rows: List[Dict[str, Any]] = []
    first_seen: Dict[str, Optional[float]] = {
        "processing_sec": None,
        "completed_sec": None,
        "vector_ready_sec": None,
        "graph_ready_sec": None,
        "fully_ready_sec": None,
    }

    while True:
        elapsed = time.monotonic() - started_monotonic
        if elapsed > args.timeout_sec:
            break

        status_code, payload, err = get_json(status_url, args.http_timeout_sec)
        status_val = str(payload.get("status") or "")
        freshness_state = str(payload.get("index_freshness_state") or "")
        freshness = payload.get("index_freshness") or {}

        row = {
            "t_sec": round(elapsed, 3),
            "at": now_iso(),
            "http_status": status_code,
            "error": err,
            "status": status_val,
            "index_freshness_state": freshness_state,
            "total_chunks": freshness.get("total_chunks"),
            "embedded_chunks": freshness.get("embedded_chunks"),
            "graph_linked_chunks": freshness.get("graph_linked_chunks"),
            "vector_coverage_ratio": freshness.get("vector_coverage_ratio"),
            "graph_coverage_ratio": freshness.get("graph_coverage_ratio"),
        }
        rows.append(row)

        if status_val == "PROCESSING" and first_seen["processing_sec"] is None:
            first_seen["processing_sec"] = round(elapsed, 3)
        if status_val == "COMPLETED" and first_seen["completed_sec"] is None:
            first_seen["completed_sec"] = round(elapsed, 3)
        if freshness_state in {"vector_ready", "fully_ready"} and first_seen["vector_ready_sec"] is None:
            first_seen["vector_ready_sec"] = round(elapsed, 3)
        if freshness_state in {"graph_ready", "fully_ready"} and first_seen["graph_ready_sec"] is None:
            first_seen["graph_ready_sec"] = round(elapsed, 3)
        if freshness_state == "fully_ready" and first_seen["fully_ready_sec"] is None:
            first_seen["fully_ready_sec"] = round(elapsed, 3)

        if freshness_state == "fully_ready":
            break

        time.sleep(args.interval_sec)

    total_elapsed = round(time.monotonic() - started_monotonic, 3)
    timed_out = first_seen["fully_ready_sec"] is None

    summary = {
        "started_at": started_at,
        "finished_at": now_iso(),
        "base_url": args.base_url,
        "uid": args.uid,
        "book_id": args.book_id,
        "timeout_sec": args.timeout_sec,
        "interval_sec": args.interval_sec,
        "total_elapsed_sec": total_elapsed,
        "timed_out": timed_out,
        "first_seen_sec": first_seen,
        "sample_count": len(rows),
        "last_sample": rows[-1] if rows else None,
        "rows": rows,
    }

    repo_root = Path(__file__).resolve().parents[3]
    reports_dir = repo_root / "documentation" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    out_json = Path(args.out_json) if args.out_json else (reports_dir / f"phase2_freshness_probe_{ts}.json")
    out_md = Path(args.out_md) if args.out_md else (reports_dir / f"phase2_freshness_probe_{ts}.md")

    out_json.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")

    md_lines = [
        f"# Phase-2 Freshness Probe ({ts})",
        "",
        "## Input",
        f"- base_url: {args.base_url}",
        f"- uid: {args.uid}",
        f"- book_id: {args.book_id}",
        f"- timeout_sec: {args.timeout_sec}",
        f"- interval_sec: {args.interval_sec}",
        "",
        "## First Seen (seconds)",
        f"- processing_sec: {first_seen['processing_sec']}",
        f"- completed_sec: {first_seen['completed_sec']}",
        f"- vector_ready_sec: {first_seen['vector_ready_sec']}",
        f"- graph_ready_sec: {first_seen['graph_ready_sec']}",
        f"- fully_ready_sec: {first_seen['fully_ready_sec']}",
        "",
        "## Result",
        f"- timed_out: {timed_out}",
        f"- total_elapsed_sec: {total_elapsed}",
        f"- sample_count: {len(rows)}",
        "",
        "## Last Sample",
        f"- status: {(rows[-1].get('status') if rows else None)}",
        f"- index_freshness_state: {(rows[-1].get('index_freshness_state') if rows else None)}",
        f"- total_chunks: {(rows[-1].get('total_chunks') if rows else None)}",
        f"- embedded_chunks: {(rows[-1].get('embedded_chunks') if rows else None)}",
        f"- graph_linked_chunks: {(rows[-1].get('graph_linked_chunks') if rows else None)}",
        f"- vector_coverage_ratio: {(rows[-1].get('vector_coverage_ratio') if rows else None)}",
        f"- graph_coverage_ratio: {(rows[-1].get('graph_coverage_ratio') if rows else None)}",
    ]
    out_md.write_text("\n".join(md_lines), encoding="utf-8")

    print(str(out_json))
    print(str(out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
