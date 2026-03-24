from models.discovery_models import DiscoveryCard, DiscoveryCategory
from services.discovery_board_service import (
    _Anchor,
    _academic_bridge_queries,
    _academic_fresh_signal_queries,
    _build_card_from_candidate,
    _build_culture_history_cards,
    _build_religious_cards,
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
        personal_note_category="IDEAS",
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


def test_build_card_prefers_candidate_summary():
    card = _build_card_from_candidate(
        category=DiscoveryCategory.CULTURE_HISTORY,
        family="Archive Artifact",
        candidate={
            "title": "Archive artifact",
            "content_chunk": "Type: image | Country: Turkey",
            "provider": "EUROPEANA",
            "reference": "/2058618/object_KUAS_22160561",
            "source_url": "https://www.europeana.eu/item/2058618/object_KUAS_22160561",
            "summary": "An Ottoman textile record with collection context and provenance.",
        },
        anchors=[_make_anchor()],
        fallback_query="ottoman",
        require_reference=True,
        require_date_or_type=True,
    )

    assert card is not None
    assert card.summary == "An Ottoman textile record with collection context and provenance."


def test_build_culture_history_cards_populates_three_families(monkeypatch):
    anchor = _Anchor(
        item_id="book-1",
        item_type="BOOK",
        title="Ottoman Worlds",
        author="Suraiya Faroqhi",
        summary="Cultural and material history of the Ottoman world.",
        tags=["ottoman", "material culture", "archive"],
        reading_status="Reading",
        source_url="",
        personal_note_category="HISTORY",
    )

    monkeypatch.setattr("services.discovery_board_service._seed_queries", lambda category, anchors: ["ottoman"])
    monkeypatch.setattr(
        "services.external_kb_service._fetch_wikidata",
        lambda query, author=None: {
            "qid": "Q123",
            "label": "Ottoman Turkish",
            "description": "Language that was used in the Ottoman Empire.",
            "instance_of_labels": ["language"],
            "part_of_labels": ["Ottoman Empire"],
            "country_labels": ["Turkey"],
            "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/Ottoman_Turkish.png",
        },
    )
    monkeypatch.setattr(
        "services.external_kb_service._search_europeana_direct",
        lambda query, limit=3: [
            {
                "title": "Ottoman textile",
                "content_chunk": "Type: IMAGE | Country: Denmark",
                "provider": "EUROPEANA",
                "reference": "/2058618/object_KUAS_22160561",
                "source_url": "https://www.europeana.eu/item/2058618/object_KUAS_22160561",
                "summary": "A woven Ottoman cover preserved by a Danish cultural collection.",
                "image_url": "https://api.europeana.eu/thumbnail/v2/url.json?uri=example",
                "provenance_provider": "The Danish Agency for Culture",
                "country": "Denmark",
            }
        ],
    )
    monkeypatch.setattr(
        "services.external_kb_service._search_poetrydb_direct",
        lambda query, limit=2: [
            {
                "title": "Ode in Memory of the American Volunteers Fallen for France",
                "content_chunk": "Author: Alan Seeger | Lines: 66 | Memory keeps faith with the fallen.",
                "provider": "POETRYDB",
                "reference": "Alan Seeger",
                "source_url": "https://poetrydb.org/title/Ode%20in%20Memory%20of%20the%20American%20Volunteers%20Fallen%20for%20France",
                "summary": "A memorial poem that opens a lateral cultural path through memory.",
                "author": "Alan Seeger",
            }
        ],
    )

    family_cards = _build_culture_history_cards(
        [anchor],
        ["WIKIDATA", "EUROPEANA", "POETRYDB"],
    )

    assert family_cards["Lineage"]
    assert family_cards["Archive Artifact"]
    assert family_cards["Wild Card"]
    assert family_cards["Lineage"][0].summary.startswith("Language that was used in the Ottoman Empire")
    assert family_cards["Archive Artifact"][0].image_url is not None
    assert any(card.summary.startswith("A memorial poem") for card in family_cards["Wild Card"])


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


def test_academic_fresh_signal_queries_prioritize_recent_terms():
    queries = _academic_fresh_signal_queries([
        _make_anchor(),
        _Anchor(
            item_id="article-1",
            item_type="ARTICLE",
            title="Political Theology and Social Memory",
            author="B. Scholar",
            summary="Academic article",
            tags=["political theology", "memory"],
            reading_status="Finished",
            source_url="https://doi.org/10.1000/x",
        ),
    ])

    assert queries
    assert any("memory" in query.lower() for query in queries)


def test_academic_bridge_queries_require_shared_terms():
    queries = _academic_bridge_queries([
        _Anchor(
            item_id="note-1",
            item_type="PERSONAL_NOTE",
            title="Memory as Method",
            author="",
            summary="",
            tags=["memory", "method"],
            reading_status="",
            source_url="",
            personal_note_category="IDEAS",
        ),
        _Anchor(
            item_id="article-1",
            item_type="ARTICLE",
            title="Collective Memory and Institutions",
            author="B. Scholar",
            summary="",
            tags=["memory", "institutions"],
            reading_status="",
            source_url="https://doi.org/10.1000/x",
        ),
    ])

    assert queries
    assert any("memory" in query.lower() for query in queries)


def _make_religious_anchor() -> _Anchor:
    return _Anchor(
        item_id="note-rel-1",
        item_type="PERSONAL_NOTE",
        title="Nur ve sabir notlari",
        author="",
        summary="Nur, sabir ve dua etrafinda notlar.",
        tags=["nur", "sabir", "dua"],
        reading_status="Reading",
        source_url="",
        personal_note_category="IDEAS",
    )


def _fake_religious_candidates(query: str, limit: int):
    return [
        {
            "provider": "QURANENC",
            "religious_source_kind": "QURAN",
            "canonical_reference": "24:35",
            "reference": "24:35",
            "title": "QuranEnc - Ayet 24:35",
            "content_chunk": "Allah goklerin ve yerin nurudur.",
            "source_url": "https://quran.com/24:35",
        },
        {
            "provider": "HADEETHENC",
            "religious_source_kind": "HADITH",
            "canonical_reference": "42",
            "reference": "42",
            "title": "HadeethEnc - Hadis",
            "content_chunk": "Hadis metni ve aciklamasi.",
            "source_url": "https://hadeethenc.com/tr/browse/hadith/42",
        },
        {
            "provider": "ISLAMHOUSE",
            "religious_source_kind": "INTERPRETATION",
            "canonical_reference": "cat:1/item:2",
            "reference": "cat:1/item:2",
            "title": "Nur tefsiri",
            "content_chunk": "Tefsir metni burada. Nur temasini aciklar.",
            "source_url": "https://islamhouse.com/tr/books/2",
        },
    ]


def _patch_religious_sources(monkeypatch):
    monkeypatch.setattr("services.discovery_board_service._safe_islamic_candidates", _fake_religious_candidates)
    monkeypatch.setattr("services.discovery_board_service.random.choice", lambda seq: seq[0])
    monkeypatch.setattr("services.discovery_board_service.random.shuffle", lambda seq: None)
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._quranenc_fetch_verse",
        lambda verse_key: {
            "sura": "24",
            "aya": "35",
            "translation": "Allah goklerin ve yerin nurudur.",
            "arabic_text": "???? ??? ???????? ??????",
        },
    )
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._quran_foundation_fetch_verse",
        lambda verse_key: {
            "verse_key": "24:35",
            "text_uthmani": "???? ??? ???????? ??????",
            "translations": [{"text": "Allah goklerin ve yerin nurudur."}],
            "words": [
                {"transliteration": {"text": "Allahu"}},
                {"transliteration": {"text": "nuru"}},
                {"transliteration": {"text": "as-samawati"}},
                {"transliteration": {"text": "wal-ard"}},
            ],
        },
    )
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._diyanet_fetch_verse",
        lambda verse_key: {
            "provider": "DIYANET_QURAN",
            "content_chunk": "Allah goklerin ve yerin nurudur.\n???? ??? ???????? ??????\nKaynak: Diyanet",
        },
    )


def test_build_religious_cards_creates_ayet_card_with_arabic_okunus_meal(monkeypatch):
    _patch_religious_sources(monkeypatch)

    cards = _build_religious_cards([_make_religious_anchor()], ["QURANENC", "HADEETHENC", "ISLAMHOUSE"])

    assert len(cards["Ayet Card"]) == 1
    verse_card = cards["Ayet Card"][0]
    evidence = {item.label: item.value for item in verse_card.evidence}

    assert verse_card.title == "Ayet 24:35"
    assert evidence["Arabic"] == "???? ??? ???????? ??????"
    assert "Allahu nuru" in (evidence["Okunus"] or "")
    assert "nurudur" in (evidence["Meal"] or "")


def test_build_religious_cards_creates_bridge_card_with_ayet_tafsir_hadith(monkeypatch):
    _patch_religious_sources(monkeypatch)

    cards = _build_religious_cards([_make_religious_anchor()], ["QURANENC", "HADEETHENC", "ISLAMHOUSE"])

    assert len(cards["Ayet + Hadis Bridge"]) == 1
    bridge_card = cards["Ayet + Hadis Bridge"][0]
    evidence = {item.label: item.value for item in bridge_card.evidence}

    assert "24:35" in (evidence["Ayet"] or "")
    assert "Tefsir metni" in (evidence["Tefsir"] or "")
    assert "Hadis metni" in (evidence["Hadis"] or "")


def test_bridge_card_works_with_verse_and_hadith_only(monkeypatch):
    """Bridge card should succeed when verse + hadith exist but tafsir/interpretation is missing."""

    def _islamic_candidates_no_tafsir(query: str, limit: int):
        return [
            {
                "provider": "QURANENC",
                "religious_source_kind": "QURAN",
                "canonical_reference": "24:35",
                "reference": "24:35",
                "title": "QuranEnc - Ayet 24:35",
                "content_chunk": "Allah goklerin ve yerin nurudur.",
                "source_url": "https://quran.com/24:35",
            },
            {
                "provider": "HADEETHENC",
                "religious_source_kind": "HADITH",
                "canonical_reference": "42",
                "reference": "42",
                "title": "HadeethEnc - Hadis",
                "content_chunk": "Hadis metni ve aciklamasi.",
                "source_url": "https://hadeethenc.com/tr/browse/hadith/42",
            },
            # No INTERPRETATION candidate — simulates ISLAMHOUSE timeout
        ]

    monkeypatch.setattr("services.discovery_board_service._safe_islamic_candidates", _islamic_candidates_no_tafsir)
    monkeypatch.setattr("services.discovery_board_service.random.choice", lambda seq: seq[0])
    monkeypatch.setattr("services.discovery_board_service.random.shuffle", lambda seq: None)
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._quranenc_fetch_verse",
        lambda verse_key: {
            "sura": "24",
            "aya": "35",
            "translation": "Allah goklerin ve yerin nurudur.",
            "arabic_text": "???? ??? ???????? ??????",
        },
    )
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._quran_foundation_fetch_verse",
        lambda verse_key: {
            "verse_key": "24:35",
            "text_uthmani": "???? ??? ???????? ??????",
            "translations": [{"text": "Allah goklerin ve yerin nurudur."}],
            "words": [
                {"transliteration": {"text": "Allahu"}},
                {"transliteration": {"text": "nuru"}},
            ],
        },
    )
    monkeypatch.setattr(
        "services.discovery_board_service.islamic_api_service._diyanet_fetch_verse",
        lambda verse_key: None,
    )

    cards = _build_religious_cards([_make_religious_anchor()], ["QURANENC", "HADEETHENC", "ISLAMHOUSE"])

    assert len(cards["Ayet + Hadis Bridge"]) == 1
    bridge_card = cards["Ayet + Hadis Bridge"][0]
    evidence = {item.label: item.value for item in bridge_card.evidence}

    assert "24:35" in (evidence["Ayet"] or "")
    assert "Hadis metni" in (evidence["Hadis"] or "")
    # Tefsir should NOT be in evidence since no interpretation candidates
    assert "Tefsir" not in evidence
