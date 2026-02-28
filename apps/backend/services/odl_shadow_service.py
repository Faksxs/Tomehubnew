import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.correction_service import LinguisticCorrectionService
from services.data_cleaner_service import DataCleanerService
from services.data_health_service import DataHealthService
from services.monitoring import (
    ODL_SHADOW_JOBS_TOTAL,
    ODL_SHADOW_JOB_DURATION_SECONDS,
    ODL_SHADOW_READY_COUNT,
)
from services.pdf_service import calculate_sis
from utils.logger import get_logger
from utils.text_utils import get_lemma_frequencies, get_lemmas, normalize_text

logger = get_logger("odl_shadow_service")

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_KEYS: set[Tuple[str, str]] = set()
_CORRECTOR_LOCK = threading.Lock()
_CORRECTOR: Optional[LinguisticCorrectionService] = None


def _get_corrector() -> LinguisticCorrectionService:
    global _CORRECTOR
    if _CORRECTOR is not None:
        return _CORRECTOR
    with _CORRECTOR_LOCK:
        if _CORRECTOR is None:
            _CORRECTOR = LinguisticCorrectionService()
    return _CORRECTOR


def _is_missing_table_or_column(error: Exception) -> bool:
    text = str(error or "")
    return "ORA-00942" in text or "ORA-00904" in text


def _target_allowed(firebase_uid: str, item_id: Optional[str]) -> bool:
    if not bool(getattr(settings, "ODL_SECONDARY_ENABLED", False)):
        return False

    uid_allow = set(getattr(settings, "ODL_SECONDARY_UID_ALLOWLIST", set()) or set())
    if uid_allow and str(firebase_uid or "").strip() not in uid_allow:
        return False

    book_allow = set(getattr(settings, "ODL_SECONDARY_BOOK_ALLOWLIST", set()) or set())
    if book_allow:
        bid = str(item_id or "").strip()
        if not bid or bid not in book_allow:
            return False

    return True


def should_enable_odl_secondary_for_target(firebase_uid: str, item_id: Optional[str]) -> bool:
    return _target_allowed(firebase_uid=firebase_uid, item_id=item_id)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            buf = f.read(1024 * 1024)
            if not buf:
                break
            digest.update(buf)
    return digest.hexdigest()


def _extract_with_odl(pdf_path: str, output_dir: str) -> List[Dict[str, Any]]:
    try:
        import opendataloader_pdf  # type: ignore
    except Exception as e:
        raise RuntimeError(f"opendataloader_pdf import failed: {e}") from e

    opendataloader_pdf.convert(
        input_path=pdf_path,
        output_dir=output_dir,
        format="json",
        quiet=True,
    )

    stem = Path(pdf_path).stem
    default_json = Path(output_dir) / f"{stem}.json"
    if default_json.exists():
        json_path = default_json
    else:
        candidates = sorted(Path(output_dir).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise RuntimeError(f"ODL JSON output not found in {output_dir}")
        json_path = candidates[0]

    with json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    kids = payload.get("kids") or []
    if not isinstance(kids, list):
        return []
    return kids


def _project_odl_rows(
    kids: List[Dict[str, Any]],
    *,
    firebase_uid: str,
    item_id: str,
    title: str,
    odl_version: str,
    postprocess_version: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    stats = {
        "raw_input_elements": len(kids),
        "raw_non_empty": 0,
        "dropped_invalid_before_clean": 0,
        "dropped_sis_quarantine_before_clean": 0,
        "dropped_invalid_after_clean": 0,
        "kept_after_tomehub_postprocess": 0,
    }

    for idx, item in enumerate(kids):
        raw_text = str(item.get("content") or "").strip()
        if not raw_text:
            continue
        stats["raw_non_empty"] += 1

        if not DataHealthService.validate_content(raw_text):
            stats["dropped_invalid_before_clean"] += 1
            continue

        sis = calculate_sis(raw_text)
        if str(sis.get("decision", "")).upper() == "QUARANTINE":
            stats["dropped_sis_quarantine_before_clean"] += 1
            continue

        repaired = _get_corrector().fix_text(raw_text)
        cleaned = DataCleanerService.strip_basic_patterns(repaired)
        if not DataHealthService.validate_content(cleaned):
            stats["dropped_invalid_after_clean"] += 1
            continue

        normalized = normalize_text(cleaned)
        content_hash = hashlib.sha1((normalized or cleaned).encode("utf-8", errors="ignore")).hexdigest()
        page_number = item.get("page number")
        quality = {
            "sis_score": sis.get("score"),
            "sis_decision": sis.get("decision"),
            "raw_len": len(raw_text),
            "clean_len": len(cleaned),
        }
        rows.append(
            {
                "firebase_uid": firebase_uid,
                "item_id": item_id,
                "title": title,
                "content_chunk": cleaned,
                "page_number": int(page_number) if page_number is not None else None,
                "chunk_index": idx,
                "normalized_content": normalized,
                "lemma_tokens": json.dumps(get_lemmas(cleaned), ensure_ascii=False),
                "token_freq": json.dumps(get_lemma_frequencies(cleaned), ensure_ascii=False),
                "content_hash": content_hash,
                "odl_version": odl_version,
                "postprocess_version": postprocess_version,
                "quality_metrics_json": json.dumps(quality, ensure_ascii=False),
            }
        )
        stats["kept_after_tomehub_postprocess"] += 1

    return rows, stats


def _upsert_status(
    *,
    firebase_uid: str,
    item_id: str,
    checksum: str,
    odl_version: str,
    status: str,
    chunk_count: int = 0,
    error_text: Optional[str] = None,
) -> None:
    sql = """
        MERGE INTO TOMEHUB_ODL_SHADOW_STATUS s
        USING (
            SELECT
                :p_uid AS firebase_uid,
                :p_item AS item_id,
                :p_checksum AS pdf_checksum,
                :p_odl_version AS odl_version
            FROM DUAL
        ) src
        ON (
            s.FIREBASE_UID = src.firebase_uid
            AND s.ITEM_ID = src.item_id
            AND s.PDF_CHECKSUM = src.pdf_checksum
            AND s.ODL_VERSION = src.odl_version
        )
        WHEN MATCHED THEN UPDATE SET
            STATUS = :p_status,
            CHUNK_COUNT = :p_chunk_count,
            ERROR_TEXT = :p_error_text,
            UPDATED_AT = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT (
            FIREBASE_UID, ITEM_ID, PDF_CHECKSUM, ODL_VERSION, STATUS, CHUNK_COUNT, ERROR_TEXT, UPDATED_AT
        ) VALUES (
            :p_uid, :p_item, :p_checksum, :p_odl_version, :p_status, :p_chunk_count, :p_error_text, CURRENT_TIMESTAMP
        )
    """
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                {
                    "p_uid": firebase_uid,
                    "p_item": item_id,
                    "p_checksum": checksum,
                    "p_odl_version": odl_version,
                    "p_status": status,
                    "p_chunk_count": int(chunk_count or 0),
                    "p_error_text": (error_text or "")[:4000] if error_text else None,
                },
            )
        conn.commit()


def _write_shadow_rows(
    *,
    firebase_uid: str,
    item_id: str,
    rows: List[Dict[str, Any]],
) -> None:
    delete_sql = """
        DELETE FROM TOMEHUB_CONTENT_ODL_SHADOW
        WHERE FIREBASE_UID = :p_uid AND ITEM_ID = :p_item
    """
    insert_sql = """
        INSERT INTO TOMEHUB_CONTENT_ODL_SHADOW
        (
            FIREBASE_UID, ITEM_ID, TITLE, CONTENT_CHUNK, PAGE_NUMBER, CHUNK_INDEX,
            NORMALIZED_CONTENT, LEMMA_TOKENS, TOKEN_FREQ, CONTENT_HASH,
            ODL_VERSION, POSTPROCESS_VERSION, QUALITY_METRICS_JSON, CREATED_AT
        )
        VALUES
        (
            :p_uid, :p_item, :p_title, :p_content, :p_page, :p_chunk_idx,
            :p_norm, :p_lemmas, :p_token_freq, :p_hash,
            :p_odl_version, :p_post_ver, :p_quality, CURRENT_TIMESTAMP
        )
    """
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(delete_sql, {"p_uid": firebase_uid, "p_item": item_id})
            for row in rows:
                cursor.execute(
                    insert_sql,
                    {
                        "p_uid": row["firebase_uid"],
                        "p_item": row["item_id"],
                        "p_title": row["title"],
                        "p_content": row["content_chunk"],
                        "p_page": row["page_number"],
                        "p_chunk_idx": row["chunk_index"],
                        "p_norm": row["normalized_content"],
                        "p_lemmas": row["lemma_tokens"],
                        "p_token_freq": row["token_freq"],
                        "p_hash": row["content_hash"],
                        "p_odl_version": row["odl_version"],
                        "p_post_ver": row["postprocess_version"],
                        "p_quality": row["quality_metrics_json"],
                    },
                )
        conn.commit()


def _ingest_odl_shadow_worker(
    *,
    local_pdf_path: str,
    temp_dir: str,
    firebase_uid: str,
    item_id: str,
    title: str,
    checksum: str,
    odl_version: str,
    postprocess_version: str,
) -> None:
    start = time.perf_counter()
    key = (firebase_uid, item_id)
    job_status = "success"
    try:
        _upsert_status(
            firebase_uid=firebase_uid,
            item_id=item_id,
            checksum=checksum,
            odl_version=odl_version,
            status="PENDING",
        )
    except Exception as e:
        if not _is_missing_table_or_column(e):
            logger.warning("ODL shadow status upsert failed (pending)", extra={"error": str(e)})

    try:
        kids = _extract_with_odl(local_pdf_path, temp_dir)
        rows, stats = _project_odl_rows(
            kids,
            firebase_uid=firebase_uid,
            item_id=item_id,
            title=title,
            odl_version=odl_version,
            postprocess_version=postprocess_version,
        )
        _write_shadow_rows(firebase_uid=firebase_uid, item_id=item_id, rows=rows)
        try:
            _upsert_status(
                firebase_uid=firebase_uid,
                item_id=item_id,
                checksum=checksum,
                odl_version=odl_version,
                status="READY",
                chunk_count=len(rows),
            )
        except Exception as e:
            if not _is_missing_table_or_column(e):
                logger.warning("ODL shadow status upsert failed (ready)", extra={"error": str(e)})
        try:
            ODL_SHADOW_JOBS_TOTAL.labels(status="success").inc()
            ODL_SHADOW_READY_COUNT.labels(firebase_uid=firebase_uid, item_id=item_id).set(float(len(rows)))
        except Exception:
            pass
        logger.info(
            "ODL shadow ingestion completed",
            extra={
                "firebase_uid": firebase_uid,
                "item_id": item_id,
                "chunk_count": len(rows),
                "stats": stats,
            },
        )
    except Exception as e:
        job_status = "failed"
        err_text = str(e)
        logger.warning(
            "ODL shadow ingestion failed (non-critical)",
            extra={"firebase_uid": firebase_uid, "item_id": item_id, "error": err_text},
        )
        try:
            _upsert_status(
                firebase_uid=firebase_uid,
                item_id=item_id,
                checksum=checksum,
                odl_version=odl_version,
                status="FAILED",
                chunk_count=0,
                error_text=err_text,
            )
        except Exception as status_err:
            if not _is_missing_table_or_column(status_err):
                logger.warning("ODL shadow status upsert failed (failed)", extra={"error": str(status_err)})
        try:
            ODL_SHADOW_JOBS_TOTAL.labels(status="failed").inc()
        except Exception:
            pass
    finally:
        elapsed = time.perf_counter() - start
        try:
            ODL_SHADOW_JOB_DURATION_SECONDS.labels(status=job_status).observe(elapsed)
        except Exception:
            pass
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        with _ACTIVE_LOCK:
            _ACTIVE_KEYS.discard(key)


def maybe_trigger_odl_shadow_ingestion_async(
    *,
    file_path: str,
    title: str,
    author: str,
    firebase_uid: str,
    item_id: Optional[str],
) -> bool:
    if not bool(getattr(settings, "ODL_SHADOW_INGEST_ENABLED", False)):
        return False
    if not _target_allowed(firebase_uid=firebase_uid, item_id=item_id):
        return False

    bid = str(item_id or "").strip()
    if not bid:
        return False

    src = str(file_path or "").strip()
    if not src or not src.lower().endswith(".pdf"):
        return False
    if not os.path.exists(src):
        return False

    key = (firebase_uid, bid)
    with _ACTIVE_LOCK:
        if key in _ACTIVE_KEYS:
            return False
        _ACTIVE_KEYS.add(key)

    staging_dir = tempfile.mkdtemp(prefix="odl_shadow_")
    local_pdf_path = os.path.join(staging_dir, os.path.basename(src))
    try:
        shutil.copy2(src, local_pdf_path)
    except Exception as e:
        with _ACTIVE_LOCK:
            _ACTIVE_KEYS.discard(key)
        shutil.rmtree(staging_dir, ignore_errors=True)
        logger.warning("ODL shadow staging copy failed", extra={"error": str(e)})
        return False

    try:
        checksum = _sha256_file(local_pdf_path)
    except Exception:
        checksum = hashlib.sha1(local_pdf_path.encode("utf-8", errors="ignore")).hexdigest()

    composed_title = f"{title} - {author}" if author else str(title or "")
    odl_version = str(getattr(settings, "ODL_EXTRACTOR_VERSION", "opendataloader-pdf") or "opendataloader-pdf")
    postprocess_version = str(getattr(settings, "ODL_POSTPROCESS_VERSION", "v1") or "v1")
    t = threading.Thread(
        target=_ingest_odl_shadow_worker,
        kwargs={
            "local_pdf_path": local_pdf_path,
            "temp_dir": staging_dir,
            "firebase_uid": firebase_uid,
            "item_id": bid,
            "title": composed_title,
            "checksum": checksum,
            "odl_version": odl_version,
            "postprocess_version": postprocess_version,
        },
        daemon=True,
    )
    t.start()
    return True
