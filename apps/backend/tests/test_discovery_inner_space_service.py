from datetime import datetime, timedelta, timezone

from models.discovery_models import DiscoveryInnerSpaceSlot
from services.discovery_inner_space_service import _InnerSpaceItem, get_discovery_inner_space


def _item(
    *,
    item_id: str,
    title: str,
    item_type: str = "BOOK",
    reading_status: str = "",
    updated_days_ago: int = 0,
    tags: list[str] | None = None,
    total_signals: int = 0,
    insight_count: int = 0,
    highlight_count: int = 0,
    note_count: int = 0,
    page_count: int | None = None,
    max_page_number: int | None = None,
):
    now = datetime.now(timezone.utc)
    updated_at = now - timedelta(days=updated_days_ago)
    return _InnerSpaceItem(
        item_id=item_id,
        item_type=item_type,
        title=title,
        author="Author",
        summary="Summary",
        tags=tags or [],
        reading_status=reading_status,
        source_url="",
        updated_at=updated_at,
        created_at=updated_at - timedelta(days=5),
        page_count=page_count,
        personal_note_category=None,
        total_signals=total_signals,
        insight_count=insight_count,
        highlight_count=highlight_count,
        note_count=note_count,
        last_signal_at=updated_at,
        max_page_number=max_page_number,
    )


def test_get_discovery_inner_space_returns_all_slots(monkeypatch):
    items = [
        _item(
            item_id="book-1",
            title="Active Reading",
            reading_status="Reading",
            updated_days_ago=1,
            tags=["systems", "brutalism"],
            total_signals=4,
            insight_count=2,
            highlight_count=2,
            page_count=200,
            max_page_number=90,
        ),
        _item(
            item_id="book-2",
            title="Fresh Sync",
            updated_days_ago=0,
            tags=["systems"],
            total_signals=1,
            note_count=1,
        ),
        _item(
            item_id="book-3",
            title="Dormant Thread",
            updated_days_ago=45,
            tags=["brutalism", "archives"],
            total_signals=2,
            insight_count=1,
        ),
    ]

    monkeypatch.setattr("services.discovery_inner_space_service._load_inner_space_items", lambda firebase_uid: items)
    monkeypatch.setattr(
        "services.discovery_inner_space_service.get_memory_profile",
        lambda firebase_uid: {
            "active_themes": ["Brutalism", "Systems Thinking"],
            "recurring_sources": ["MUBI"],
        },
    )

    response = get_discovery_inner_space("user-1")

    assert [card.slot for card in response.cards] == [
        DiscoveryInnerSpaceSlot.CONTINUE_THIS,
        DiscoveryInnerSpaceSlot.LATEST_SYNC,
        DiscoveryInnerSpaceSlot.DORMANT_GEM,
        DiscoveryInnerSpaceSlot.THEME_PULSE,
    ]
    assert response.cards[0].title == "Active Reading"
    assert response.cards[0].progress_percent == 45
    assert response.cards[1].title == "Fresh Sync"
    assert response.cards[2].title == "Dormant Thread"
    assert response.cards[3].badge == "2 active themes"


def test_get_discovery_inner_space_derives_themes_without_profile(monkeypatch):
    items = [
        _item(item_id="book-1", title="A", tags=["Semiotics", "Urbanism"], updated_days_ago=1),
        _item(item_id="book-2", title="B", tags=["Semiotics"], updated_days_ago=2),
    ]

    monkeypatch.setattr("services.discovery_inner_space_service._load_inner_space_items", lambda firebase_uid: items)
    monkeypatch.setattr("services.discovery_inner_space_service.get_memory_profile", lambda firebase_uid: None)

    response = get_discovery_inner_space("user-1")

    assert response.metadata.has_memory_profile is False
    assert response.metadata.active_theme_count == 2
    assert "Semiotics" in response.cards[3].summary
