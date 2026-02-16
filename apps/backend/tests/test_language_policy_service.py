from services.language_policy_service import (
    resolve_book_content_language,
    text_matches_target_language,
    tags_match_target_language,
)


def test_resolve_language_uses_mode_override():
    payload = {
        "title": "Leviathan",
        "author": "Thomas Hobbes",
        "content_language_mode": "TR",
        "summary": "A political philosophy classic.",
    }
    result = resolve_book_content_language(payload)
    assert result["resolved_lang"] == "tr"
    assert result["reason"] == "mode_override_tr"


def test_resolve_language_uses_source_hint_before_metadata():
    payload = {
        "title": "Leviathan",
        "author": "Thomas Hobbes",
        "source_language_hint": "en",
    }
    result = resolve_book_content_language(payload)
    assert result["resolved_lang"] == "en"
    assert result["reason"] == "source_language_hint"


def test_resolve_language_defaults_to_tr_when_ambiguous():
    payload = {
        "title": "Leviathan",
        "author": "Thomas Hobbes",
    }
    result = resolve_book_content_language(payload)
    assert result["resolved_lang"] == "tr"


def test_text_matches_target_language():
    assert text_matches_target_language("Bu kitap toplum duzenini tartisir.", "tr")
    assert not text_matches_target_language("This book discusses social contract.", "tr")


def test_tags_match_target_language():
    assert tags_match_target_language(["siyasal felsefe", "toplum kurami"], "tr")
    assert not tags_match_target_language(["political philosophy", "social contract"], "tr")
