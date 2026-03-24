from models.discovery_models import (
    DiscoveryBoardMetadata,
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceMetadata,
    DiscoveryInnerSpaceResponse,
)
from services.discovery_page_service import get_discovery_page


def test_get_discovery_page_survives_board_failure(monkeypatch):
    monkeypatch.setattr(
        "services.discovery_page_service.get_discovery_inner_space_cached",
        lambda firebase_uid, force_refresh=False: (
            DiscoveryInnerSpaceResponse(
                cards=[],
                metadata=DiscoveryInnerSpaceMetadata(
                    last_updated_at="2026-03-24T00:00:00+00:00",
                    cache_status="live",
                ),
            ),
            "live",
            None,
        ),
    )

    def _board(category: DiscoveryCategory, firebase_uid: str, force_refresh: bool = False):
        if category == DiscoveryCategory.RELIGIOUS:
            raise RuntimeError("provider down")
        return (
            DiscoveryBoardResponse(
                category=category,
                featured_card=None,
                family_sections=[],
                metadata=DiscoveryBoardMetadata(
                    category_title=category.value.title(),
                    category_description="",
                    last_updated_at="2026-03-24T00:00:00+00:00",
                    active_provider_names=[],
                    total_cards=0,
                    cache_status="fresh_cache",
                ),
            ),
            "fresh_cache",
            None,
        )

    monkeypatch.setattr("services.discovery_page_service.get_discovery_board_cached", _board)

    page = get_discovery_page("user-1")

    assert page.boards.academic.category == DiscoveryCategory.ACADEMIC
    assert page.boards.religious.category == DiscoveryCategory.RELIGIOUS
    assert page.metadata.used_cached_fallbacks is True
    assert page.metadata.segment_status["academic"] == "fresh_cache"
    assert any("RELIGIOUS:" in error for error in page.metadata.board_errors)


def test_get_discovery_page_reports_cache_status(monkeypatch):
    monkeypatch.setattr(
        "services.discovery_page_service.get_discovery_inner_space_cached",
        lambda firebase_uid, force_refresh=False: (
            DiscoveryInnerSpaceResponse(
                cards=[],
                metadata=DiscoveryInnerSpaceMetadata(
                    last_updated_at="2026-03-24T00:00:00+00:00",
                    cache_status="stale_cache",
                ),
            ),
            "stale_cache",
            None,
        ),
    )

    monkeypatch.setattr(
        "services.discovery_page_service.get_discovery_board_cached",
        lambda category, firebase_uid, force_refresh=False: (
            DiscoveryBoardResponse(
                category=category,
                featured_card=None,
                family_sections=[],
                metadata=DiscoveryBoardMetadata(
                    category_title=category.value.title(),
                    category_description="",
                    last_updated_at="2026-03-24T00:00:00+00:00",
                    active_provider_names=[],
                    total_cards=0,
                    cache_status="fresh_cache",
                ),
            ),
            "fresh_cache",
            None,
        ),
    )

    page = get_discovery_page("user-1")

    assert page.metadata.cache_status == "partial_stale"
    assert page.metadata.segment_status["inner_space"] == "stale_cache"
