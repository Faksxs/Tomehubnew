from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager
from models.firestore_sync_models import StrictFirestoreItem, normalize_and_validate_item
from services.ingestion_service import ingest_text_item, sync_highlights_for_item, sync_personal_note_for_item
from services.monitoring import (
    EMBEDDING_BACKFILL_COST_ESTIMATE,
    EMBEDDING_BACKFILL_QUEUE_DEPTH,
    EMBEDDING_BACKFILL_TOTAL_CALLS,
)
from utils.logger import get_logger

logger = get_logger("firestore_sync_service")

_sync_lock = threading.Lock()
_FIRESTORE_DB_SYNC_ENABLED = str(os.getenv("FIRESTORE_DB_SYNC_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
_sync_status: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "job_id": None,
    "scope_uid": None,
    "dry_run": True,
    "processed": 0,
    "synced": 0,
    "failed": 0,
    "quarantined": 0,
    "skipped_non_ideas_notes": 0,
    "remaining_missing": None,
    "errors": [],
    "idempotency_keys": 0,
    "embedding_calls_total": 0,
    "embedding_cost_estimate": 0.0,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_firestore_items(firebase_uid: str) -> Dict[str, Dict[str, Any]]:
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError("FIREBASE_READY is false; configure Firebase Admin first.")

    from firebase_admin import firestore

    db = firestore.client()
    docs = (
        db.collection("users")
        .document(firebase_uid)
        .collection("items")
        .stream()
    )
    out: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        out[str(doc.id)] = doc.to_dict() or {}
    return out


def _load_oracle_book_ids(firebase_uid: str) -> set[str]:
    out: set[str] = set()
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ITEM_ID
                FROM TOMEHUB_CONTENT_V2
                WHERE firebase_uid = :p_uid
                  AND ITEM_ID IS NOT NULL
                """,
                {"p_uid": firebase_uid},
            )
            for row in cursor.fetchall():
                bid = str(row[0] or "").strip()
                if bid:
                    out.add(bid)
    return out


def _build_item_text(item: StrictFirestoreItem) -> str:
    parts: list[str] = [f"Title: {item.title}", f"Author: {item.author}"]
    if item.publisher:
        parts.append(f"Publisher: {item.publisher}")
    if item.tags:
        parts.append(f"Tags: {', '.join(item.tags)}")
    if item.generalNotes:
        parts.append(f"Content/Notes: {item.generalNotes}")
    text = "\n".join(parts).strip()
    return text if len(text) >= 12 else f"Title: {item.title}\nAuthor: {item.author}"






def _upsert_library_item_meta(cursor, uid: str, item: StrictFirestoreItem):
    try:
        tags_json = json.dumps(item.tags, ensure_ascii=False) if item.tags else None
        
        category_json = None
        if hasattr(item, 'categories') and item.categories:
            category_json = json.dumps(item.categories, ensure_ascii=False)
        elif hasattr(item, 'tags') and item.tags:
            # Fallback for frontend design where categories are just the first tags
            category_json = json.dumps(item.tags, ensure_ascii=False)
            
        sql = '''
        MERGE INTO TOMEHUB_LIBRARY_ITEMS li
        USING (SELECT :p_id AS item_id, :p_uid AS firebase_uid FROM DUAL) src
        ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
        WHEN NOT MATCHED THEN
            INSERT (
                ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, PUBLISHER, 
                TRANSLATOR, PUBLICATION_YEAR, ISBN, SOURCE_URL, PAGE_COUNT, COVER_URL,
                SUMMARY_TEXT, TAGS_JSON, CATEGORY_JSON, 
                READING_STATUS, INVENTORY_STATUS, IS_FAVORITE, PERSONAL_NOTE_CATEGORY, 
                CONTENT_LANGUAGE_MODE, CONTENT_LANGUAGE_RESOLVED, SOURCE_LANGUAGE_HINT,
                LANGUAGE_DECISION_REASON, LANGUAGE_DECISION_CONFIDENCE,
                PERSONAL_FOLDER_ID, FOLDER_PATH,
                ORIGIN_SYSTEM, CREATED_AT, UPDATED_AT
            ) VALUES (
                :p_id, :p_uid, CAST(:p_type AS VARCHAR2(50)), CAST(:p_title AS VARCHAR2(1000)), 
                CAST(:p_author AS VARCHAR2(1000)), CAST(:p_publisher AS VARCHAR2(255)),
                CAST(:p_translator AS VARCHAR2(255)), CAST(:p_pub_year AS NUMBER), 
                CAST(:p_isbn AS VARCHAR2(255)), CAST(:p_url AS VARCHAR2(2000)),
                CAST(:p_page_count AS NUMBER), CAST(:p_cover_url AS VARCHAR2(2000)),
                CASE WHEN :p_summary IS NOT NULL THEN TO_CLOB(:p_summary) ELSE NULL END,
                CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE NULL END,
                CASE WHEN :p_category_json IS NOT NULL THEN TO_CLOB(:p_category_json) ELSE NULL END,
                CAST(:p_read_status AS VARCHAR2(50)), CAST(:p_phys_status AS VARCHAR2(100)), 
                CAST(:p_fav AS NUMBER), CAST(:p_category AS VARCHAR2(50)),
                CAST(:p_lang_mode AS VARCHAR2(50)), CAST(:p_lang_res AS VARCHAR2(50)), CAST(:p_lang_hint AS VARCHAR2(50)),
                CAST(:p_lang_reason AS VARCHAR2(255)), CAST(:p_lang_conf AS NUMBER),
                CAST(:p_folder_id AS VARCHAR2(255)), CASE WHEN :p_folder_path IS NOT NULL THEN TO_CLOB(:p_folder_path) ELSE NULL END,
                'FIRESTORE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        WHEN MATCHED THEN
            UPDATE SET
                ITEM_TYPE = COALESCE(CAST(:p_type AS VARCHAR2(50)), li.ITEM_TYPE),
                TITLE = COALESCE(CAST(:p_title AS VARCHAR2(1000)), li.TITLE),
                AUTHOR = COALESCE(CAST(:p_author AS VARCHAR2(1000)), li.AUTHOR),
                PUBLISHER = COALESCE(CAST(:p_publisher AS VARCHAR2(255)), li.PUBLISHER),
                TRANSLATOR = COALESCE(CAST(:p_translator AS VARCHAR2(255)), li.TRANSLATOR),
                PUBLICATION_YEAR = COALESCE(CAST(:p_pub_year AS NUMBER), li.PUBLICATION_YEAR),
                ISBN = COALESCE(CAST(:p_isbn AS VARCHAR2(255)), li.ISBN),
                SOURCE_URL = COALESCE(CAST(:p_url AS VARCHAR2(2000)), li.SOURCE_URL),
                PAGE_COUNT = COALESCE(CAST(:p_page_count AS NUMBER), li.PAGE_COUNT),
                COVER_URL = COALESCE(CAST(:p_cover_url AS VARCHAR2(2000)), li.COVER_URL),
                SUMMARY_TEXT = CASE WHEN :p_summary IS NOT NULL THEN TO_CLOB(:p_summary) ELSE li.SUMMARY_TEXT END,
                TAGS_JSON = CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE li.TAGS_JSON END,
                CATEGORY_JSON = CASE WHEN :p_category_json IS NOT NULL THEN TO_CLOB(:p_category_json) ELSE li.CATEGORY_JSON END,
                READING_STATUS = COALESCE(CAST(:p_read_status AS VARCHAR2(50)), li.READING_STATUS),
                INVENTORY_STATUS = COALESCE(CAST(:p_phys_status AS VARCHAR2(100)), li.INVENTORY_STATUS),
                IS_FAVORITE = COALESCE(CAST(:p_fav AS NUMBER), li.IS_FAVORITE),
                PERSONAL_NOTE_CATEGORY = COALESCE(CAST(:p_category AS VARCHAR2(50)), li.PERSONAL_NOTE_CATEGORY),
                CONTENT_LANGUAGE_MODE = COALESCE(CAST(:p_lang_mode AS VARCHAR2(50)), li.CONTENT_LANGUAGE_MODE),
                CONTENT_LANGUAGE_RESOLVED = COALESCE(CAST(:p_lang_res AS VARCHAR2(50)), li.CONTENT_LANGUAGE_RESOLVED),
                SOURCE_LANGUAGE_HINT = COALESCE(CAST(:p_lang_hint AS VARCHAR2(50)), li.SOURCE_LANGUAGE_HINT),
                LANGUAGE_DECISION_REASON = COALESCE(CAST(:p_lang_reason AS VARCHAR2(255)), li.LANGUAGE_DECISION_REASON),
                LANGUAGE_DECISION_CONFIDENCE = COALESCE(CAST(:p_lang_conf AS NUMBER), li.LANGUAGE_DECISION_CONFIDENCE),
                PERSONAL_FOLDER_ID = COALESCE(CAST(:p_folder_id AS VARCHAR2(255)), li.PERSONAL_FOLDER_ID),
                FOLDER_PATH = CASE WHEN :p_folder_path IS NOT NULL THEN TO_CLOB(:p_folder_path) ELSE li.FOLDER_PATH END,
                UPDATED_AT = CURRENT_TIMESTAMP
        '''
        
        # safely extract from model
        translator = getattr(item, 'translator', None)
        pub_year = getattr(item, 'publicationYear', None)
        isbn = getattr(item, 'isbn', None)
        url = getattr(item, 'url', None)
        page_count = getattr(item, 'pageCount', None)
        cover_url = getattr(item, 'coverUrl', None)
        summary = getattr(item, 'summary', None)
        reading_status = getattr(item, 'readingStatus', None)
        phys_status = getattr(item, 'status', None)
        is_fav = 1 if getattr(item, 'isFavorite', False) else 0

        lang_mode = getattr(item, 'contentLanguageMode', None)
        lang_res = getattr(item, 'contentLanguageResolved', None)
        lang_hint = getattr(item, 'sourceLanguageHint', None)
        lang_reason = getattr(item, 'languageDecisionReason', None)
        lang_conf = getattr(item, 'languageDecisionConfidence', None)
        folder_id = getattr(item, 'personalFolderId', None)
        folder_path = getattr(item, 'folderPath', None)

        cursor.execute(sql, {
            "p_id": item.book_id,
            "p_uid": uid,
            "p_type": item.type or 'BOOK',
            "p_title": item.title,
            "p_author": item.author,
            "p_publisher": item.publisher,
            "p_translator": translator,
            "p_pub_year": pub_year,
            "p_isbn": isbn,
            "p_url": url,
            "p_page_count": page_count,
            "p_cover_url": cover_url,
            "p_summary": summary,
            "p_tags": tags_json,
            "p_category_json": category_json,
            "p_read_status": reading_status,
            "p_phys_status": phys_status,
            "p_fav": is_fav,
            "p_category": item.personalNoteCategory,
            "p_lang_mode": lang_mode,
            "p_lang_res": lang_res,
            "p_lang_hint": lang_hint,
            "p_lang_reason": lang_reason,
            "p_lang_conf": lang_conf,
            "p_folder_id": folder_id,
            "p_folder_path": folder_path
        })
    except Exception as e:
        logger.warning(f"Failed to upsert library item metadata for {item.book_id}: {e}")


def _write_quarantine(uid: str, item_id: str, raw_item: Dict[str, Any], reason: str) -> None:
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", "firestore_sync_quarantine.jsonl")
    payload = {
        "at": _utc_now(),
        "uid": uid,
        "item_id": item_id,
        "reason": reason,
        "raw": raw_item,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _rate_limit(last_call_at: float, rpm_cap: int) -> float:
    if rpm_cap <= 0:
        return time.time()
    min_interval = 60.0 / float(rpm_cap)
    now = time.time()
    delta = now - last_call_at
    if delta < min_interval:
        time.sleep(min_interval - delta)
    return time.time()


def _set_status(**kwargs: Any) -> None:
    with _sync_lock:
        _sync_status.update(kwargs)


def get_firestore_oracle_sync_status() -> Dict[str, Any]:
    with _sync_lock:
        return dict(_sync_status)


def _sync_uid_worker(
    scope_uid: str,
    *,
    dry_run: bool,
    max_items: int,
    embedding_rpm_cap: int,
    embedding_unit_cost_usd: float,
) -> None:
    _set_status(
        running=True,
        started_at=_utc_now(),
        finished_at=None,
        scope_uid=scope_uid,
        dry_run=dry_run,
        processed=0,
        synced=0,
        failed=0,
        quarantined=0,
        skipped_non_ideas_notes=0,
        remaining_missing=None,
        errors=[],
        idempotency_keys=0,
        embedding_calls_total=0,
        embedding_cost_estimate=0.0,
    )
    idempotency_seen: set[str] = set()
    last_embed_call_at = 0.0

    try:
        DatabaseManager.init_pool()
        firestore_items = _load_firestore_items(scope_uid)
        fs_ids = set(firestore_items.keys())
        oracle_ids = _load_oracle_book_ids(scope_uid)
        missing_ids = sorted(fs_ids - oracle_ids)
        if max_items > 0:
            missing_ids = missing_ids[:max_items]

        EMBEDDING_BACKFILL_QUEUE_DEPTH.set(len(missing_ids))
        type_counter = Counter(
            str((firestore_items.get(item_id) or {}).get("type") or "UNKNOWN").upper()
            for item_id in missing_ids
        )
        logger.info("firestore->oracle sync start", extra={"uid": scope_uid, "missing": len(missing_ids), "by_type": dict(type_counter)})

        for item_id in missing_ids:
            raw_item = firestore_items.get(item_id) or {}
            _set_status(processed=int(_sync_status["processed"]) + 1)

            try:
                item = normalize_and_validate_item(item_id, raw_item)
            except Exception as e:
                _set_status(
                    quarantined=int(_sync_status["quarantined"]) + 1,
                    errors=[*_sync_status["errors"], f"{item_id}:validation:{str(e)}"][-100:],
                )
                _write_quarantine(scope_uid, item_id, raw_item, f"validation_error:{e}")
                continue

            idem_key = f"{scope_uid}:{item.book_id}:{item.entity_hash()}"
            if idem_key in idempotency_seen:
                continue
            idempotency_seen.add(idem_key)
            _set_status(idempotency_keys=len(idempotency_seen))

            # Upsert library item FULL metadata early
            try:
                with DatabaseManager.get_write_connection() as _conn:
                    with _conn.cursor() as _cursor:
                        _upsert_library_item_meta(_cursor, scope_uid, item)
                    _conn.commit()
            except Exception as meta_ex:
                logger.warning(f"Meta upsert failed: {meta_ex}")

            try:
                if dry_run:
                    continue

                if item.type == "PERSONAL_NOTE":
                    last_embed_call_at = _rate_limit(last_embed_call_at, embedding_rpm_cap)
                    result = sync_personal_note_for_item(
                        firebase_uid=scope_uid,
                        book_id=item.book_id,
                        title=item.title,
                        author=item.author,
                        content=item.generalNotes,
                        tags=item.tags,
                        category=item.personalNoteCategory,
                        delete_only=False,
                    )
                    if not result.get("success"):
                        raise RuntimeError(result.get("error", "sync_personal_note_failed"))
                    embed_calls = 1
                else:
                    text = _build_item_text(item)
                    last_embed_call_at = _rate_limit(last_embed_call_at, embedding_rpm_cap)
                    ok = ingest_text_item(
                        text=text,
                        title=item.title,
                        author=item.author,
                        source_type=item.type or "BOOK",
                        firebase_uid=scope_uid,
                        book_id=item.book_id,
                        tags=item.tags,
                    )
                    if not ok:
                        raise RuntimeError("ingest_text_item_failed")
                    embed_calls = 1

                if item.highlights:
                    last_embed_call_at = _rate_limit(last_embed_call_at, embedding_rpm_cap)
                    h_result = sync_highlights_for_item(
                        firebase_uid=scope_uid,
                        book_id=item.book_id,
                        title=item.title,
                        author=item.author,
                        highlights=[h.model_dump() for h in item.highlights],
                    )
                    if not h_result.get("success"):
                        raise RuntimeError(h_result.get("error", "sync_highlights_failed"))
                    embed_calls += len(item.highlights)

                new_calls = int(_sync_status["embedding_calls_total"]) + embed_calls
                new_cost = float(new_calls) * float(embedding_unit_cost_usd)
                _set_status(
                    synced=int(_sync_status["synced"]) + 1,
                    embedding_calls_total=new_calls,
                    embedding_cost_estimate=round(new_cost, 6),
                )
                EMBEDDING_BACKFILL_TOTAL_CALLS.inc(embed_calls)
                EMBEDDING_BACKFILL_COST_ESTIMATE.set(float(round(new_cost, 6)))
            except Exception as e:
                _set_status(
                    failed=int(_sync_status["failed"]) + 1,
                    errors=[*_sync_status["errors"], f"{item_id}:sync:{str(e)}"][-100:],
                )
                logger.warning("sync failed", extra={"uid": scope_uid, "item_id": item_id, "error": str(e)})

        remaining_ids = _load_oracle_book_ids(scope_uid)
        expected_present_ids: set[str] = set()
        for item_id, raw in firestore_items.items():
            try:
                item = normalize_and_validate_item(item_id, raw)
                expected_present_ids.add(item_id)
            except Exception:
                continue
        still_missing = len(expected_present_ids - remaining_ids)
        _set_status(remaining_missing=still_missing)
    except Exception as e:
        _set_status(errors=[*_sync_status["errors"], f"fatal:{str(e)}"][-100:])
        logger.exception("firestore->oracle sync worker crashed")
    finally:
        EMBEDDING_BACKFILL_QUEUE_DEPTH.set(0)
        _set_status(running=False, finished_at=_utc_now())
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def start_firestore_oracle_sync_async(
    *,
    scope_uid: str,
    dry_run: bool = True,
    max_items: int = 0,
    embedding_rpm_cap: int = 30,
    embedding_unit_cost_usd: float = 0.00002,
) -> Dict[str, Any]:
    if not _FIRESTORE_DB_SYNC_ENABLED:
        _set_status(
            running=False,
            finished_at=_utc_now(),
            errors=[*_sync_status.get("errors", []), "firestore_db_sync_disabled"][-100:],
        )
        logger.warning("firestore->oracle sync blocked: FIRESTORE_DB_SYNC_ENABLED is false")
        return dict(_sync_status)

    with _sync_lock:
        if _sync_status.get("running"):
            return dict(_sync_status)
        job_id = f"sync-{int(time.time())}"
        _sync_status["job_id"] = job_id

    th = threading.Thread(
        target=_sync_uid_worker,
        kwargs={
            "scope_uid": scope_uid,
            "dry_run": bool(dry_run),
            "max_items": int(max_items),
            "embedding_rpm_cap": int(embedding_rpm_cap),
            "embedding_unit_cost_usd": float(embedding_unit_cost_usd),
        },
        daemon=True,
        name=f"firestore-oracle-sync-{scope_uid[:8]}",
    )
    th.start()
    return get_firestore_oracle_sync_status()
