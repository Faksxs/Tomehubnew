from models.discovery_models import (
    DiscoveryBoardMetadata,
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceMetadata,
    DiscoveryInnerSpaceResponse,
)
from services.discovery_cache_service import (
    get_discovery_board_cached,
    get_discovery_inner_space_cached,
    invalidate_discovery_cache,
)


def test_inner_space_cache_reuses_payload(monkeypatch):
    invalidate_discovery_cache("user-1")
    calls = {"count": 0}

    def _loader(firebase_uid: str):
        calls["count"] += 1
        return DiscoveryInnerSpaceResponse(
            cards=[],
            metadata=DiscoveryInnerSpaceMetadata(
                last_updated_at=f"2026-03-24T00:00:0{calls['count']}+00:00",
            ),
        )

    monkeypatch.setattr("services.discovery_cache_service.get_discovery_inner_space", _loader)

    first, first_status, _ = get_discovery_inner_space_cached("user-1")
    second, second_status, _ = get_discovery_inner_space_cached("user-1")

    assert calls["count"] == 1
    assert first_status == "live"
    assert second_status == "fresh_cache"
    assert first.metadata.cache_status == "live"
    assert second.metadata.cache_status == "fresh_cache"


def test_board_force_refresh_bypasses_cache(monkeypatch):
    invalidate_discovery_cache("user-1", category=DiscoveryCategory.ACADEMIC)
    calls = {"count": 0}

    monkeypatch.setattr("services.discovery_cache_service._provider_preferences_token", lambda firebase_uid: "prefs")

    def _loader(category: str, firebase_uid: str, selection_token=None):
        calls["count"] += 1
        return DiscoveryBoardResponse(
            category=DiscoveryCategory(category),
            featured_card=None,
            family_sections=[],
            metadata=DiscoveryBoardMetadata(
                category_title="Academic",
                category_description="",
                last_updated_at=f"2026-03-24T00:00:0{calls['count']}+00:00",
                active_provider_names=[],
                total_cards=0,
            ),
        )

    monkeypatch.setattr("services.discovery_cache_service.get_discovery_board", _loader)

    first, first_status, _ = get_discovery_board_cached(DiscoveryCategory.ACADEMIC, "user-1")
    second, second_status, _ = get_discovery_board_cached(DiscoveryCategory.ACADEMIC, "user-1", force_refresh=True)

    assert calls["count"] == 2
    assert first_status == "live"
    assert second_status == "live"
    assert first.metadata.cache_status == "live"
    assert second.metadata.cache_status == "live"
