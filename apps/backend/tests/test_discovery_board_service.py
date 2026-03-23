from models.discovery_models import DiscoveryCard, DiscoveryCategory
from services.discovery_board_service import (
    _Anchor,
    _build_card_from_candidate,
    get_discovery_board,
)


def _make_anchor() -> _Anchor:
    return _Anchor(
        item_id="note-1",
        item_type="PERSONAL_NOTE",
        title="Memory and Metaphor",
        author="A. Writer",
        summary="Themes around metaphor, memory, and image.",
        tags=["memory", "metaphor"],
        reading_status="Reading",
        source_url="",
    )


def test_fresh_signal_requires_date():
    card = _build_card_from_candidate(
        category=DiscoveryCategory.ACADEMIC,
        family="Fresh Signal",
        candidate={
            "title": "Undated paper",
            "content_chunk": "Type: preprint | Authors: Test Author",
            "provider": "ARXIV",
            "source_url": "https://example.com/paper",
            "reference": "arxiv:1234",
        },
        anchors=[_make_anchor()],
        fallback_query="memory",
        require_date=True,
    )

    assert card is None


def test_bridge_requires_two_match_signals():
    card = _build_card_from_candidate(
        category=DiscoveryCategory.ACADEMIC,
        family="Bridge",
        candidate={
            "title": "Metaphor and Memory in Narrative",
            "content_chunk": "Year: 2025 | Authors: A. Writer | Themes: memory, metaphor",
            "provider": "OPENALEX",
            "source_url": "https://example.com/work",
            "reference": "10.1000/test",
        },
        anchors=[_make_anchor()],
        fallback_query="memory",
        min_match_signals=2,
        require_reference=True,
    )

    assert card is not None
    assert card.confidence_label in {"Relevant", "Strong match"}
    assert len(card.anchor_refs) == 1


def test_get_discovery_board_builds_response(monkeypatch):
    featured = DiscoveryCard(
        id="card-1",
        category=DiscoveryCategory.ACADEMIC,
        family="Fresh Signal",
        title="Fresh paper",
        summary="Recent paper summary",
        why_seen="Matches your archive",
        confidence_label="Strong match",
        freshness_label="preprint · 2026-03-20",
        primary_source="Arxiv",
        source_refs=[],
        anchor_refs=[],
        evidence=[],
        actions=[],
        score=0.82,
    )

    monkeypatch.setattr("services.discovery_board_service._load_user_anchors", lambda firebase_uid: [])
    monkeypatch.setattr("services.discovery_board_service._load_user_provider_preferences", lambda firebase_uid: {})
    monkeypatch.setattr("services.discovery_board_service._resolve_active_provider_names", lambda category, preferences: ["ARXIV"])
    monkeypatch.setattr(
        "services.discovery_board_service._build_family_cards",
        lambda category_enum, anchors, active_provider_names: {
            "Fresh Signal": [featured],
            "Bridge": [],
            "Deepen": [],
        },
    )

    board = get_discovery_board("ACADEMIC", "user-1")

    assert board.category == DiscoveryCategory.ACADEMIC
    assert board.featured_card is not None
    assert board.featured_card.title == "Fresh paper"
    assert board.metadata.active_provider_names == ["ARXIV"]
    assert board.metadata.total_cards == 1


def test_build_card_adds_open_source_from_doi_reference():
    card = _build_card_from_candidate(
        category=DiscoveryCategory.ACADEMIC,
        family="Bridge",
        candidate={
            "title": "Paper with DOI",
            "content_chunk": "Year: 2025 | Authors: A. Writer | Themes: memory, metaphor",
            "provider": "CROSSREF",
            "reference": "10.1000/test-doi",
        },
        anchors=[_make_anchor()],
        fallback_query="memory",
        min_match_signals=2,
        require_reference=True,
    )

    assert card is not None
    assert any(ref.url == "https://doi.org/10.1000/test-doi" for ref in card.source_refs)
    assert any(action.type.value == "open_source" for action in card.actions)


def test_get_discovery_board_survives_provider_failures(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("services.discovery_board_service._load_user_anchors", lambda firebase_uid: [_make_anchor()])
    monkeypatch.setattr("services.discovery_board_service._load_user_provider_preferences", lambda firebase_uid: {})
    monkeypatch.setattr("services.discovery_board_service._resolve_active_provider_names", lambda category, preferences: ["ARXIV"])
    monkeypatch.setattr("services.external_kb_service._search_arxiv_direct", _boom)

    board = get_discovery_board("ACADEMIC", "user-1")

    assert board.category == DiscoveryCategory.ACADEMIC
    assert board.metadata.total_cards == 0
    assert board.featured_card is None
