from __future__ import annotations

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
from services.discovery_board_service import get_discovery_board
from services.discovery_inner_space_service import get_discovery_inner_space
from utils.logger import get_logger

logger = get_logger("discovery_page_service")


def get_discovery_page(firebase_uid: str) -> DiscoveryPageResponse:
    board_errors: List[str] = []
    used_cached_fallbacks = False

    inner_space, inner_space_error = _safe_inner_space(firebase_uid)
    if inner_space_error:
        board_errors.append(inner_space_error)
        used_cached_fallbacks = True

    academic, academic_error = _safe_board(DiscoveryCategory.ACADEMIC, firebase_uid)
    religious, religious_error = _safe_board(DiscoveryCategory.RELIGIOUS, firebase_uid)
    literary, literary_error = _safe_board(DiscoveryCategory.LITERARY, firebase_uid)
    culture_history, culture_history_error = _safe_board(DiscoveryCategory.CULTURE_HISTORY, firebase_uid)

    for error in [academic_error, religious_error, literary_error, culture_history_error]:
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
        ),
    )


def _safe_inner_space(firebase_uid: str) -> Tuple[DiscoveryInnerSpaceResponse, str | None]:
    try:
        return get_discovery_inner_space(firebase_uid), None
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
                ),
            ),
            f"INNER_SPACE: {exc}",
        )


def _safe_board(category: DiscoveryCategory, firebase_uid: str) -> Tuple[DiscoveryBoardResponse, str | None]:
    try:
        return get_discovery_board(category.value, firebase_uid), None
    except Exception as exc:
        logger.warning("discovery page board fallback category=%s uid=%s error=%s", category.value, firebase_uid, exc)
        return _empty_board(category), f"{category.value}: {exc}"


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
        ),
    )
