from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List, Tuple

from models.discovery_models import (
    DiscoveryBoardMetadata,
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceMetadata,
    DiscoveryInnerSpaceResponse,
    DiscoveryPageBoards,
    DiscoveryPageMetadata,
    DiscoveryPageResponse,
)
from services.discovery_cache_service import (
    get_discovery_board_cached,
    get_discovery_inner_space_cached,
    invalidate_discovery_cache,
)
from utils.logger import get_logger

logger = get_logger("discovery_page_service")


def get_discovery_page(
    firebase_uid: str,
    *,
    force_refresh: bool = False,
    refresh_token: str | None = None,
) -> DiscoveryPageResponse:
    if force_refresh:
        invalidate_discovery_cache(firebase_uid)

    # 1. Fetch only Inner Space immediately (Fastest)
    inner_space, inner_space_status, inner_space_error = _safe_inner_space(firebase_uid, force_refresh=force_refresh)

    # 2. Return empty placeholders for boards. Frontend will fetch them via /api/discovery/board?category=X
    return DiscoveryPageResponse(
        inner_space=inner_space,
        boards=DiscoveryPageBoards(
            academic=_empty_board(DiscoveryCategory.ACADEMIC),
            religious=_empty_board(DiscoveryCategory.RELIGIOUS),
            literary=_empty_board(DiscoveryCategory.LITERARY),
            culture_history=_empty_board(DiscoveryCategory.CULTURE_HISTORY),
        ),
        metadata=DiscoveryPageMetadata(
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            board_errors=[inner_space_error] if inner_space_error else [],
            used_cached_fallbacks=False,
            cache_status=inner_space_status,
            segment_status={"inner_space": inner_space_status},
        ),
    )


def _safe_inner_space(firebase_uid: str, *, force_refresh: bool) -> Tuple[DiscoveryInnerSpaceResponse, str, str | None]:
    try:
        response, cache_status, error = get_discovery_inner_space_cached(firebase_uid, force_refresh=force_refresh)
        return response, cache_status, error
    except Exception as exc:
        logger.warning("discovery page inner-space fallback uid=%s error=%s", firebase_uid, exc)
        return (
            DiscoveryInnerSpaceResponse(
                cards=[],
                metadata=DiscoveryInnerSpaceMetadata(
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                    active_theme_count=0,
                    has_memory_profile=False,
                    total_items_considered=0,
                    cache_status="live",
                ),
            ),
            "live",
            f"INNER_SPACE: {exc}",
        )


def _safe_board(
    category: DiscoveryCategory,
    firebase_uid: str,
    *,
    force_refresh: bool,
    refresh_token: str | None,
) -> Tuple[DiscoveryBoardResponse, str, str | None]:
    try:
        response, cache_status, error = get_discovery_board_cached(
            category,
            firebase_uid,
            force_refresh=force_refresh,
            refresh_token=refresh_token,
        )
        return response, cache_status, error
    except Exception as exc:
        logger.warning("discovery page board fallback category=%s uid=%s error=%s", category.value, firebase_uid, exc)
        return _empty_board(category), "live", f"{category.value}: {exc}"


def _empty_board(category: DiscoveryCategory) -> DiscoveryBoardResponse:
    category_title = {
        DiscoveryCategory.ACADEMIC: "Academic",
        DiscoveryCategory.RELIGIOUS: "Religious",
        DiscoveryCategory.LITERARY: "Literary",
        DiscoveryCategory.CULTURE_HISTORY: "Culture",
    }[category]
    return DiscoveryBoardResponse(
        category=category,
        featured_card=None,
        family_sections=[],
        metadata=DiscoveryBoardMetadata(
            category_title=category_title,
            category_description="",
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            active_provider_names=[],
            total_cards=0,
            cache_status="live",
        ),
    )


def _aggregate_page_cache_status(segment_status: dict[str, str]) -> str:
    statuses = [status for status in segment_status.values() if status]
    if not statuses:
        return "live"
    if any(status == "stale_cache" for status in statuses):
        return "partial_stale"
    if all(status == "fresh_cache" for status in statuses):
        return "fresh_cache"
    if any(status == "fresh_cache" for status in statuses):
        return "mixed_cache"
    return "live"
