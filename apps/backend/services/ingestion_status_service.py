from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any, Dict, Iterable, Optional

from infrastructure.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

_COLUMN_CACHE: Optional[set[str]] = None
_TERMINAL_PARSE_STATUSES = {"COMPLETED", "FAILED"}

_FIELD_TO_COLUMN = {
    "file_name": "SOURCE_FILE_NAME",
    "status": "STATUS",
    "chunk_count": "CHUNK_COUNT",
    "embedding_count": "EMBEDDING_COUNT",
    "storage_backend": "STORAGE_BACKEND",
    "bucket_name": "BUCKET_NAME",
    "object_key": "OBJECT_KEY",
    "size_bytes": "SIZE_BYTES",
    "storage_status": "STORAGE_STATUS",
    "parse_path": "PARSE_PATH",
    "parse_status": "PARSE_STATUS",
    "oci_job_id": "OCI_JOB_ID",
    "oci_output_prefix": "OCI_OUTPUT_PREFIX",
    "storage_warning": "STORAGE_WARNING",
    "content_type": "CONTENT_TYPE",
    "mime_type": "MIME_TYPE",
    "sha256": "SHA256",
    "error_message": "ERROR_MESSAGE",
    "classification_route": "CLASSIFICATION_ROUTE",
    "parse_engine": "PARSE_ENGINE",
    "fallback_engine": "FALLBACK_ENGINE",
    "classifier_metrics_json": "CLASSIFIER_METRICS_JSON",
    "quality_metrics_json": "QUALITY_METRICS_JSON",
    "routing_metrics_json": "ROUTING_METRICS_JSON",
    "parse_time_ms": "PARSE_TIME_MS",
    "pages": "PAGES",
    "chars_extracted": "CHARS_EXTRACTED",
    "garbled_ratio": "GARBLED_RATIO",
    "avg_chunk_tokens": "AVG_CHUNK_TOKENS",
    "fallback_triggered": "FALLBACK_TRIGGERED",
    "shard_count": "SHARD_COUNT",
    "shard_failed_count": "SHARD_FAILED_COUNT",
}


def invalidate_ingestion_status_column_cache() -> None:
    global _COLUMN_CACHE
    _COLUMN_CACHE = None


def _get_columns(cursor) -> set[str]:
    global _COLUMN_CACHE
    if _COLUMN_CACHE is not None:
        return _COLUMN_CACHE
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = 'TOMEHUB_INGESTED_FILES'
        """
    )
    _COLUMN_CACHE = {str(row[0]).upper() for row in cursor.fetchall()}
    return _COLUMN_CACHE


def _supported_fields(cursor, payload: Dict[str, Any]) -> Dict[str, Any]:
    columns = _get_columns(cursor)
    supported: Dict[str, Any] = {}
    for field_name, value in payload.items():
        column_name = _FIELD_TO_COLUMN.get(field_name)
        if column_name and column_name in columns:
            supported[field_name] = value
    return supported


def _decode_json_if_needed(value: Any) -> Any:
    if not isinstance(value, str):
        return value


def is_active_parse_status(status: Any, parse_status: Any) -> bool:
    status_value = str(status or "").strip().upper()
    parse_value = str(parse_status or "").strip().upper()
    if status_value != "PROCESSING":
        return False
    return parse_value not in _TERMINAL_PARSE_STATUSES
    stripped = value.strip()
    if not stripped or stripped[:1] not in {"{", "["}:
        return value
    try:
        return json.loads(stripped)
    except Exception:
        return value


def upsert_ingestion_status(
    book_id: str,
    firebase_uid: str,
    **payload: Any,
) -> None:
    if not book_id or not firebase_uid:
        return
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                supported = _supported_fields(cursor, payload)

                update_assignments = ["UPDATED_AT = CURRENT_TIMESTAMP"]
                insert_columns = ["BOOK_ID", "FIREBASE_UID"]
                insert_values = [":p_bid", ":p_uid"]
                bind_vars: Dict[str, Any] = {"p_bid": book_id, "p_uid": firebase_uid}

                for field_name, value in supported.items():
                    column_name = _FIELD_TO_COLUMN[field_name]
                    bind_name = f"p_{field_name}"
                    if field_name == "file_name":
                        update_assignments.append(
                            f"{column_name} = COALESCE(:{bind_name}, target.{column_name})"
                        )
                    else:
                        update_assignments.append(f"{column_name} = :{bind_name}")
                    insert_columns.append(column_name)
                    insert_values.append(f":{bind_name}")
                    bind_vars[bind_name] = value

                merge_sql = f"""
                MERGE INTO TOMEHUB_INGESTED_FILES target
                USING (SELECT :p_bid AS book_id, :p_uid AS firebase_uid FROM DUAL) src
                ON (target.BOOK_ID = src.book_id AND target.FIREBASE_UID = src.firebase_uid)
                WHEN MATCHED THEN
                    UPDATE SET {", ".join(update_assignments)}
                WHEN NOT MATCHED THEN
                    INSERT ({", ".join(insert_columns)})
                    VALUES ({", ".join(insert_values)})
                """
                cursor.execute(merge_sql, bind_vars)
                conn.commit()
    except Exception as exc:
        logger.error("Failed to upsert ingestion status: %s", exc)


def fetch_ingestion_status(book_id: str, firebase_uid: str) -> Optional[Dict[str, Any]]:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                columns = _get_columns(cursor)
                select_parts = [
                    "STATUS",
                    "SOURCE_FILE_NAME",
                    "CHUNK_COUNT",
                    "EMBEDDING_COUNT",
                    "UPDATED_AT",
                ]
                optional_parts = {
                    "PARSE_PATH": "parse_path",
                    "PARSE_STATUS": "parse_status",
                    "STORAGE_WARNING": "storage_warning",
                    "STORAGE_STATUS": "storage_status",
                    "SIZE_BYTES": "size_bytes",
                    "OBJECT_KEY": "object_key",
                    "BUCKET_NAME": "bucket_name",
                    "STORAGE_BACKEND": "storage_backend",
                    "OCI_JOB_ID": "oci_job_id",
                    "OCI_OUTPUT_PREFIX": "oci_output_prefix",
                    "MIME_TYPE": "mime_type",
                    "ERROR_MESSAGE": "error_message",
                    "CLASSIFICATION_ROUTE": "classification_route",
                    "PARSE_ENGINE": "parse_engine",
                    "FALLBACK_ENGINE": "fallback_engine",
                    "CLASSIFIER_METRICS_JSON": "classifier_metrics_json",
                    "QUALITY_METRICS_JSON": "quality_metrics_json",
                    "ROUTING_METRICS_JSON": "routing_metrics_json",
                    "PARSE_TIME_MS": "parse_time_ms",
                    "PAGES": "pages",
                    "CHARS_EXTRACTED": "chars_extracted",
                    "GARBLED_RATIO": "garbled_ratio",
                    "AVG_CHUNK_TOKENS": "avg_chunk_tokens",
                    "FALLBACK_TRIGGERED": "fallback_triggered",
                    "SHARD_COUNT": "shard_count",
                    "SHARD_FAILED_COUNT": "shard_failed_count",
                }
                for column_name in optional_parts:
                    if column_name in columns:
                        select_parts.append(column_name)

                cursor.execute(
                    f"""
                    SELECT {", ".join(select_parts)}
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if not row:
                    return None

                result = {
                    "status": row[0],
                    "file_name": row[1],
                    "chunk_count": row[2],
                    "embedding_count": row[3],
                    "updated_at": row[4],
                }
                idx = 5
                for column_name, key in optional_parts.items():
                    if column_name in columns:
                        value = row[idx]
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        value = _decode_json_if_needed(value)
                        result[key] = value
                        idx += 1

                result["pdf_available"] = bool(result.get("object_key"))
                return result
    except Exception as exc:
        logger.error("Failed to fetch ingestion status: %s", exc)
        return None


def get_user_storage_bytes(firebase_uid: str, exclude_book_id: Optional[str] = None) -> int:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                columns = _get_columns(cursor)
                if "SIZE_BYTES" not in columns:
                    return 0

                where = [
                    "FIREBASE_UID = :p_uid",
                    "NVL(SIZE_BYTES, 0) > 0",
                ]
                binds: Dict[str, Any] = {"p_uid": firebase_uid}
                if "CONTENT_TYPE" in columns:
                    where.append("UPPER(NVL(CONTENT_TYPE, 'PDF')) = 'PDF'")
                if "STORAGE_STATUS" in columns:
                    where.append("NVL(STORAGE_STATUS, 'STORED') NOT IN ('DELETE_PENDING', 'DELETED')")
                if exclude_book_id:
                    where.append("BOOK_ID <> :p_book")
                    binds["p_book"] = exclude_book_id

                cursor.execute(
                    f"""
                    SELECT NVL(SUM(SIZE_BYTES), 0)
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE {" AND ".join(where)}
                    """,
                    binds,
                )
                row = cursor.fetchone()
                return int(row[0] or 0) if row else 0
    except Exception as exc:
        logger.error("Failed to compute user storage bytes: %s", exc)
        return 0


def get_pdf_record(book_id: str, firebase_uid: str) -> Optional[Dict[str, Any]]:
    return fetch_ingestion_status(book_id, firebase_uid)


def list_pending_parse_jobs(limit: int = 100) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                columns = _get_columns(cursor)
                required = {"PARSE_STATUS", "OBJECT_KEY", "BUCKET_NAME", "STATUS"}
                if not required.issubset(columns):
                    return rows

                cursor.execute(
                    """
                    SELECT
                        BOOK_ID,
                        FIREBASE_UID,
                        SOURCE_FILE_NAME,
                        PARSE_STATUS,
                        PARSE_PATH,
                        OCI_JOB_ID,
                        OCI_OUTPUT_PREFIX,
                        BUCKET_NAME,
                        OBJECT_KEY,
                        SOURCE_FILE_NAME,
                        STORAGE_STATUS
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE STATUS = 'PROCESSING'
                      AND NVL(PARSE_PATH, 'LEGACY') = 'PDF_V2'
                      AND PARSE_STATUS NOT IN ('COMPLETED', 'FAILED')
                    ORDER BY UPDATED_AT
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_limit": int(limit)},
                )
                for row in cursor.fetchall():
                    rows.append(
                        {
                            "book_id": row[0],
                            "firebase_uid": row[1],
                            "title": None,
                            "parse_status": row[3],
                            "parse_path": row[4],
                            "oci_job_id": row[5],
                            "oci_output_prefix": row[6],
                            "bucket_name": row[7],
                            "object_key": row[8],
                            "file_name": row[9],
                            "storage_status": row[10],
                        }
                    )
    except Exception as exc:
        logger.error("Failed to list pending parse jobs: %s", exc)
    return rows


def mark_storage_delete_failed(book_id: str, firebase_uid: str, error_message: str) -> None:
    upsert_ingestion_status(
        book_id,
        firebase_uid,
        storage_status="DELETE_FAILED",
        error_message=(error_message or "")[:1000],
    )


def delete_ingested_file_row(book_id: str, firebase_uid: str) -> None:
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_INGESTED_FILES
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
            conn.commit()
    except Exception as exc:
        logger.error("Failed to delete ingested file row: %s", exc)


def list_pending_storage_deletes(limit: int = 100) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                columns = _get_columns(cursor)
                if "STORAGE_STATUS" not in columns or "OBJECT_KEY" not in columns:
                    return rows
                cursor.execute(
                    """
                    SELECT BOOK_ID, FIREBASE_UID, BUCKET_NAME, OBJECT_KEY, OCI_OUTPUT_PREFIX, STORAGE_STATUS
                    FROM TOMEHUB_INGESTED_FILES
                    WHERE STORAGE_STATUS IN ('DELETE_PENDING', 'DELETE_FAILED')
                    ORDER BY UPDATED_AT
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_limit": int(limit)},
                )
                for row in cursor.fetchall():
                    rows.append(
                        {
                            "book_id": row[0],
                            "firebase_uid": row[1],
                            "bucket_name": row[2],
                            "object_key": row[3],
                            "oci_output_prefix": row[4],
                            "storage_status": row[5],
                        }
                    )
    except Exception as exc:
        logger.error("Failed to list pending storage deletes: %s", exc)
    return rows


def set_storage_delete_pending(book_id: str, firebase_uid: str) -> None:
    upsert_ingestion_status(book_id, firebase_uid, storage_status="DELETE_PENDING")


def bulk_mark_storage_delete_pending(items: Iterable[Dict[str, Any]]) -> None:
    for item in items:
        set_storage_delete_pending(str(item.get("book_id") or ""), str(item.get("firebase_uid") or ""))
