from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from services.islamic_api_service import is_religious_query

DOMAIN_MODE_AUTO = "AUTO"
DOMAIN_MODE_ACADEMIC = "ACADEMIC"
DOMAIN_MODE_RELIGIOUS = "RELIGIOUS"
DOMAIN_MODE_LITERARY = "LITERARY"
DOMAIN_MODE_CULTURE_HISTORY = "CULTURE_HISTORY"

VALID_DOMAIN_MODES = {
    DOMAIN_MODE_AUTO,
    DOMAIN_MODE_ACADEMIC,
    DOMAIN_MODE_RELIGIOUS,
    DOMAIN_MODE_LITERARY,
    DOMAIN_MODE_CULTURE_HISTORY,
}

PROVIDER_GROUP_LEXICAL_ETYMOLOGY = "LEXICAL_ETYMOLOGY"
PROVIDER_GROUP_BOOK_METADATA = "BOOK_METADATA"
PROVIDER_GROUP_EXTERNAL_KB = "EXTERNAL_KB"
PROVIDER_GROUP_ISLAMIC_API = "ISLAMIC_API"

_ACADEMIC_TERMS = {
    "academic",
    "abstract",
    "article",
    "bibliography",
    "citation",
    "citations",
    "conference",
    "doi",
    "journal",
    "literature",
    "literatur",
    "makale",
    "method",
    "methodology",
    "paper",
    "research",
    "review",
    "scholar",
    "semantic scholar",
    "source",
    "tez",
}

_LITERARY_TERMS = {
    "allegory",
    "close reading",
    "edebi",
    "edebiyat",
    "image",
    "imagery",
    "imge",
    "metafor",
    "metaphor",
    "narrator",
    "novel",
    "poem",
    "poetry",
    "roman",
    "siir",
    "stanza",
    "style",
    "theme",
    "uslup",
}

_CULTURE_HISTORY_TERMS = {
    "archive",
    "archival",
    "civilization",
    "culture",
    "cultural",
    "donem",
    "empire",
    "historical",
    "history",
    "medeniyet",
    "movement",
    "museum",
    "period",
    "tarih",
    "toplum",
}

_RELIGIOUS_EXACT_QURAN_RE = re.compile(r"\b\d{1,3}\s*[:/]\s*\d{1,3}\b")
_RELIGIOUS_EXACT_HADITH_RE = re.compile(
    r"\b(?:hadis|hadith)\s*(?:no|numara|number)?\s*[:#]?\s*\d{1,5}\b",
    re.IGNORECASE,
)
_LITERARY_CLOSE_READING_TERMS = {
    "close reading",
    "imagery",
    "image",
    "imge",
    "metafor",
    "metaphor",
    "motif",
    "narrator",
    "stanza",
    "style",
    "symbol",
    "theme",
    "tone",
    "uslup",
    "satir",
    "kita",
    "paragraph",
    "scene",
}
_LITERARY_AUTHOR_CONTEXT_TERMS = {
    "author",
    "writer",
    "yazar",
    "biyografi",
    "biography",
    "donem",
    "movement",
    "akim",
    "influence",
    "context",
    "baglam",
}
_LITERARY_WORK_CONTEXT_TERMS = {
    "novel",
    "roman",
    "poem",
    "poetry",
    "play",
    "drama",
    "eser",
    "kitap",
    "book",
    "hamlet",
}

_INTERNAL_SOURCE_TYPES = {
    "HIGHLIGHT",
    "PERSONAL_NOTE",
    "PDF",
    "PDF_CHUNK",
    "BOOK_CHUNK",
    "EPUB",
}
_PRIMARY_TEXT_SOURCE_TYPES = {
    "HIGHLIGHT",
    "PDF",
    "PDF_CHUNK",
    "BOOK_CHUNK",
    "EPUB",
}

_DOMAIN_POLICIES: Dict[str, Dict[str, Any]] = {
    DOMAIN_MODE_AUTO: {
        "allowed_provider_groups": [
            PROVIDER_GROUP_EXTERNAL_KB,
            PROVIDER_GROUP_ISLAMIC_API,
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "retrieval_priority": ["internal", "domain_specific", "external_graph", "shared_capabilities"],
        "answer_contract": "GENERIC_EXPLORER",
        "active_provider_names": [
            "GOOGLE_BOOKS",
            "OPEN_LIBRARY",
            "OPENALEX",
            "WIKIDATA",
            "DBPEDIA",
            "ORKG",
            "QURANENC",
            "HADEETHENC",
            "ISLAMHOUSE",
            "QURAN_FOUNDATION",
            "DIYANET_QURAN",
            "HADITH_API_DATASET",
            "QURAN_NLP_DATASET",
            "TMDB",
        ],
        "prepared_provider_names": ["EUROPEANA", "BIG_BOOK_API"],
        "shared_capability_policy": [
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
    },
    DOMAIN_MODE_ACADEMIC: {
        "allowed_provider_groups": [
            PROVIDER_GROUP_EXTERNAL_KB,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "retrieval_priority": ["internal", "academic_external", "external_graph", "shared_capabilities"],
        "answer_contract": "ACADEMIC_REVIEW",
        "active_provider_names": ["OPENALEX", "CROSSREF", "SEMANTIC_SCHOLAR", "SHARE", "ARXIV", "WIKIDATA", "DBPEDIA", "ORKG"],
        "shared_provider_names": ["GOOGLE_BOOKS", "OPEN_LIBRARY"],
        "prepared_provider_names": [],
        "shared_capability_policy": [PROVIDER_GROUP_BOOK_METADATA],
    },
    DOMAIN_MODE_RELIGIOUS: {
        "allowed_provider_groups": [
            PROVIDER_GROUP_ISLAMIC_API,
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "retrieval_priority": ["religious_exact", "religious_context", "internal", "interpretations"],
        "answer_contract": "RELIGIOUS_DIRECT_FIRST",
        "active_provider_names": [
            "QURANENC",
            "HADEETHENC",
            "ISLAMHOUSE",
            "QURAN_FOUNDATION",
            "DIYANET_QURAN",
            "HADITH_API_DATASET",
            "QURAN_NLP_DATASET",
        ],
        "shared_provider_names": ["GOOGLE_BOOKS", "WIKTIONARY", "LINGUA_ROBOT", "WORDS_API"],
        "shared_capability_policy": [PROVIDER_GROUP_LEXICAL_ETYMOLOGY, PROVIDER_GROUP_BOOK_METADATA],
    },
    DOMAIN_MODE_LITERARY: {
        "allowed_provider_groups": [
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_EXTERNAL_KB,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "retrieval_priority": ["primary_text", "literary_context", "internal", "lexical_support"],
        "answer_contract": "LITERARY_CLOSE_READING",
        "active_provider_names": ["GOOGLE_BOOKS", "OPEN_LIBRARY", "GUTENDEX", "POETRYDB", "ART_SEARCH_API"],
        "prepared_provider_names": ["BIG_BOOK_API"],
        "shared_provider_names": ["WIKTIONARY", "LINGUA_ROBOT", "WORDS_API"],
        "shared_capability_policy": [
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
    },
    DOMAIN_MODE_CULTURE_HISTORY: {
        "allowed_provider_groups": [
            PROVIDER_GROUP_EXTERNAL_KB,
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "retrieval_priority": ["archive_context", "internal", "external_graph", "shared_capabilities"],
        "answer_contract": "CULTURE_HISTORY_CONTEXT",
        "active_provider_names": [
            "EUROPEANA",
            "INTERNET_ARCHIVE",
            "WIKIDATA",
            "DBPEDIA",
            "ORKG",
            "TMDB",
            "GOOGLE_BOOKS",
            "OPEN_LIBRARY",
        ],
        "prepared_provider_names": [],
        "shared_capability_policy": [
            PROVIDER_GROUP_LEXICAL_ETYMOLOGY,
            PROVIDER_GROUP_BOOK_METADATA,
        ],
        "shared_provider_names": ["WIKTIONARY", "LINGUA_ROBOT", "WORDS_API"],
    },
}


def normalize_domain_mode(value: Any) -> str:
    mode = str(value or DOMAIN_MODE_AUTO).strip().upper()
    if mode not in VALID_DOMAIN_MODES:
        return DOMAIN_MODE_AUTO
    return mode


def get_domain_policy(domain_mode: Any) -> Dict[str, Any]:
    normalized = normalize_domain_mode(domain_mode)
    return dict(_DOMAIN_POLICIES.get(normalized, _DOMAIN_POLICIES[DOMAIN_MODE_AUTO]))


def domain_allows_provider_group(domain_mode: Any, provider_group: str) -> bool:
    policy = get_domain_policy(domain_mode)
    allowed = {str(item).strip().upper() for item in policy.get("allowed_provider_groups", [])}
    return str(provider_group or "").strip().upper() in allowed


def infer_domain_from_history(chat_history: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    if not chat_history:
        return None
    recent_text = " ".join(str((msg or {}).get("content") or "") for msg in chat_history[-4:])
    resolved = _infer_domain(recent_text)
    if resolved["domain_mode"] == DOMAIN_MODE_AUTO or float(resolved["confidence"]) < 0.55:
        return None
    return str(resolved["domain_mode"])


def resolve_domain_mode(
    question: str,
    *,
    requested_domain_mode: Any = DOMAIN_MODE_AUTO,
    chat_history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    explicit = normalize_domain_mode(requested_domain_mode)
    if explicit != DOMAIN_MODE_AUTO:
        return {
            "resolved_domain_mode": explicit,
            "domain_confidence": 1.0,
            "domain_reason": "user_override",
            "provider_policy_applied": get_domain_policy(explicit),
            "secondary_domain_mode": None,
            "secondary_domain_confidence": 0.0,
            "auto_confidence_band": "high",
        }

    history_domain = infer_domain_from_history(chat_history)
    if history_domain:
        return {
            "resolved_domain_mode": history_domain,
            "domain_confidence": 0.72,
            "domain_reason": "history_inference",
            "provider_policy_applied": get_domain_policy(history_domain),
            "secondary_domain_mode": None,
            "secondary_domain_confidence": 0.0,
            "auto_confidence_band": _resolve_auto_confidence_band(history_domain, 0.72),
        }

    inferred = _infer_domain(question)
    return {
        "resolved_domain_mode": inferred["domain_mode"],
        "domain_confidence": inferred["confidence"],
        "domain_reason": inferred["reason"],
        "provider_policy_applied": get_domain_policy(inferred["domain_mode"]),
        "secondary_domain_mode": inferred.get("secondary_mode"),
        "secondary_domain_confidence": inferred.get("secondary_confidence", 0.0),
        "auto_confidence_band": _resolve_auto_confidence_band(
            inferred["domain_mode"],
            inferred["confidence"],
        ),
    }


def _resolve_auto_confidence_band(domain_mode: Any, confidence: Any) -> str:
    normalized = normalize_domain_mode(domain_mode)
    if normalized == DOMAIN_MODE_AUTO:
        return "low"
    score = float(confidence or 0.0)
    if score >= 0.78:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def infer_religious_query_type(question: str) -> str:
    query = str(question or "").strip()
    normalized = _normalize_ascii(query)
    if not query:
        return "GENERAL_RELIGIOUS"
    if any(term in normalized for term in ("tefsir", "tafsir")) and _RELIGIOUS_EXACT_QURAN_RE.search(query):
        return "TAFSIR_REQUEST"
    if _RELIGIOUS_EXACT_QURAN_RE.search(query):
        return "EXACT_QURAN_VERSE"
    if _RELIGIOUS_EXACT_HADITH_RE.search(query):
        return "EXACT_HADITH"
    if any(token in normalized for token in ("hadis", "hadith", "sahih", "rivayet", "buhari", "muslim", "tirmizi")):
        return "TOPICAL_HADITH"
    if any(token in normalized for token in ("ayet", "sure", "surah", "kuran", "quran", "meal")):
        return "TOPICAL_QURAN"
    return "GENERAL_RELIGIOUS"


def infer_literary_query_type(question: str) -> str:
    query = str(question or "").strip()
    normalized = _normalize_ascii(query)
    if not query:
        return "GENERAL_LITERARY"
    close_hits = _token_hits(normalized, _LITERARY_CLOSE_READING_TERMS)
    author_hits = _token_hits(normalized, _LITERARY_AUTHOR_CONTEXT_TERMS)
    work_hits = _token_hits(normalized, _LITERARY_WORK_CONTEXT_TERMS)

    if close_hits >= max(author_hits, work_hits, 1):
        return "CLOSE_READING"
    if author_hits > max(close_hits, work_hits):
        return "AUTHOR_CONTEXT"
    if work_hits > 0:
        return "WORK_CONTEXT"
    return "GENERAL_LITERARY"


def resolve_explorer_query_profile(
    question: str,
    *,
    resolved_domain_mode: Any,
    domain_confidence: Any,
    requested_domain_mode: Any = DOMAIN_MODE_AUTO,
    domain_reason: Optional[str] = None,
    secondary_domain_mode: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_domain = normalize_domain_mode(resolved_domain_mode)
    requested = normalize_domain_mode(requested_domain_mode)
    confidence_band = _resolve_auto_confidence_band(normalized_domain, domain_confidence)
    profile: Dict[str, Any] = {
        "resolved_domain_mode": normalized_domain,
        "requested_domain_mode": requested,
        "domain_reason": str(domain_reason or ""),
        "domain_confidence": float(domain_confidence or 0.0),
        "auto_confidence_band": confidence_band,
        "secondary_domain_mode": normalize_domain_mode(secondary_domain_mode) if secondary_domain_mode else None,
        "religious_query_type": None,
        "literary_query_type": None,
        "direct_external_limit": 0,
        "lexical_support_limit": 2,
        "islamic_external_limit": 0,
        "source_type_multipliers": {},
        "provider_multipliers": {},
        "religious_kind_multipliers": {},
        "primary_source_types": [],
        "promote_primary_source_top_n": 0,
        "max_same_source_type_top_n": 4,
    }

    if normalized_domain == DOMAIN_MODE_AUTO:
        profile["direct_external_limit"] = 0 if confidence_band == "low" else 1
        profile["lexical_support_limit"] = 1 if confidence_band == "low" else 2
        profile["source_type_multipliers"] = {
            "EXTERNAL_KB": 0.72 if confidence_band == "low" else 0.9,
            "ISLAMIC_EXTERNAL": 0.78 if confidence_band == "low" else 0.96,
            "HIGHLIGHT": 1.12,
            "PDF": 1.08,
            "PDF_CHUNK": 1.08,
            "BOOK_CHUNK": 1.08,
            "EPUB": 1.05,
            "PERSONAL_NOTE": 1.06,
        }
        profile["primary_source_types"] = sorted(_INTERNAL_SOURCE_TYPES)
        profile["promote_primary_source_top_n"] = 3
        profile["max_same_source_type_top_n"] = 4
        return profile

    if normalized_domain == DOMAIN_MODE_RELIGIOUS:
        religious_query_type = infer_religious_query_type(question)
        profile["religious_query_type"] = religious_query_type
        is_exact = religious_query_type in {"EXACT_HADITH", "EXACT_QURAN_VERSE", "TAFSIR_REQUEST"}
        profile["islamic_external_limit"] = 5 if is_exact else 4
        profile["lexical_support_limit"] = 1 if is_exact else 2
        profile["source_type_multipliers"] = {
            "ISLAMIC_EXTERNAL": 1.28 if is_exact else 1.18,
            "HIGHLIGHT": 0.72 if is_exact else 0.88,
            "PDF": 0.74 if is_exact else 0.9,
            "PDF_CHUNK": 0.74 if is_exact else 0.9,
            "BOOK_CHUNK": 0.74 if is_exact else 0.9,
            "EPUB": 0.72 if is_exact else 0.88,
            "PERSONAL_NOTE": 0.7 if is_exact else 0.84,
            "EXTERNAL_KB": 0.55,
        }
        profile["religious_kind_multipliers"] = {
            "HADITH": 1.22,
            "QURAN": 1.24,
            "INTERPRETATION": 0.94 if is_exact else 1.02,
        }
        profile["primary_source_types"] = ["ISLAMIC_EXTERNAL"]
        profile["promote_primary_source_top_n"] = 3
        profile["max_same_source_type_top_n"] = 4 if is_exact else 5
        return profile

    if normalized_domain == DOMAIN_MODE_LITERARY:
        literary_query_type = infer_literary_query_type(question)
        profile["literary_query_type"] = literary_query_type
        if literary_query_type == "CLOSE_READING":
            profile["direct_external_limit"] = 2
            profile["source_type_multipliers"] = {
                "HIGHLIGHT": 1.24,
                "PDF": 1.22,
                "PDF_CHUNK": 1.22,
                "BOOK_CHUNK": 1.22,
                "EPUB": 1.18,
                "PERSONAL_NOTE": 1.0,
                "EXTERNAL_KB": 0.76,
                "ISLAMIC_EXTERNAL": 0.42,
            }
            profile["provider_multipliers"] = {
                "GUTENDEX": 0.92,
                "POETRYDB": 0.96,
                "ART_SEARCH_API": 0.84,
                "GOOGLE_BOOKS": 0.72,
                "OPEN_LIBRARY": 0.72,
                "BIG_BOOK_API": 0.68,
            }
        elif literary_query_type == "AUTHOR_CONTEXT":
            profile["direct_external_limit"] = 5
            profile["source_type_multipliers"] = {
                "HIGHLIGHT": 1.08,
                "PDF": 1.06,
                "PDF_CHUNK": 1.06,
                "BOOK_CHUNK": 1.06,
                "EPUB": 1.04,
                "PERSONAL_NOTE": 0.98,
                "EXTERNAL_KB": 1.08,
                "ISLAMIC_EXTERNAL": 0.42,
            }
            profile["provider_multipliers"] = {
                "GOOGLE_BOOKS": 1.16,
                "OPEN_LIBRARY": 1.14,
                "BIG_BOOK_API": 1.08,
                "GUTENDEX": 0.96,
                "POETRYDB": 0.82,
                "ART_SEARCH_API": 0.88,
            }
        else:
            profile["direct_external_limit"] = 3
            profile["source_type_multipliers"] = {
                "HIGHLIGHT": 1.16,
                "PDF": 1.14,
                "PDF_CHUNK": 1.14,
                "BOOK_CHUNK": 1.14,
                "EPUB": 1.12,
                "PERSONAL_NOTE": 1.0,
                "EXTERNAL_KB": 0.96,
                "ISLAMIC_EXTERNAL": 0.42,
            }
            profile["provider_multipliers"] = {
                "GOOGLE_BOOKS": 1.04,
                "OPEN_LIBRARY": 1.02,
                "GUTENDEX": 1.0,
                "POETRYDB": 1.02,
                "ART_SEARCH_API": 0.92,
                "BIG_BOOK_API": 0.98,
            }
        profile["lexical_support_limit"] = 1
        profile["primary_source_types"] = sorted(_PRIMARY_TEXT_SOURCE_TYPES)
        profile["promote_primary_source_top_n"] = 3
        profile["max_same_source_type_top_n"] = 4
        return profile

    if normalized_domain == DOMAIN_MODE_ACADEMIC:
        profile["direct_external_limit"] = 3 if confidence_band == "high" else 2
        profile["lexical_support_limit"] = 0
        profile["source_type_multipliers"] = {
            "HIGHLIGHT": 1.16,
            "PDF": 1.14,
            "PDF_CHUNK": 1.14,
            "BOOK_CHUNK": 1.12,
            "EPUB": 1.08,
            "PERSONAL_NOTE": 1.05,
            "EXTERNAL_KB": 0.96,
            "ISLAMIC_EXTERNAL": 0.36,
        }
        profile["provider_multipliers"] = {
            "OPENALEX": 1.08,
            "SEMANTIC_SCHOLAR": 1.06,
            "CROSSREF": 1.02,
            "ARXIV": 1.0,
            "SHARE": 0.96,
        }
        profile["primary_source_types"] = sorted(_INTERNAL_SOURCE_TYPES)
        profile["promote_primary_source_top_n"] = 3
        profile["max_same_source_type_top_n"] = 4
        return profile

    if normalized_domain == DOMAIN_MODE_CULTURE_HISTORY:
        profile["direct_external_limit"] = 4
        profile["lexical_support_limit"] = 1
        profile["source_type_multipliers"] = {
            "EXTERNAL_KB": 1.08,
            "GRAPH_RELATION": 1.04,
            "HIGHLIGHT": 1.02,
            "PDF": 1.0,
            "PDF_CHUNK": 1.0,
            "BOOK_CHUNK": 1.0,
            "EPUB": 1.0,
            "PERSONAL_NOTE": 0.96,
            "ISLAMIC_EXTERNAL": 0.44,
        }
        profile["provider_multipliers"] = {
            "EUROPEANA": 1.08,
            "INTERNET_ARCHIVE": 1.06,
            "WIKIDATA": 1.02,
            "DBPEDIA": 1.0,
            "ORKG": 0.96,
        }
        profile["primary_source_types"] = ["EXTERNAL_KB", "GRAPH_RELATION"] + sorted(_INTERNAL_SOURCE_TYPES)
        profile["promote_primary_source_top_n"] = 3
        profile["max_same_source_type_top_n"] = 4
        return profile

    return profile


def compute_source_composition_weight(chunk: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> float:
    if not profile:
        return 1.0

    source_type = str(chunk.get("source_type") or "").strip().upper()
    provider = str(chunk.get("provider") or "").strip().upper()
    religious_kind = str(chunk.get("religious_source_kind") or "").strip().upper()

    weight = 1.0
    weight *= float((profile.get("source_type_multipliers") or {}).get(source_type, 1.0))
    weight *= float((profile.get("provider_multipliers") or {}).get(provider, 1.0))
    if religious_kind:
        weight *= float((profile.get("religious_kind_multipliers") or {}).get(religious_kind, 1.0))
    if bool(chunk.get("is_exact_match")):
        weight *= 1.1

    return max(0.35, min(1.75, weight))


def is_primary_source_for_profile(chunk: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> bool:
    if not profile:
        return False
    source_type = str(chunk.get("source_type") or "").strip().upper()
    primary_types = {
        str(item or "").strip().upper()
        for item in (profile.get("primary_source_types") or [])
        if str(item or "").strip()
    }
    if source_type not in primary_types:
        return False
    if source_type == "ISLAMIC_EXTERNAL":
        return str(chunk.get("religious_source_kind") or "").strip().upper() in {"HADITH", "QURAN"}
    return True


def reorder_chunks_for_domain(chunks: List[Dict[str, Any]], domain_mode: Any) -> List[Dict[str, Any]]:
    normalized = normalize_domain_mode(domain_mode)
    if not chunks:
        return []

    def sort_key(chunk: Dict[str, Any]) -> tuple[float, float]:
        score = float(chunk.get("answerability_score", chunk.get("score", 0.0)) or 0.0)
        source_type = str(chunk.get("source_type") or "").upper()
        is_exact = bool(chunk.get("is_exact_match"))

        priority = 50.0
        if normalized == DOMAIN_MODE_RELIGIOUS:
            if source_type == "ISLAMIC_EXTERNAL" and is_exact:
                priority = 0.0
            elif source_type == "ISLAMIC_EXTERNAL":
                priority = 5.0
            elif source_type in {"HIGHLIGHT", "PERSONAL_NOTE", "PDF", "PDF_CHUNK", "BOOK_CHUNK", "EPUB"}:
                priority = 20.0
            else:
                priority = 35.0
        elif normalized == DOMAIN_MODE_ACADEMIC:
            if source_type in {"HIGHLIGHT", "PERSONAL_NOTE", "PDF", "PDF_CHUNK", "BOOK_CHUNK", "EPUB"}:
                priority = 0.0
            elif source_type == "EXTERNAL_KB":
                priority = 10.0
            elif source_type == "GRAPH_RELATION":
                priority = 20.0
        elif normalized == DOMAIN_MODE_LITERARY:
            if source_type in {"PDF", "PDF_CHUNK", "BOOK_CHUNK", "EPUB", "HIGHLIGHT"}:
                priority = 0.0
            elif source_type == "EXTERNAL_KB":
                priority = 15.0
            elif source_type == "ISLAMIC_EXTERNAL":
                priority = 40.0
        elif normalized == DOMAIN_MODE_CULTURE_HISTORY:
            if source_type == "EXTERNAL_KB":
                priority = 0.0
            elif source_type == "GRAPH_RELATION":
                priority = 8.0
            elif source_type in {"PDF", "PDF_CHUNK", "BOOK_CHUNK", "EPUB", "HIGHLIGHT", "PERSONAL_NOTE"}:
                priority = 15.0

        return (priority, -score)

    return sorted(chunks, key=sort_key)


def domain_prompt_instructions(domain_mode: Any) -> str:
    normalized = normalize_domain_mode(domain_mode)
    if normalized == DOMAIN_MODE_RELIGIOUS:
        return (
            "DOMAIN POLICY: RELIGIOUS.\n"
            "Yaniti su sirayla kur: Dogrudan Kaynak, Kisa Aciklama, Kutuphanemdeki Iliskili Kaynaklar, "
            "Farkli Yorumlar, Sonuc.\n"
            "Exact ayet/hadis varsa onu once ver. Sure veya referans adini tahmin etme; sadece verilen canonical "
            "reference bilgisini kullan."
        )
    if normalized == DOMAIN_MODE_ACADEMIC:
        return (
            "DOMAIN POLICY: ACADEMIC.\n"
            "Yaniti su sirayla kur: Soru/Iddia, Kaynaklar ve Literatur, Karsi Gorusler, Sinirliliklar, Sonuc.\n"
            "Kaynak destekli ol, yontemsel sinirliliklari acikca belirt."
        )
    if normalized == DOMAIN_MODE_LITERARY:
        return (
            "DOMAIN POLICY: LITERARY.\n"
            "Yaniti su sirayla kur: Metin/Parca, Tema ve Uslup, Alternatif Okuma, Sonuc.\n"
            "Yakin okuma yap, imge ve anlatim ozelliklerini belirt."
        )
    if normalized == DOMAIN_MODE_CULTURE_HISTORY:
        return (
            "DOMAIN POLICY: CULTURE_HISTORY.\n"
            "Yaniti su sirayla kur: Baglam, Tarihsel/Kulturel Kaynaklar, Yorum Eksenleri, Sonuc.\n"
            "Donem, baglam ve arsivsel kaniti one cikar."
        )
    return "DOMAIN POLICY: AUTO. Domain belirsizse genel Explorer davranisini koru."


def _normalize_ascii(text: str) -> str:
    return (
        str(text or "")
        .lower()
        .replace("ç", "c")
        .replace("ğ", "g")
        .replace("ı", "i")
        .replace("i̇", "i")
        .replace("ö", "o")
        .replace("ş", "s")
        .replace("ü", "u")
    )


def _token_hits(text: str, phrases: Iterable[str]) -> int:
    normalized = _normalize_ascii(text)
    hits = 0
    for phrase in phrases:
        pattern = str(phrase or "").strip().lower()
        if not pattern:
            continue
        if pattern in normalized:
            hits += 1
    return hits


def _infer_domain(question: str) -> Dict[str, Any]:
    text = str(question or "").strip()
    if not text:
        return {"domain_mode": DOMAIN_MODE_AUTO, "confidence": 0.0, "reason": "empty_query"}

    if is_religious_query(text):
        return {
            "domain_mode": DOMAIN_MODE_RELIGIOUS,
            "confidence": 0.96,
            "reason": "religious_signal",
            "secondary_mode": None,
            "secondary_confidence": 0.0,
        }

    scores = {
        DOMAIN_MODE_ACADEMIC: _token_hits(text, _ACADEMIC_TERMS),
        DOMAIN_MODE_LITERARY: _token_hits(text, _LITERARY_TERMS),
        DOMAIN_MODE_CULTURE_HISTORY: _token_hits(text, _CULTURE_HISTORY_TERMS),
    }

    if re.search(r"\b(doi|isbn|abstract|paper|journal)\b", _normalize_ascii(text)):
        scores[DOMAIN_MODE_ACADEMIC] += 2
    if re.search(r"\b(siir|poem|stanza|narrator|metaphor|metafor)\b", _normalize_ascii(text)):
        scores[DOMAIN_MODE_LITERARY] += 2
    if re.search(r"\b(history|historical|archive|museum|empire|medeniyet|tarih)\b", _normalize_ascii(text)):
        scores[DOMAIN_MODE_CULTURE_HISTORY] += 2

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_mode, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    secondary_mode = ranked[1][0] if len(ranked) > 1 and ranked[1][1] > 0 else None
    secondary_confidence = round(min(0.74, 0.30 + (second_score * 0.10)), 4) if second_score > 0 else 0.0
    if best_score <= 0:
        return {
            "domain_mode": DOMAIN_MODE_AUTO,
            "confidence": 0.0,
            "reason": "no_domain_signal",
            "secondary_mode": secondary_mode,
            "secondary_confidence": secondary_confidence,
        }
    if best_score == second_score:
        return {
            "domain_mode": DOMAIN_MODE_AUTO,
            "confidence": 0.35,
            "reason": "ambiguous_domain_signal",
            "secondary_mode": secondary_mode,
            "secondary_confidence": secondary_confidence,
        }

    confidence = min(0.92, 0.45 + (best_score * 0.12))
    return {
        "domain_mode": best_mode,
        "confidence": round(confidence, 4),
        "reason": f"keyword_signal:{best_mode.lower()}",
        "secondary_mode": secondary_mode,
        "secondary_confidence": secondary_confidence,
    }
