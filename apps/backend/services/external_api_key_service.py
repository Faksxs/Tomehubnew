import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import OrderedDict
from typing import Any, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.logger import get_logger


logger = get_logger("external_api_key_service")

KEY_PREFIX_LEN = 20
DEFAULT_SCOPES = ("search:read",)
_CACHE_MISS = object()
_api_key_cache_lock = threading.Lock()
_api_key_cache: "OrderedDict[str, tuple[float, object]]" = OrderedDict()
_last_key_touch_by_id: dict[int, tuple[float, Optional[str]]] = {}


@dataclass
class ExternalApiKeyRecord:
    key_id: int
    owner_firebase_uid: str
    key_prefix: str
    label: Optional[str]
    scopes: list[str]
    status: str
    expires_at: Optional[str]


def ensure_external_api_enabled() -> None:
    if not bool(getattr(settings, "EXTERNAL_API_ENABLED", False)):
        raise RuntimeError("External API is disabled")


def normalize_scopes(raw_scopes: Optional[list[str] | tuple[str, ...]]) -> list[str]:
    scopes = raw_scopes or settings.EXTERNAL_API_DEFAULT_SCOPES or DEFAULT_SCOPES
    normalized: list[str] = []
    seen = set()
    for scope in scopes:
        value = str(scope or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized or list(DEFAULT_SCOPES)


def generate_external_api_key() -> str:
    return f"th_live_{secrets.token_urlsafe(32)}"


def get_key_prefix(raw_key: str) -> str:
    return str(raw_key or "").strip()[:KEY_PREFIX_LEN]


def hash_external_api_key(raw_key: str) -> str:
    material = f"{settings.EXTERNAL_API_KEY_PEPPER}:{str(raw_key or '').strip()}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _parse_scopes(scopes_value: Any) -> list[str]:
    if scopes_value is None:
        return list(DEFAULT_SCOPES)
    if isinstance(scopes_value, list):
        return normalize_scopes(scopes_value)
    text = safe_read_clob(scopes_value) if hasattr(scopes_value, "read") else str(scopes_value or "")
    if not text.strip():
        return list(DEFAULT_SCOPES)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(payload, list):
        return normalize_scopes(payload)
    return list(DEFAULT_SCOPES)


def _row_to_record(row: Any) -> ExternalApiKeyRecord:
    return ExternalApiKeyRecord(
        key_id=int(row[0]),
        owner_firebase_uid=str(row[1]),
        key_prefix=str(row[2]),
        label=str(row[3]) if row[3] is not None else None,
        scopes=_parse_scopes(row[4]),
        status=str(row[5]),
        expires_at=row[6].isoformat() if row[6] is not None else None,
    )


def _cache_ttl_seconds() -> int:
    return int(getattr(settings, "EXTERNAL_API_KEY_CACHE_TTL_SEC", 300) or 300)


def _cache_maxsize() -> int:
    return int(getattr(settings, "EXTERNAL_API_KEY_CACHE_MAXSIZE", 1024) or 1024)


def _touch_debounce_seconds() -> int:
    return int(getattr(settings, "EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC", 300) or 300)


def _prune_api_key_cache(now: Optional[float] = None) -> None:
    current = now if now is not None else time.monotonic()
    expired_keys = [key for key, (expires_at, _) in _api_key_cache.items() if expires_at <= current]
    for key in expired_keys:
        _api_key_cache.pop(key, None)

    maxsize = _cache_maxsize()
    while len(_api_key_cache) > maxsize:
        _api_key_cache.popitem(last=False)


def _get_cached_external_api_key(cache_key: str) -> object:
    now = time.monotonic()
    with _api_key_cache_lock:
        _prune_api_key_cache(now)
        cached = _api_key_cache.get(cache_key)
        if cached is None:
            return _CACHE_MISS
        expires_at, value = cached
        if expires_at <= now:
            _api_key_cache.pop(cache_key, None)
            return _CACHE_MISS
        _api_key_cache.move_to_end(cache_key)
        return value


def _store_cached_external_api_key(cache_key: str, value: object) -> None:
    now = time.monotonic()
    with _api_key_cache_lock:
        _api_key_cache[cache_key] = (now + _cache_ttl_seconds(), value)
        _api_key_cache.move_to_end(cache_key)
        _prune_api_key_cache(now)


def invalidate_external_api_key_cache() -> None:
    with _api_key_cache_lock:
        _api_key_cache.clear()
        _last_key_touch_by_id.clear()


def resolve_external_api_key(raw_key: str) -> Optional[ExternalApiKeyRecord]:
    ensure_external_api_enabled()
    key = str(raw_key or "").strip()
    if not key:
        return None

    key_prefix = get_key_prefix(key)
    key_hash = hash_external_api_key(key)
    cached = _get_cached_external_api_key(key_hash)
    if cached is not _CACHE_MISS:
        return cached if isinstance(cached, ExternalApiKeyRecord) else None

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT ID,
                       OWNER_FIREBASE_UID,
                       KEY_PREFIX,
                       LABEL,
                       SCOPES_JSON,
                       STATUS,
                       EXPIRES_AT,
                       KEY_HASH
                FROM TOMEHUB_EXTERNAL_API_KEYS
                WHERE KEY_PREFIX = :p_key_prefix
                  AND STATUS = 'ACTIVE'
                  AND (EXPIRES_AT IS NULL OR EXPIRES_AT > SYSTIMESTAMP)
                FETCH FIRST 1 ROWS ONLY
                """,
                {"p_key_prefix": key_prefix},
            )
            row = cursor.fetchone()

    if not row:
        _store_cached_external_api_key(key_hash, None)
        return None

    stored_hash = safe_read_clob(row[7]) if hasattr(row[7], "read") else str(row[7] or "")
    if not stored_hash or not hmac.compare_digest(stored_hash, key_hash):
        _store_cached_external_api_key(key_hash, None)
        return None

    record = _row_to_record(row)
    _store_cached_external_api_key(key_hash, record)
    return record


def touch_external_api_key(key_id: int, remote_addr: Optional[str] = None) -> None:
    normalized_ip = str(remote_addr or "")[:128] or None
    now = time.monotonic()
    with _api_key_cache_lock:
        previous = _last_key_touch_by_id.get(int(key_id))
        if previous is not None:
            last_touch_at, last_ip = previous
            if (now - last_touch_at) < _touch_debounce_seconds() and last_ip == normalized_ip:
                return

    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE TOMEHUB_EXTERNAL_API_KEYS
                    SET LAST_USED_AT = SYSTIMESTAMP,
                        LAST_IP = :p_last_ip
                    WHERE ID = :p_id
                    """,
                    {"p_id": int(key_id), "p_last_ip": normalized_ip},
                )
            conn.commit()
        with _api_key_cache_lock:
            _last_key_touch_by_id[int(key_id)] = (now, normalized_ip)
    except Exception as exc:
        logger.warning("Failed to update external API key usage id=%s: %s", key_id, exc)


def create_external_api_key(
    *,
    owner_firebase_uid: str,
    label: str,
    scopes: Optional[list[str]] = None,
    expires_at_iso: Optional[str] = None,
) -> dict[str, Any]:
    ensure_external_api_enabled()
    owner_uid = str(owner_firebase_uid or "").strip()
    if not owner_uid:
        raise ValueError("owner_firebase_uid is required")

    raw_key = generate_external_api_key()
    key_prefix = get_key_prefix(raw_key)
    key_hash = hash_external_api_key(raw_key)
    normalized_scopes = normalize_scopes(scopes)
    expires_at = None
    if expires_at_iso:
        expires_at = datetime.fromisoformat(str(expires_at_iso).strip())
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            key_id_var = cursor.var(int)
            cursor.execute(
                """
                INSERT INTO TOMEHUB_EXTERNAL_API_KEYS (
                    ID,
                    OWNER_FIREBASE_UID,
                    KEY_PREFIX,
                    KEY_HASH,
                    LABEL,
                    SCOPES_JSON,
                    STATUS,
                    EXPIRES_AT,
                    CREATED_AT
                ) VALUES (
                    TOMEHUB_EXTERNAL_API_KEYS_SEQ.NEXTVAL,
                    :p_owner_uid,
                    :p_key_prefix,
                    :p_key_hash,
                    :p_label,
                    :p_scopes_json,
                    'ACTIVE',
                    :p_expires_at,
                    SYSTIMESTAMP
                )
                RETURNING ID INTO :p_key_id
                """,
                {
                    "p_owner_uid": owner_uid,
                    "p_key_prefix": key_prefix,
                    "p_key_hash": key_hash,
                    "p_label": str(label or "").strip()[:255] or None,
                    "p_scopes_json": json.dumps(normalized_scopes, ensure_ascii=True),
                    "p_expires_at": expires_at,
                    "p_key_id": key_id_var,
                },
            )
            conn.commit()
            key_id = int(key_id_var.getvalue()[0])

    invalidate_external_api_key_cache()
    return {
        "key_id": key_id,
        "raw_key": raw_key,
        "key_prefix": key_prefix,
        "owner_firebase_uid": owner_uid,
        "label": str(label or "").strip()[:255] or None,
        "scopes": normalized_scopes,
        "expires_at": expires_at.isoformat() if expires_at is not None else None,
    }


def revoke_external_api_key(*, key_id: Optional[int] = None, key_prefix: Optional[str] = None) -> bool:
    ensure_external_api_enabled()
    if key_id is None and not str(key_prefix or "").strip():
        raise ValueError("key_id or key_prefix is required")

    params: dict[str, Any] = {}
    if key_id is not None:
        where_clause = "ID = :p_id"
        params["p_id"] = int(key_id)
    else:
        where_clause = "KEY_PREFIX = :p_key_prefix"
        params["p_key_prefix"] = str(key_prefix or "").strip()[:KEY_PREFIX_LEN]

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE TOMEHUB_EXTERNAL_API_KEYS
                SET STATUS = 'REVOKED',
                    REVOKED_AT = SYSTIMESTAMP
                WHERE {where_clause}
                  AND STATUS = 'ACTIVE'
                """,
                params,
            )
            updated = int(cursor.rowcount or 0)
            conn.commit()
    if updated > 0:
        invalidate_external_api_key_cache()
    return updated > 0
