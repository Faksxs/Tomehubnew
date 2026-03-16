#!/usr/bin/env python3
"""
Offline in-place re-embed workflow for gemini-embedding-2-preview.

This tool is designed for maintenance windows where the backend is not serving
traffic. It supports:
- preflight checks
- Oracle-side backup tables
- throttled full re-embed for content/concepts
- progress checkpointing + resume
- vector index rebuild
- post-run validation
- rollback restore dry-run / execute
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import oracledb

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
REPO_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
sys.path.insert(0, BACKEND_DIR)

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402
from services.llm_client import MODEL_TIER_EMBEDDING, embed_contents, get_model_for_tier  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover - optional at import time
    psutil = None


EXPECTED_MODEL_NAME = "gemini-embedding-2-preview"
EXPECTED_MODEL_VERSION = "v4"
CONTENT_BACKUP_TABLE = "TOMEHUB_CONTENT_V2_EMB_BAK_PRE_GEM2"
CONCEPT_BACKUP_TABLE = "TOMEHUB_CONCEPTS_EMB_BAK_PRE_GEM2"
CONTENT_INDEX_NAME = "IDX_CNT_VEC_V2"
CONCEPT_INDEX_NAME = "IDX_CONCEPTS_DESC_VEC"
CHECKPOINT_PATH = os.path.join(REPO_ROOT, "tmp", "embedding_reembed_v4_progress.json")
ROLLBACK_HINT = (
    "Rollback also requires restoring EMBEDDING_MODEL_NAME and "
    "EMBEDDING_MODEL_VERSION in apps/backend/.env to their pre-migration values."
)
CONTENT_SCOPE = "content"
CONCEPT_SCOPE = "concepts"
ALL_SCOPE = "all"


@dataclass(frozen=True)
class ScopeConfig:
    scope: str
    label: str
    select_sql: str
    count_sql: str
    backup_table: str
    update_sql: str
    checkpoint_key: str


SCOPES: dict[str, ScopeConfig] = {
    CONTENT_SCOPE: ScopeConfig(
        scope=CONTENT_SCOPE,
        label="content",
        select_sql="""
            SELECT id, content_chunk
            FROM (
                SELECT id, content_chunk
                FROM TOMEHUB_CONTENT_V2
                WHERE content_chunk IS NOT NULL
                  AND id > :p_last_id
                ORDER BY id
            )
            WHERE ROWNUM <= :p_limit
        """,
        count_sql="""
            SELECT COUNT(*),
                   SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN CONTENT_CHUNK IS NOT NULL THEN DBMS_LOB.GETLENGTH(CONTENT_CHUNK) ELSE 0 END)
            FROM TOMEHUB_CONTENT_V2
            WHERE CONTENT_CHUNK IS NOT NULL
        """,
        backup_table=CONTENT_BACKUP_TABLE,
        update_sql="""
            UPDATE TOMEHUB_CONTENT_V2
            SET VEC_EMBEDDING = :p_vec
            WHERE ID = :p_id
        """,
        checkpoint_key="content",
    ),
    CONCEPT_SCOPE: ScopeConfig(
        scope=CONCEPT_SCOPE,
        label="concepts",
        select_sql="""
            SELECT id, name, description
            FROM (
                SELECT id, name, description
                FROM TOMEHUB_CONCEPTS
                WHERE id > :p_last_id
                ORDER BY id
            )
            WHERE ROWNUM <= :p_limit
        """,
        count_sql="""
            SELECT COUNT(*),
                   SUM(CASE WHEN DESCRIPTION_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE
                         WHEN DESCRIPTION IS NOT NULL THEN DBMS_LOB.GETLENGTH(DESCRIPTION)
                         ELSE NVL(LENGTH(NAME), 0)
                       END)
            FROM TOMEHUB_CONCEPTS
        """,
        backup_table=CONCEPT_BACKUP_TABLE,
        update_sql="""
            UPDATE TOMEHUB_CONCEPTS
            SET DESCRIPTION_EMBEDDING = :p_vec
            WHERE ID = :p_id
        """,
        checkpoint_key="concepts",
    ),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens_from_chars(char_count: int) -> int:
    return max(0, int(math.ceil(max(0, int(char_count or 0)) / 4.0)))


def _table_exists(cursor: oracledb.Cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :p_table",
        {"p_table": str(table_name or "").upper()},
    )
    return cursor.fetchone() is not None


def _get_index_statuses(cursor: oracledb.Cursor) -> dict[str, str]:
    cursor.execute(
        """
        SELECT index_name, status
        FROM user_indexes
        WHERE index_name IN (:p_content, :p_concepts)
        ORDER BY index_name
        """,
        {"p_content": CONTENT_INDEX_NAME, "p_concepts": CONCEPT_INDEX_NAME},
    )
    return {str(name): str(status) for name, status in cursor.fetchall()}


def _ensure_expected_runtime() -> None:
    if settings.EMBEDDING_MODEL_NAME != EXPECTED_MODEL_NAME:
        raise RuntimeError(
            f"EMBEDDING_MODEL_NAME must be {EXPECTED_MODEL_NAME!r}, "
            f"got {settings.EMBEDDING_MODEL_NAME!r}"
        )
    if settings.EMBEDDING_MODEL_VERSION != EXPECTED_MODEL_VERSION:
        raise RuntimeError(
            f"EMBEDDING_MODEL_VERSION must be {EXPECTED_MODEL_VERSION!r}, "
            f"got {settings.EMBEDDING_MODEL_VERSION!r}"
        )


def _iter_backend_processes() -> list[dict[str, Any]]:
    if psutil is None:
        return []

    current_pid = os.getpid()
    matches: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = int(proc.info.get("pid") or 0)
            if pid == current_pid:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            lowered = cmdline.lower()
            if not lowered:
                continue
            if "reembed_embeddings_inplace.py" in lowered:
                continue
            if (
                "apps\\backend\\app.py" in lowered
                or "apps/backend/app.py" in lowered
                or "uvicorn" in lowered
            ):
                matches.append(
                    {
                        "pid": pid,
                        "name": proc.info.get("name") or "",
                        "cmdline": cmdline,
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def _ensure_backend_not_running() -> None:
    matches = _iter_backend_processes()
    if not matches:
        return
    lines = ["Backend or uvicorn process appears to be running:"]
    for item in matches:
        lines.append(
            f"  pid={item['pid']} name={item['name']} cmd={item['cmdline'][:180]}"
        )
    raise RuntimeError("\n".join(lines))


def _ensure_tmp_dir() -> None:
    Path(os.path.dirname(CHECKPOINT_PATH)).mkdir(parents=True, exist_ok=True)


def _load_checkpoint() -> dict[str, Any]:
    if not os.path.exists(CHECKPOINT_PATH):
        return {
            "updated_at": None,
            "content": {"last_id": 0, "processed": 0, "batches": 0},
            "concepts": {"last_id": 0, "processed": 0, "batches": 0},
        }
    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    data.setdefault("content", {"last_id": 0, "processed": 0, "batches": 0})
    data.setdefault("concepts", {"last_id": 0, "processed": 0, "batches": 0})
    return data


def _save_checkpoint(payload: dict[str, Any]) -> None:
    _ensure_tmp_dir()
    payload["updated_at"] = _utc_now()
    tmp_path = f"{CHECKPOINT_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
    os.replace(tmp_path, CHECKPOINT_PATH)


class TokenThrottle:
    def __init__(self, target_tpm: int, sleep_floor_ms: int = 0) -> None:
        self.target_tpm = max(1, int(target_tpm))
        self.sleep_floor_ms = max(0, int(sleep_floor_ms))
        self._window: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _tokens_used(self, now: float) -> int:
        self._prune(now)
        return sum(tokens for _, tokens in self._window)

    def wait_for_budget(self, tokens: int) -> float:
        required = max(0, int(tokens))
        waited = 0.0
        while True:
            now = time.monotonic()
            used = self._tokens_used(now)
            if used + required <= self.target_tpm:
                self._window.append((now, required))
                break
            if not self._window:
                break
            oldest_ts, _ = self._window[0]
            sleep_s = max(0.05, 60.0 - (now - oldest_ts))
            time.sleep(sleep_s)
            waited += sleep_s

        if self.sleep_floor_ms > 0:
            floor_s = float(self.sleep_floor_ms) / 1000.0
            time.sleep(floor_s)
            waited += floor_s
        return waited


class RateWindowThrottle:
    def __init__(self, limit_per_minute: int, sleep_floor_ms: int = 0) -> None:
        self.limit_per_minute = max(1, int(limit_per_minute))
        self.sleep_floor_ms = max(0, int(sleep_floor_ms))
        self._window: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _used(self, now: float) -> int:
        self._prune(now)
        return sum(units for _, units in self._window)

    def wait_for_budget(self, units: int) -> float:
        required = max(0, int(units))
        waited = 0.0
        while True:
            now = time.monotonic()
            used = self._used(now)
            if used + required <= self.limit_per_minute:
                self._window.append((now, required))
                break
            if not self._window:
                break
            oldest_ts, _ = self._window[0]
            sleep_s = max(0.05, 60.0 - (now - oldest_ts))
            time.sleep(sleep_s)
            waited += sleep_s

        if self.sleep_floor_ms > 0:
            floor_s = float(self.sleep_floor_ms) / 1000.0
            time.sleep(floor_s)
            waited += floor_s
        return waited


def _normalize_scope(scope: str) -> list[ScopeConfig]:
    normalized = str(scope or ALL_SCOPE).strip().lower()
    if normalized == ALL_SCOPE:
        return [SCOPES[CONTENT_SCOPE], SCOPES[CONCEPT_SCOPE]]
    if normalized not in SCOPES:
        raise ValueError(f"Unsupported scope: {scope}")
    return [SCOPES[normalized]]


def _fetch_rows(cursor: oracledb.Cursor, config: ScopeConfig, last_id: int, limit: int) -> list[Any]:
    cursor.execute(
        config.select_sql,
        {"p_last_id": int(last_id), "p_limit": int(limit)},
    )
    return cursor.fetchall()


def _content_payload(rows: Sequence[Any]) -> tuple[list[int], list[str], int]:
    ids: list[int] = []
    texts: list[str] = []
    total_chars = 0
    for row_id, content_chunk in rows:
        text = safe_read_clob(content_chunk).strip()
        if not text:
            raise RuntimeError(f"Empty content encountered for content id={row_id}")
        ids.append(int(row_id))
        texts.append(text)
        total_chars += len(text)
    return ids, texts, total_chars


def _concept_payload(rows: Sequence[Any]) -> tuple[list[int], list[str], int]:
    ids: list[int] = []
    texts: list[str] = []
    total_chars = 0
    for row_id, name, description in rows:
        desc_text = safe_read_clob(description).strip() if description else ""
        text = desc_text if desc_text else str(name or "").strip()
        if not text:
            raise RuntimeError(f"Empty concept source text encountered for concept id={row_id}")
        ids.append(int(row_id))
        texts.append(text)
        total_chars += len(text)
    return ids, texts, total_chars


def _build_payload(config: ScopeConfig, rows: Sequence[Any]) -> tuple[list[int], list[str], int]:
    if config.scope == CONTENT_SCOPE:
        return _content_payload(rows)
    return _concept_payload(rows)


def _count_summary(cursor: oracledb.Cursor, config: ScopeConfig) -> dict[str, int]:
    cursor.execute(config.count_sql)
    row = cursor.fetchone() or (0, 0, 0)
    total_rows = int(row[0] or 0)
    embedded_rows = int(row[1] or 0)
    total_chars = int(row[2] or 0)
    return {
        "total_rows": total_rows,
        "embedded_rows": embedded_rows,
        "missing_rows": max(0, total_rows - embedded_rows),
        "total_chars": total_chars,
        "estimated_tokens": _estimate_tokens_from_chars(total_chars),
    }


def _direct_batch_embeddings(texts: Sequence[str]) -> list[array.array]:
    model_name = get_model_for_tier(MODEL_TIER_EMBEDDING)
    attempts = 4
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            vectors = embed_contents(
                model=model_name,
                contents=list(texts),
                task_type="retrieval_document",
                output_dimensionality=768,
                timeout_s=30.0,
                task="embedding_migration",
            )
            if len(vectors) != len(texts):
                raise RuntimeError(
                    f"Embedding response count mismatch: expected={len(texts)} actual={len(vectors)}"
                )
            return [array.array("f", vector) for vector in vectors]
        except (httpx.ReadError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(10.0, 1.5 * attempt)
            print(
                f"[embedding_migration] transient read/timeout error, retrying attempt={attempt}/{attempts} delay_s={delay}"
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Embedding batch failed without an explicit error")


def _print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True))


def run_preflight(target_tpm: int) -> int:
    _ensure_expected_runtime()
    result: dict[str, Any] = {
        "mode": "preflight",
        "runtime": {
            "embedding_model_name": settings.EMBEDDING_MODEL_NAME,
            "embedding_model_version": settings.EMBEDDING_MODEL_VERSION,
            "expected_model_name": EXPECTED_MODEL_NAME,
            "expected_model_version": EXPECTED_MODEL_VERSION,
        },
        "backup_tables": {},
        "index_status": {},
        "scopes": {},
        "checkpoint_path": CHECKPOINT_PATH,
        "backend_processes": _iter_backend_processes(),
    }

    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                for config in _normalize_scope(ALL_SCOPE):
                    result["backup_tables"][config.scope] = _table_exists(cursor, config.backup_table)
                    scope_summary = _count_summary(cursor, config)
                    scope_summary["estimated_minutes_at_target_tpm"] = round(
                        scope_summary["estimated_tokens"] / max(1, int(target_tpm)),
                        2,
                    )
                    result["scopes"][config.scope] = scope_summary
                result["index_status"] = _get_index_statuses(cursor)
    finally:
        DatabaseManager.close_pool()

    _print_json(result)
    return 0


def _create_backup_table(cursor: oracledb.Cursor, config: ScopeConfig) -> None:
    if _table_exists(cursor, config.backup_table):
        raise RuntimeError(f"Backup table already exists: {config.backup_table}")

    if config.scope == CONTENT_SCOPE:
        sql = f"""
            CREATE TABLE {config.backup_table} AS
            SELECT ID, VEC_EMBEDDING, CURRENT_TIMESTAMP AS BACKED_UP_AT
            FROM TOMEHUB_CONTENT_V2
        """
    else:
        sql = f"""
            CREATE TABLE {config.backup_table} AS
            SELECT ID, DESCRIPTION_EMBEDDING, CURRENT_TIMESTAMP AS BACKED_UP_AT
            FROM TOMEHUB_CONCEPTS
        """
    cursor.execute(sql)


def run_backup(scope: str) -> int:
    _ensure_expected_runtime()
    _ensure_backend_not_running()

    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                configs = _normalize_scope(scope)
                existing = [config.backup_table for config in configs if _table_exists(cursor, config.backup_table)]
                if existing:
                    raise RuntimeError(f"Backup table(s) already exist: {', '.join(existing)}")
                for config in configs:
                    _create_backup_table(cursor, config)
                conn.commit()
    finally:
        DatabaseManager.close_pool()
    print(f"Backup tables created for scope={scope}")
    return 0


def _update_embeddings(
    cursor: oracledb.Cursor,
    config: ScopeConfig,
    ids: Sequence[int],
    embeddings: Sequence[Any],
) -> None:
    if len(ids) != len(embeddings):
        raise RuntimeError(
            f"Embedding count mismatch for {config.scope}: ids={len(ids)} embeddings={len(embeddings)}"
        )
    for row_id, vector in zip(ids, embeddings):
        if vector is None:
            raise RuntimeError(f"Embedding API returned None for {config.scope} id={row_id}")
        cursor.execute(config.update_sql, {"p_id": int(row_id), "p_vec": vector})


def _run_reembed_scope(
    config: ScopeConfig,
    *,
    batch_size: int,
    target_tpm: int,
    target_item_rpm: int,
    sleep_floor_ms: int,
    resume: bool,
) -> dict[str, Any]:
    checkpoint = _load_checkpoint()
    scope_state = checkpoint.get(config.checkpoint_key, {})
    last_id = int(scope_state.get("last_id", 0)) if resume else 0
    processed = int(scope_state.get("processed", 0)) if resume else 0
    batches = int(scope_state.get("batches", 0)) if resume else 0
    throttle = TokenThrottle(target_tpm=target_tpm, sleep_floor_ms=sleep_floor_ms)
    item_throttle = RateWindowThrottle(limit_per_minute=target_item_rpm, sleep_floor_ms=0)
    started_at = time.time()

    while True:
        with DatabaseManager.get_read_connection() as read_conn:
            with read_conn.cursor() as read_cursor:
                rows = _fetch_rows(read_cursor, config, last_id=last_id, limit=batch_size)

        if not rows:
            break

        ids, texts, total_chars = _build_payload(config, rows)
        estimated_tokens = _estimate_tokens_from_chars(total_chars)
        waited_s = 0.0
        waited_s += item_throttle.wait_for_budget(len(texts))
        waited_s += throttle.wait_for_budget(estimated_tokens)
        embeddings = _direct_batch_embeddings(texts)

        with DatabaseManager.get_write_connection() as write_conn:
            with write_conn.cursor() as write_cursor:
                try:
                    _update_embeddings(write_cursor, config, ids, embeddings)
                    write_conn.commit()
                except Exception:
                    write_conn.rollback()
                    raise

        last_id = int(ids[-1])
        processed += len(ids)
        batches += 1
        checkpoint[config.checkpoint_key] = {
            "last_id": last_id,
            "processed": processed,
            "batches": batches,
        }
        _save_checkpoint(checkpoint)
        elapsed = round(time.time() - started_at, 2)
        print(
            f"[{config.scope}] batch={batches} processed={processed} "
            f"last_id={last_id} est_tokens={estimated_tokens} waited_s={round(waited_s, 2)} "
            f"elapsed_s={elapsed}"
        )

    return {
        "scope": config.scope,
        "processed": processed,
        "last_id": last_id,
        "batches": batches,
        "elapsed_s": round(time.time() - started_at, 2),
    }


def run_reembed(
    scope: str,
    batch_size: int,
    target_tpm: int,
    target_item_rpm: int,
    sleep_floor_ms: int,
    resume: bool,
) -> int:
    _ensure_expected_runtime()
    _ensure_backend_not_running()
    _ensure_tmp_dir()

    summaries: list[dict[str, Any]] = []
    DatabaseManager.init_pool()
    try:
        configs = _normalize_scope(scope)
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                missing_backups = [
                    config.backup_table
                    for config in configs
                    if not _table_exists(cursor, config.backup_table)
                ]
        if missing_backups:
            raise RuntimeError(
                "Required backup table(s) missing before re-embed: "
                + ", ".join(missing_backups)
            )
        for config in configs:
            summaries.append(
                _run_reembed_scope(
                    config,
                    batch_size=batch_size,
                    target_tpm=target_tpm,
                    target_item_rpm=target_item_rpm,
                    sleep_floor_ms=sleep_floor_ms,
                    resume=resume,
                )
            )
    finally:
        DatabaseManager.close_pool()

    _print_json({"mode": "reembed", "scope": scope, "summaries": summaries})
    return 0


def run_rebuild_indexes() -> int:
    _ensure_expected_runtime()
    _ensure_backend_not_running()

    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"ALTER INDEX {CONTENT_INDEX_NAME} REBUILD")
                cursor.execute(f"ALTER INDEX {CONCEPT_INDEX_NAME} REBUILD")
                conn.commit()
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                statuses = _get_index_statuses(cursor)
    finally:
        DatabaseManager.close_pool()

    invalid = {name: status for name, status in statuses.items() if status != "VALID"}
    _print_json({"mode": "rebuild_indexes", "index_status": statuses})
    if invalid:
        raise RuntimeError(f"Index rebuild completed but invalid indexes remain: {invalid}")
    return 0


def run_validate() -> int:
    _ensure_expected_runtime()
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                content = _count_summary(cursor, SCOPES[CONTENT_SCOPE])
                concepts = _count_summary(cursor, SCOPES[CONCEPT_SCOPE])
                index_status = _get_index_statuses(cursor)
                backup_status = {
                    CONTENT_SCOPE: _table_exists(cursor, CONTENT_BACKUP_TABLE),
                    CONCEPT_SCOPE: _table_exists(cursor, CONCEPT_BACKUP_TABLE),
                }
    finally:
        DatabaseManager.close_pool()

    result = {
        "mode": "validate",
        "content": content,
        "concepts": concepts,
        "index_status": index_status,
        "backup_tables": backup_status,
    }
    _print_json(result)

    problems: list[str] = []
    if content["missing_rows"] != 0:
        problems.append(f"content missing_rows={content['missing_rows']}")
    if concepts["missing_rows"] != 0:
        problems.append(f"concepts missing_rows={concepts['missing_rows']}")
    invalid_indexes = {name: status for name, status in index_status.items() if status != "VALID"}
    if invalid_indexes:
        problems.append(f"invalid_indexes={invalid_indexes}")

    if problems:
        raise RuntimeError("Validation failed: " + "; ".join(problems))
    return 0


def _restore_scope_sql(config: ScopeConfig) -> str:
    if config.scope == CONTENT_SCOPE:
        return f"""
            UPDATE TOMEHUB_CONTENT_V2 dst
            SET VEC_EMBEDDING = (
                SELECT src.VEC_EMBEDDING
                FROM {config.backup_table} src
                WHERE src.ID = dst.ID
            )
            WHERE EXISTS (
                SELECT 1
                FROM {config.backup_table} src
                WHERE src.ID = dst.ID
            )
        """
    return f"""
        UPDATE TOMEHUB_CONCEPTS dst
        SET DESCRIPTION_EMBEDDING = (
            SELECT src.DESCRIPTION_EMBEDDING
            FROM {config.backup_table} src
            WHERE src.ID = dst.ID
        )
        WHERE EXISTS (
            SELECT 1
            FROM {config.backup_table} src
            WHERE src.ID = dst.ID
        )
    """


def run_restore(scope: str, execute: bool) -> int:
    configs = _normalize_scope(scope)
    payload = {
        "mode": "restore",
        "scope": scope,
        "execute": bool(execute),
        "rollback_hint": ROLLBACK_HINT,
        "sql": {config.scope: _restore_scope_sql(config) for config in configs},
    }

    if not execute:
        _print_json(payload)
        return 0

    _ensure_backend_not_running()
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                missing = [
                    config.backup_table
                    for config in configs
                    if not _table_exists(cursor, config.backup_table)
                ]
        if missing:
            raise RuntimeError(f"Missing backup table(s) for restore: {', '.join(missing)}")
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                for config in configs:
                    cursor.execute(_restore_scope_sql(config))
                conn.commit()
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"ALTER INDEX {CONTENT_INDEX_NAME} REBUILD")
                cursor.execute(f"ALTER INDEX {CONCEPT_INDEX_NAME} REBUILD")
                conn.commit()
    finally:
        DatabaseManager.close_pool()

    _print_json(payload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline in-place embedding rewriter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight", help="Show counts, estimates, and safety checks")
    preflight.add_argument("--target-tpm", type=int, default=24000)

    backup = subparsers.add_parser("backup", help="Create Oracle backup tables")
    backup.add_argument("--scope", choices=[CONTENT_SCOPE, CONCEPT_SCOPE, ALL_SCOPE], default=ALL_SCOPE)

    reembed = subparsers.add_parser("reembed", help="Re-embed rows in place")
    reembed.add_argument("--scope", choices=[CONTENT_SCOPE, CONCEPT_SCOPE, ALL_SCOPE], default=ALL_SCOPE)
    reembed.add_argument("--batch-size", type=int, default=20)
    reembed.add_argument("--target-tpm", type=int, default=24000)
    reembed.add_argument("--target-item-rpm", type=int, default=80)
    reembed.add_argument("--sleep-floor-ms", type=int, default=500)
    reembed.add_argument("--resume", action="store_true")

    rebuild = subparsers.add_parser("rebuild-indexes", help="Rebuild vector indexes")

    validate = subparsers.add_parser("validate", help="Validate coverage and index status")

    restore = subparsers.add_parser("restore", help="Print restore SQL or execute rollback")
    restore.add_argument("--scope", choices=[CONTENT_SCOPE, CONCEPT_SCOPE, ALL_SCOPE], default=ALL_SCOPE)
    restore.add_argument("--execute", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "preflight":
        return run_preflight(target_tpm=args.target_tpm)
    if args.command == "backup":
        return run_backup(scope=args.scope)
    if args.command == "reembed":
        return run_reembed(
            scope=args.scope,
            batch_size=max(1, int(args.batch_size)),
            target_tpm=max(1, int(args.target_tpm)),
            target_item_rpm=max(1, int(args.target_item_rpm)),
            sleep_floor_ms=max(0, int(args.sleep_floor_ms)),
            resume=bool(args.resume),
        )
    if args.command == "rebuild-indexes":
        return run_rebuild_indexes()
    if args.command == "validate":
        return run_validate()
    if args.command == "restore":
        return run_restore(scope=args.scope, execute=bool(args.execute))

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
