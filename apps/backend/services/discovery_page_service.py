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
from services.discovery_cache_service import get_discovery_board_cached, get_discovery_inner_space_cached
from utils.logger import get_logger

logger = get_logger("discovery_page_service")


def get_discovery_page(firebase_uid: str, *, force_refresh: bool = False) -> DiscoveryPageResponse:
    board_errors: List[str] = []
    used_cached_fallbacks = False
    segment_status: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="discovery-page") as executor:
        inner_space_future = executor.submit(_safe_inner_space, firebase_uid, force_refresh=force_refresh)
        academic_future = executor.submit(_safe_board, DiscoveryCategory.ACADEMIC, firebase_uid, force_refresh=force_refresh)
        religious_future = executor.submit(_safe_board, DiscoveryCategory.RELIGIOUS, firebase_uid, force_refresh=force_refresh)
        literary_future = executor.submit(_safe_board, DiscoveryCategory.LITERARY, firebase_uid, force_refresh=force_refresh)
        culture_future = executor.submit(_safe_board, DiscoveryCategory.CULTURE_HISTORY, firebase_uid, force_refresh=force_refresh)

        inner_space, inner_space_status, inner_space_error = inner_space_future.result()
        academic, academic_status, academic_error = academic_future.result()
        religious, religious_status, religious_error = religious_future.result()
        literary, literary_status, literary_error = literary_future.result()
        culture_history, culture_status, culture_history_error = culture_future.result()

    segment_status["inner_space"] = inner_space_status
    segment_status["academic"] = academic_status
    segment_status["religious"] = religious_status
    segment_status["literary"] = literary_status
    segment_status["culture_history"] = culture_status

    for error in [inner_space_error, academic_error, religious_error, literary_error, culture_history_error]:
        if error:
            board_errors.append(error)
            used_cached_fallbacks = True

    return DiscoveryPageResponse(
        inner_space=inner_space,
        boards=DiscoveryPageBoards(
            academic=academic,
            religious=religious,
            literary=literary,
            culture_history=culture_history,
        ),
        metadata=DiscoveryPageMetadata(
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            board_errors=board_errors,
            used_cached_fallbacks=used_cached_fallbacks,
            cache_status=_aggregate_page_cache_status(segment_status),
            segment_status=segment_status,
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
) -> Tuple[DiscoveryBoardResponse, str, str | None]:
    try:
        response, cache_status, error = get_discovery_board_cached(category, firebase_uid, force_refresh=force_refresh)
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
