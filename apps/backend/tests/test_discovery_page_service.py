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
        "services.discovery_page_service.get_discovery_inner_space",
        lambda firebase_uid: DiscoveryInnerSpaceResponse(
            cards=[],
            metadata=DiscoveryInnerSpaceMetadata(
                last_updated_at="2026-03-24T00:00:00+00:00",
            ),
        ),
    )

    def _board(category: str, firebase_uid: str):
        if category == "RELIGIOUS":
            raise RuntimeError("provider down")
        category_enum = DiscoveryCategory(category)
        return DiscoveryBoardResponse(
            category=category_enum,
            featured_card=None,
            family_sections=[],
            metadata=DiscoveryBoardMetadata(
                category_title=category_enum.value.title(),
                category_description="",
                last_updated_at="2026-03-24T00:00:00+00:00",
                active_provider_names=[],
                total_cards=0,
            ),
        )

    monkeypatch.setattr("services.discovery_page_service.get_discovery_board", _board)

    page = get_discovery_page("user-1")

    assert page.boards.academic.category == DiscoveryCategory.ACADEMIC
    assert page.boards.religious.category == DiscoveryCategory.RELIGIOUS
    assert page.metadata.used_cached_fallbacks is True
    assert any("RELIGIOUS:" in error for error in page.metadata.board_errors)
