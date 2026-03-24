from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Literal, TypeVar

from models.discovery_models import (
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceResponse,
)
from services.cache_service import get_cache
from services.discovery_board_service import get_discovery_board
from services.discovery_inner_space_service import get_discovery_inner_space
from services.user_preferences_service import get_user_preferences
from utils.logger import get_logger

logger = get_logger("discovery_cache_service")

CacheStatus = Literal["live", "fresh_cache", "stale_cache"]
TResponse = TypeVar("TResponse", DiscoveryBoardResponse, DiscoveryInnerSpaceResponse)


@dataclass(frozen=True)
class DiscoveryCachePolicy:
    fresh_ttl_seconds: int
    stale_ttl_seconds: int


INNER_SPACE_POLICY = DiscoveryCachePolicy(fresh_ttl_seconds=30 * 60, stale_ttl_seconds=2 * 60 * 60)
BOARD_POLICIES: Dict[DiscoveryCategory, DiscoveryCachePolicy] = {
    DiscoveryCategory.ACADEMIC: DiscoveryCachePolicy(fresh_ttl_seconds=12 * 60 * 60, stale_ttl_seconds=36 * 60 * 60),
    DiscoveryCategory.RELIGIOUS: DiscoveryCachePolicy(fresh_ttl_seconds=24 * 60 * 60, stale_ttl_seconds=7 * 24 * 60 * 60),
    DiscoveryCategory.LITERARY: DiscoveryCachePolicy(fresh_ttl_seconds=12 * 60 * 60, stale_ttl_seconds=48 * 60 * 60),
    DiscoveryCategory.CULTURE_HISTORY: DiscoveryCachePolicy(fresh_ttl_seconds=24 * 60 * 60, stale_ttl_seconds=72 * 60 * 60),
}

_LOCAL_CACHE_LOCK = threading.Lock()
_LOCAL_DISCOVERY_CACHE: Dict[str, Dict[str, Any]] = {}
_REFRESHING_KEYS: set[str] = set()
_DISCOVERY_INNER_SPACE_CACHE_VERSION = "v2"
_DISCOVERY_BOARD_CACHE_VERSION = "v3"


def get_discovery_inner_space_cached(
    firebase_uid: str,
    *,
    force_refresh: bool = False,
) -> tuple[DiscoveryInnerSpaceResponse, CacheStatus, str | None]:
    cache_key = _make_inner_space_cache_key(firebase_uid)
    if force_refresh:
        _delete_cache_entry(cache_key)
    cached = _get_cache_entry(cache_key)
    if cached and not force_refresh:
        state = _cache_state(cached)
        if state == "fresh_cache":
            return _apply_inner_space_cache_metadata(_deserialize_inner_space(cached["payload"]), state, cached), state, None
        if state == "stale_cache":
            _start_background_refresh_if_needed(
                cache_key=cache_key,
                policy=INNER_SPACE_POLICY,
                loader=lambda: get_discovery_inner_space(firebase_uid),
            )
            return _apply_inner_space_cache_metadata(_deserialize_inner_space(cached["payload"]), state, cached), state, None

    try:
        response = get_discovery_inner_space(firebase_uid)
        entry = _build_cache_entry(response, INNER_SPACE_POLICY)
        _set_cache_entry(cache_key, entry, INNER_SPACE_POLICY.stale_ttl_seconds)
        return _apply_inner_space_cache_metadata(response, "live", entry), "live", None
    except Exception as exc:
        if cached and not force_refresh and _cache_state(cached) in {"fresh_cache", "stale_cache"}:
            logger.warning("discovery inner-space serving stale cache uid=%s error=%s", firebase_uid, exc)
            return (
                _apply_inner_space_cache_metadata(_deserialize_inner_space(cached["payload"]), "stale_cache", cached),
                "stale_cache",
                str(exc),
            )
        raise


def get_discovery_board_cached(
    category: DiscoveryCategory,
    firebase_uid: str,
    *,
    force_refresh: bool = False,
    refresh_token: str | None = None,
) -> tuple[DiscoveryBoardResponse, CacheStatus, str | None]:
    policy = BOARD_POLICIES[category]
    cache_key = _make_board_cache_key(category, firebase_uid)
    if force_refresh:
        _delete_cache_entry(cache_key)
    cached = _get_cache_entry(cache_key)
    if cached and not force_refresh:
        state = _cache_state(cached)
        if state == "fresh_cache":
            return _apply_board_cache_metadata(_deserialize_board(cached["payload"]), state, cached), state, None
        if state == "stale_cache":
            _start_background_refresh_if_needed(
                cache_key=cache_key,
                policy=policy,
                loader=lambda: get_discovery_board(category.value, firebase_uid),
            )
            return _apply_board_cache_metadata(_deserialize_board(cached["payload"]), state, cached), state, None

    try:
        response = get_discovery_board(
            category.value,
            firebase_uid,
            selection_token=refresh_token if force_refresh else None,
        )
        entry = _build_cache_entry(response, policy)
        _set_cache_entry(cache_key, entry, policy.stale_ttl_seconds)
        return _apply_board_cache_metadata(response, "live", entry), "live", None
    except Exception as exc:
        if cached and not force_refresh and _cache_state(cached) in {"fresh_cache", "stale_cache"}:
            logger.warning("discovery board serving stale cache category=%s uid=%s error=%s", category.value, firebase_uid, exc)
            return (
                _apply_board_cache_metadata(_deserialize_board(cached["payload"]), "stale_cache", cached),
                "stale_cache",
                str(exc),
            )
        raise


def invalidate_discovery_cache(firebase_uid: str, *, category: DiscoveryCategory | None = None) -> None:
    prefixes = (
        [f"discovery:inner_space:{firebase_uid}:"]
        if category is None
        else []
    )
    if category is None:
        prefixes.extend(
            [
                f"discovery:board:{firebase_uid}:{DiscoveryCategory.ACADEMIC.value}:",
                f"discovery:board:{firebase_uid}:{DiscoveryCategory.RELIGIOUS.value}:",
                f"discovery:board:{firebase_uid}:{DiscoveryCategory.LITERARY.value}:",
                f"discovery:board:{firebase_uid}:{DiscoveryCategory.CULTURE_HISTORY.value}:",
            ]
        )
    else:
        prefixes.append(f"discovery:board:{firebase_uid}:{category.value}:")

    with _LOCAL_CACHE_LOCK:
        for key in list(_LOCAL_DISCOVERY_CACHE.keys()):
            if any(key.startswith(prefix) for prefix in prefixes):
                _LOCAL_DISCOVERY_CACHE.pop(key, None)
        _REFRESHING_KEYS.difference_update({key for key in _REFRESHING_KEYS if any(key.startswith(prefix) for prefix in prefixes)})

    shared_cache = get_cache()
    if shared_cache:
        for prefix in prefixes:
            shared_cache.delete_pattern(f"{prefix}*")


def _make_inner_space_cache_key(firebase_uid: str) -> str:
    return f"discovery:inner_space:{firebase_uid}:{_DISCOVERY_INNER_SPACE_CACHE_VERSION}"


def _make_board_cache_key(category: DiscoveryCategory, firebase_uid: str) -> str:
    prefs_token = _provider_preferences_token(firebase_uid)
    return f"discovery:board:{firebase_uid}:{category.value}:{prefs_token}:{_DISCOVERY_BOARD_CACHE_VERSION}"


def _provider_preferences_token(firebase_uid: str) -> str:
    try:
        prefs = get_user_preferences(firebase_uid) or {}
        api_preferences = prefs.get("api_preferences", {})
        if not isinstance(api_preferences, dict):
            api_preferences = {}
        serialized = json.dumps(api_preferences, sort_keys=True, separators=(",", ":"))
    except Exception as exc:
        logger.warning("discovery cache prefs token fallback uid=%s error=%s", firebase_uid, exc)
        serialized = "{}"
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]


def _build_cache_entry(response: TResponse, policy: DiscoveryCachePolicy) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "payload": response.model_dump(mode="json"),
        "cached_at": now.isoformat(),
        "fresh_until": (now + timedelta(seconds=policy.fresh_ttl_seconds)).isoformat(),
        "stale_until": (now + timedelta(seconds=policy.stale_ttl_seconds)).isoformat(),
    }


def _get_cache_entry(cache_key: str) -> Dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    with _LOCAL_CACHE_LOCK:
        entry = _LOCAL_DISCOVERY_CACHE.get(cache_key)
        if entry:
            if _parse_timestamp(entry.get("stale_until")) <= now:
                _LOCAL_DISCOVERY_CACHE.pop(cache_key, None)
            else:
                return entry

    shared_cache = get_cache()
    if not shared_cache:
        return None

    entry = shared_cache.get(cache_key)
    if not isinstance(entry, dict):
        return None
    if _parse_timestamp(entry.get("stale_until")) <= now:
        shared_cache.delete(cache_key)
        return None
    with _LOCAL_CACHE_LOCK:
        _LOCAL_DISCOVERY_CACHE[cache_key] = entry
    return entry


def _set_cache_entry(cache_key: str, entry: Dict[str, Any], ttl_seconds: int) -> None:
    with _LOCAL_CACHE_LOCK:
        _LOCAL_DISCOVERY_CACHE[cache_key] = entry
    shared_cache = get_cache()
    if shared_cache:
        shared_cache.set(cache_key, entry, ttl=ttl_seconds)


def _delete_cache_entry(cache_key: str) -> None:
    with _LOCAL_CACHE_LOCK:
        _LOCAL_DISCOVERY_CACHE.pop(cache_key, None)
        _REFRESHING_KEYS.discard(cache_key)
    shared_cache = get_cache()
    if shared_cache:
        shared_cache.delete(cache_key)


def _cache_state(entry: Dict[str, Any]) -> CacheStatus | None:
    now = datetime.now(timezone.utc)
    fresh_until = _parse_timestamp(entry.get("fresh_until"))
    stale_until = _parse_timestamp(entry.get("stale_until"))
    if fresh_until > now:
        return "fresh_cache"
    if stale_until > now:
        return "stale_cache"
    return None


def _parse_timestamp(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _start_background_refresh_if_needed(
    *,
    cache_key: str,
    policy: DiscoveryCachePolicy,
    loader: Callable[[], TResponse],
) -> None:
    with _LOCAL_CACHE_LOCK:
        if cache_key in _REFRESHING_KEYS:
            return
        _REFRESHING_KEYS.add(cache_key)

    def _runner() -> None:
        try:
            response = loader()
            entry = _build_cache_entry(response, policy)
            _set_cache_entry(cache_key, entry, policy.stale_ttl_seconds)
        except Exception as exc:
            logger.warning("discovery cache background refresh failed key=%s error=%s", cache_key, exc)
        finally:
            with _LOCAL_CACHE_LOCK:
                _REFRESHING_KEYS.discard(cache_key)

    thread = threading.Thread(target=_runner, name=f"discovery-refresh-{cache_key[-16:]}", daemon=True)
    thread.start()


def _deserialize_inner_space(payload: Dict[str, Any]) -> DiscoveryInnerSpaceResponse:
    return DiscoveryInnerSpaceResponse.model_validate(payload)


def _deserialize_board(payload: Dict[str, Any]) -> DiscoveryBoardResponse:
    return DiscoveryBoardResponse.model_validate(payload)


def _apply_inner_space_cache_metadata(
    response: DiscoveryInnerSpaceResponse,
    cache_status: CacheStatus,
    entry: Dict[str, Any],
) -> DiscoveryInnerSpaceResponse:
    metadata = response.metadata.model_copy(
        update={
            "cache_status": cache_status,
            "cache_generated_at": entry.get("cached_at"),
            "cache_expires_at": entry.get("fresh_until"),
            "cache_stale_at": entry.get("stale_until"),
        }
    )
    return response.model_copy(update={"metadata": metadata})


def _apply_board_cache_metadata(
    response: DiscoveryBoardResponse,
    cache_status: CacheStatus,
    entry: Dict[str, Any],
) -> DiscoveryBoardResponse:
    metadata = response.metadata.model_copy(
        update={
            "cache_status": cache_status,
            "cache_generated_at": entry.get("cached_at"),
            "cache_expires_at": entry.get("fresh_until"),
            "cache_stale_at": entry.get("stale_until"),
        }
    )
    return response.model_copy(update={"metadata": metadata})
