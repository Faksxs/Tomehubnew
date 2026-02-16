import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.epistemic_service import classify_chunk, extract_core_concepts
from utils.logger import get_logger

logger = get_logger("epistemic_distribution_service")

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_KEYS: set[Tuple[str, str]] = set()


def _is_missing_table_or_column(error: Exception) -> bool:
    text = str(error or "")
    return "ORA-00942" in text or "ORA-00904" in text


def refresh_epistemic_distribution(book_id: str, firebase_uid: str, max_chunks: int = 2500) -> Dict[str, Any]:
    if not book_id or not firebase_uid:
        return {"updated": False, "reason": "missing_identity"}

    rows: List[Any] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT CONTENT_CHUNK, SOURCE_TYPE
                    FROM TOMEHUB_CONTENT
                    WHERE BOOK_ID = :p_book
                      AND FIREBASE_UID = :p_uid
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_book": book_id, "p_uid": firebase_uid, "p_limit": max(50, int(max_chunks))},
                )
                rows = cursor.fetchall() or []
    except Exception as e:
        logger.warning("epistemic distribution read failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return {"updated": False, "reason": str(e)}

    if not rows:
        try:
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        DELETE FROM TOMEHUB_BOOK_EPISTEMIC_METRICS
                        WHERE BOOK_ID = :p_book AND FIREBASE_UID = :p_uid
                        """,
                        {"p_book": book_id, "p_uid": firebase_uid},
                    )
                conn.commit()
        except Exception as e:
            if not _is_missing_table_or_column(e):
                logger.warning("epistemic distribution cleanup failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return {"updated": True, "book_id": book_id, "firebase_uid": firebase_uid, "level_a": 0, "level_b": 0, "level_c": 0, "total": 0}

    a_count = 0
    b_count = 0
    c_count = 0

    for content_lob, source_type in rows:
        text = safe_read_clob(content_lob) if content_lob is not None else ""
        text = str(text or "").strip()
        if not text:
            continue
        keywords = extract_core_concepts(text[:380]) or []
        chunk = {
            "content_chunk": text,
            "source_type": str(source_type or "").strip().upper(),
            "title": "",
        }
        if keywords:
            level = classify_chunk(keywords, chunk)
        else:
            level = "C"
            chunk["epistemic_level"] = "C"

        level_norm = str(level or chunk.get("epistemic_level") or "C").strip().upper()
        if level_norm == "A":
            a_count += 1
        elif level_norm == "B":
            b_count += 1
        else:
            c_count += 1

    total = a_count + b_count + c_count
    now = datetime.utcnow()

    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    MERGE INTO TOMEHUB_BOOK_EPISTEMIC_METRICS t
                    USING (SELECT :p_book AS BOOK_ID, :p_uid AS FIREBASE_UID FROM DUAL) s
                    ON (t.BOOK_ID = s.BOOK_ID AND t.FIREBASE_UID = s.FIREBASE_UID)
                    WHEN MATCHED THEN UPDATE SET
                        LEVEL_A = :p_a,
                        LEVEL_B = :p_b,
                        LEVEL_C = :p_c,
                        TOTAL_CHUNKS = :p_total,
                        UPDATED_AT = :p_updated
                    WHEN NOT MATCHED THEN INSERT
                        (BOOK_ID, FIREBASE_UID, LEVEL_A, LEVEL_B, LEVEL_C, TOTAL_CHUNKS, UPDATED_AT)
                    VALUES
                        (:p_book, :p_uid, :p_a, :p_b, :p_c, :p_total, :p_updated)
                    """,
                    {
                        "p_book": book_id,
                        "p_uid": firebase_uid,
                        "p_a": a_count,
                        "p_b": b_count,
                        "p_c": c_count,
                        "p_total": total,
                        "p_updated": now,
                    },
                )
            conn.commit()
    except Exception as e:
        logger.warning("epistemic distribution upsert failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})
        return {"updated": False, "reason": str(e)}

    return {
        "updated": True,
        "book_id": book_id,
        "firebase_uid": firebase_uid,
        "level_a": a_count,
        "level_b": b_count,
        "level_c": c_count,
        "total": total,
    }


def maybe_trigger_epistemic_distribution_refresh_async(book_id: Optional[str], firebase_uid: Optional[str], reason: str = "ingest") -> bool:
    if not book_id or not firebase_uid:
        return False
    key = (str(firebase_uid), str(book_id))
    with _ACTIVE_LOCK:
        if key in _ACTIVE_KEYS:
            return False
        _ACTIVE_KEYS.add(key)

    def _worker() -> None:
        try:
            refresh_epistemic_distribution(str(book_id), str(firebase_uid))
        except Exception as e:
            logger.warning("epistemic distribution worker failed", extra={"book_id": book_id, "uid": firebase_uid, "reason": reason, "error": str(e)})
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE_KEYS.discard(key)

    threading.Thread(target=_worker, daemon=True).start()
    return True


def delete_epistemic_distribution(book_id: str, firebase_uid: str) -> None:
    if not book_id or not firebase_uid:
        return
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM TOMEHUB_BOOK_EPISTEMIC_METRICS WHERE BOOK_ID = :p_book AND FIREBASE_UID = :p_uid",
                    {"p_book": book_id, "p_uid": firebase_uid},
                )
            conn.commit()
    except Exception as e:
        if not _is_missing_table_or_column(e):
            logger.warning("epistemic distribution delete failed", extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)})


def get_epistemic_distribution(firebase_uid: str, book_id: Optional[str] = None, limit: int = 250) -> Dict[str, Any]:
    if not firebase_uid:
        return {"items": [], "count": 0}

    items: List[Dict[str, Any]] = []
    safe_limit = max(1, min(int(limit or 250), 1000))
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                if book_id:
                    cursor.execute(
                        """
                        SELECT BOOK_ID, LEVEL_A, LEVEL_B, LEVEL_C, TOTAL_CHUNKS, UPDATED_AT
                        FROM TOMEHUB_BOOK_EPISTEMIC_METRICS
                        WHERE FIREBASE_UID = :p_uid AND BOOK_ID = :p_book
                        FETCH FIRST :p_limit ROWS ONLY
                        """,
                        {"p_uid": firebase_uid, "p_book": book_id, "p_limit": safe_limit},
                    )
                else:
                    cursor.execute(
                        """
                        SELECT BOOK_ID, LEVEL_A, LEVEL_B, LEVEL_C, TOTAL_CHUNKS, UPDATED_AT
                        FROM TOMEHUB_BOOK_EPISTEMIC_METRICS
                        WHERE FIREBASE_UID = :p_uid
                        ORDER BY UPDATED_AT DESC
                        FETCH FIRST :p_limit ROWS ONLY
                        """,
                        {"p_uid": firebase_uid, "p_limit": safe_limit},
                    )
                rows = cursor.fetchall() or []
                for row in rows:
                    level_a = int(row[1] or 0)
                    level_b = int(row[2] or 0)
                    level_c = int(row[3] or 0)
                    total = int(row[4] or (level_a + level_b + level_c) or 0)
                    items.append(
                        {
                            "book_id": str(row[0]),
                            "level_a": level_a,
                            "level_b": level_b,
                            "level_c": level_c,
                            "total_chunks": total,
                            "ratio_a": round((level_a / total), 4) if total > 0 else 0.0,
                            "ratio_b": round((level_b / total), 4) if total > 0 else 0.0,
                            "ratio_c": round((level_c / total), 4) if total > 0 else 0.0,
                            "updated_at": row[5].isoformat() if row[5] else None,
                        }
                    )
    except Exception as e:
        if _is_missing_table_or_column(e):
            return {"items": [], "count": 0}
        logger.warning("epistemic distribution read failed", extra={"uid": firebase_uid, "book_id": book_id, "error": str(e)})
        return {"items": [], "count": 0, "error": str(e)}

    return {"items": items, "count": len(items)}
