#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _append_backend_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "apps" / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


_append_backend_to_path()

from infrastructure.db_manager import DatabaseManager  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def fetch_state(book_id: str, firebase_uid: str) -> dict[str, Any]:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ITEM_ID, TITLE, AUTHOR
                FROM TOMEHUB_LIBRARY_ITEMS
                WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid
                """,
                {"p_bid": book_id, "p_uid": firebase_uid},
            )
            item_row = cur.fetchone()

            cur.execute(
                """
                SELECT STATUS,
                       SOURCE_FILE_NAME,
                       UPDATED_AT,
                       CHUNK_COUNT,
                       EMBEDDING_COUNT,
                       CLASSIFICATION_ROUTE,
                       PARSE_ENGINE,
                       FALLBACK_ENGINE,
                       PARSE_TIME_MS,
                       PAGES,
                       CHARS_EXTRACTED,
                       GARBLED_RATIO,
                       AVG_CHUNK_TOKENS,
                       FALLBACK_TRIGGERED,
                       SHARD_COUNT,
                       SHARD_FAILED_COUNT
                FROM TOMEHUB_INGESTED_FILES
                WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                """,
                {"p_bid": book_id, "p_uid": firebase_uid},
            )
            ingest_row = cur.fetchone()

            cur.execute(
                """
                SELECT CONTENT_TYPE, COUNT(*)
                FROM TOMEHUB_CONTENT_V2
                WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid
                GROUP BY CONTENT_TYPE
                ORDER BY CONTENT_TYPE
                """,
                {"p_bid": book_id, "p_uid": firebase_uid},
            )
            content_rows = cur.fetchall()

    state: dict[str, Any] = {
        "book_id": book_id,
        "firebase_uid": firebase_uid,
        "observed_at": utc_now(),
        "library_item": None,
        "ingestion": None,
        "content_counts": {},
    }

    if item_row:
        state["library_item"] = {
            "item_id": str(item_row[0]),
            "title": str(item_row[1] or ""),
            "author": str(item_row[2] or ""),
        }

    if ingest_row:
        state["ingestion"] = {
            "status": str(ingest_row[0] or ""),
            "source_file_name": str(ingest_row[1] or ""),
            "updated_at": ingest_row[2].isoformat() if getattr(ingest_row[2], "isoformat", None) else str(ingest_row[2] or ""),
            "chunk_count": int(ingest_row[3] or 0),
            "embedding_count": int(ingest_row[4] or 0),
            "classification_route": str(ingest_row[5] or ""),
            "parse_engine": str(ingest_row[6] or ""),
            "fallback_engine": str(ingest_row[7] or ""),
            "parse_time_ms": int(ingest_row[8] or 0),
            "pages": int(ingest_row[9] or 0),
            "chars_extracted": int(ingest_row[10] or 0),
            "garbled_ratio": float(ingest_row[11] or 0.0),
            "avg_chunk_tokens": float(ingest_row[12] or 0.0),
            "fallback_triggered": bool(ingest_row[13]),
            "shard_count": int(ingest_row[14] or 0),
            "shard_failed_count": int(ingest_row[15] or 0),
        }

    state["content_counts"] = {str(kind or ""): int(count or 0) for kind, count in content_rows}
    state["effective_pdf_chunks"] = int(
        state["content_counts"].get("PDF", 0)
        + state["content_counts"].get("PDF_CHUNK", 0)
        + state["content_counts"].get("EPUB", 0)
    )
    return state


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    ingest = state.get("ingestion") or {}
    item = state.get("library_item") or {}
    return {
        "title": item.get("title"),
        "author": item.get("author"),
        "status": ingest.get("status"),
        "source_file_name": ingest.get("source_file_name"),
        "updated_at": ingest.get("updated_at"),
        "chunk_count": ingest.get("chunk_count"),
        "embedding_count": ingest.get("embedding_count"),
        "classification_route": ingest.get("classification_route"),
        "parse_engine": ingest.get("parse_engine"),
        "fallback_engine": ingest.get("fallback_engine"),
        "parse_time_ms": ingest.get("parse_time_ms"),
        "pages": ingest.get("pages"),
        "chars_extracted": ingest.get("chars_extracted"),
        "garbled_ratio": ingest.get("garbled_ratio"),
        "avg_chunk_tokens": ingest.get("avg_chunk_tokens"),
        "fallback_triggered": ingest.get("fallback_triggered"),
        "shard_count": ingest.get("shard_count"),
        "shard_failed_count": ingest.get("shard_failed_count"),
        "content_counts": state.get("content_counts"),
        "effective_pdf_chunks": state.get("effective_pdf_chunks"),
    }


def log_line(handle, message: str) -> None:
    handle.write(message + "\n")
    handle.flush()
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll TomeHub PDF ingestion state for a single book.")
    parser.add_argument("--firebase-uid", required=True)
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--poll-sec", type=float, default=5.0)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--log-file", required=True)
    args = parser.parse_args()

    DatabaseManager.init_pool()

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    last_snapshot = None

    with log_path.open("a", encoding="utf-8") as handle:
        log_line(
            handle,
            f"[{utc_now()}] watcher_started label={args.label or '-'} book_id={args.book_id}",
        )
        while True:
            try:
                state = fetch_state(args.book_id, args.firebase_uid)
                snapshot = compact_state(state)
                if snapshot != last_snapshot:
                    log_line(handle, f"[{utc_now()}] state_change {json_dumps(snapshot)}")
                    last_snapshot = snapshot

                status = str((state.get("ingestion") or {}).get("status") or "").upper()
                if status in {"COMPLETED", "FAILED"}:
                    log_line(handle, f"[{utc_now()}] watcher_finished terminal_status={status}")
                    return 0
            except Exception as exc:
                log_line(handle, f"[{utc_now()}] watcher_error {exc}")

            if (time.time() - started_at) >= args.timeout_sec:
                log_line(handle, f"[{utc_now()}] watcher_finished timeout=true")
                return 2

            time.sleep(max(1.0, float(args.poll_sec)))


if __name__ == "__main__":
    raise SystemExit(main())
