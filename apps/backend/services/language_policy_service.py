from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

LANG_TR = "tr"
LANG_EN = "en"

MODE_AUTO = "AUTO"
MODE_TR = "TR"
MODE_EN = "EN"

_TR_CHARS = set("çğıöşüÇĞİÖŞÜ")

_TR_STOPWORDS = {
    "ve",
    "ile",
    "bir",
    "bu",
    "için",
    "olan",
    "olarak",
    "de",
    "da",
    "ama",
    "fakat",
    "gibi",
    "çok",
    "daha",
    "ancak",
    "üzerine",
    "kitap",
    "eser",
}

_EN_STOPWORDS = {
    "the",
    "and",
    "of",
    "to",
    "in",
    "for",
    "with",
    "on",
    "about",
    "from",
    "book",
    "work",
    "this",
    "that",
    "is",
    "are",
    "was",
    "were",
}

# Domain-oriented English terms that appear frequently in catalog tags.
_EN_TAG_HINTS = {
    "political",
    "philosophy",
    "social",
    "contract",
    "society",
    "ethics",
    "theory",
    "history",
    "economics",
    "psychology",
    "law",
    "state",
}

_TR_PUBLISHER_HINTS = (
    "yayın",
    "yayin",
    "yayinevi",
    "yayınları",
    "yayinlari",
    "kitabevi",
)


def normalize_language_mode(mode: Any) -> str:
    raw = str(mode or MODE_AUTO).strip().upper()
    if raw in {MODE_TR, MODE_EN}:
        return raw
    return MODE_AUTO


def normalize_language_hint(hint: Any) -> Optional[str]:
    raw = str(hint or "").strip().lower()
    if raw in {"tr", "turkish", "turkce", "türkçe"}:
        return LANG_TR
    if raw in {"en", "english", "ingilizce"}:
        return LANG_EN
    return None


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-ZçğıöşüÇĞİÖŞÜ']+", text or "")


def detect_text_language(text: Any) -> Dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        return {"language": None, "confidence": 0.0, "scores": {"tr": 0.0, "en": 0.0}}

    lowered = value.lower()
    tokens = [t.lower() for t in _tokenize(value)]
    token_count = max(1, len(tokens))

    tr_char_hits = sum(1 for ch in value if ch in _TR_CHARS)
    tr_stop_hits = sum(1 for t in tokens if t in _TR_STOPWORDS)
    en_stop_hits = sum(1 for t in tokens if t in _EN_STOPWORDS)
    en_tag_hits = sum(1 for t in tokens if t in _EN_TAG_HINTS)

    tr_score = (tr_char_hits / max(1, len(value))) * 3.0 + (tr_stop_hits / token_count) * 1.3
    en_score = (en_stop_hits / token_count) * 1.5 + (en_tag_hits / token_count) * 1.1

    # Common English morphology hints
    en_score += 0.25 * sum(1 for t in tokens if t.endswith(("tion", "ment", "ness", "ship")))

    # Publisher hint is strong for Turkish catalog entries
    if any(h in lowered for h in _TR_PUBLISHER_HINTS):
        tr_score += 0.8

    gap = abs(tr_score - en_score)
    top = max(tr_score, en_score)
    if top < 0.25 or gap < 0.12:
        return {
            "language": None,
            "confidence": 0.0,
            "scores": {"tr": round(tr_score, 4), "en": round(en_score, 4)},
        }

    lang = LANG_TR if tr_score > en_score else LANG_EN
    confidence = min(1.0, gap / max(0.25, top))
    return {
        "language": lang,
        "confidence": round(confidence, 4),
        "scores": {"tr": round(tr_score, 4), "en": round(en_score, 4)},
    }


def text_matches_target_language(text: Any, target_lang: str) -> bool:
    verdict = detect_text_language(text)
    detected = verdict.get("language")
    if not detected:
        return True
    return detected == target_lang


def tags_match_target_language(tags: Any, target_lang: str) -> bool:
    if not isinstance(tags, list):
        return True

    detected_langs: List[str] = []
    for tag in tags:
        verdict = detect_text_language(tag)
        lang = verdict.get("language")
        if lang:
            detected_langs.append(lang)

    if not detected_langs:
        return True

    tr_count = sum(1 for x in detected_langs if x == LANG_TR)
    en_count = sum(1 for x in detected_langs if x == LANG_EN)
    dominant = LANG_TR if tr_count >= en_count else LANG_EN
    return dominant == target_lang


def resolve_book_content_language(book_data: Dict[str, Any]) -> Dict[str, Any]:
    mode = normalize_language_mode(book_data.get("content_language_mode"))
    if mode == MODE_TR:
        return {
            "resolved_lang": LANG_TR,
            "reason": "mode_override_tr",
            "confidence": 1.0,
            "signals": {"mode": mode},
        }
    if mode == MODE_EN:
        return {
            "resolved_lang": LANG_EN,
            "reason": "mode_override_en",
            "confidence": 1.0,
            "signals": {"mode": mode},
        }

    source_hint = normalize_language_hint(book_data.get("source_language_hint"))
    if source_hint:
        return {
            "resolved_lang": source_hint,
            "reason": "source_language_hint",
            "confidence": 0.8,
            "signals": {"source_language_hint": source_hint},
        }

    # CRITICAL CHANGE: Ignore existing 'summary' or 'tags' to prevent language lock-in.
    # We rely strictly on Metadata (Publisher, Title, Author).

    publisher = str(book_data.get("publisher") or "").strip()
    title = str(book_data.get("title") or "").strip()
    author = str(book_data.get("author") or "").strip()
    
    # Check for strong Turkish Publisher Hints first
    if any(h in publisher.lower() for h in _TR_PUBLISHER_HINTS):
        return {
            "resolved_lang": LANG_TR,
            "reason": "publisher_hint_tr",
            "confidence": 0.9,
            "signals": {"publisher": publisher},
        }

    # Analyze Metadata Text
    metadata_text = f"{publisher}\n{title}\n{author}"
    metadata_verdict = detect_text_language(metadata_text)
    
    if metadata_verdict.get("language"):
        return {
            "resolved_lang": metadata_verdict["language"],
            "reason": "metadata_signal",
            "confidence": metadata_verdict.get("confidence", 0.5),
            "signals": {"metadata_verdict": metadata_verdict},
        }

    # Default Fallback -> TURKISH (User Preference)
    return {
        "resolved_lang": LANG_TR,
        "reason": "default_fallback_tr",
        "confidence": 0.1,
        "signals": {},
    }
