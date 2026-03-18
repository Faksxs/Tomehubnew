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
        }

    history_domain = infer_domain_from_history(chat_history)
    if history_domain:
        return {
            "resolved_domain_mode": history_domain,
            "domain_confidence": 0.72,
            "domain_reason": "history_inference",
            "provider_policy_applied": get_domain_policy(history_domain),
        }

    inferred = _infer_domain(question)
    return {
        "resolved_domain_mode": inferred["domain_mode"],
        "domain_confidence": inferred["confidence"],
        "domain_reason": inferred["reason"],
        "provider_policy_applied": get_domain_policy(inferred["domain_mode"]),
    }


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
        return {"domain_mode": DOMAIN_MODE_RELIGIOUS, "confidence": 0.96, "reason": "religious_signal"}

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
    if best_score <= 0:
        return {"domain_mode": DOMAIN_MODE_AUTO, "confidence": 0.0, "reason": "no_domain_signal"}
    if best_score == second_score:
        return {"domain_mode": DOMAIN_MODE_AUTO, "confidence": 0.35, "reason": "ambiguous_domain_signal"}

    confidence = min(0.92, 0.45 + (best_score * 0.12))
    return {
        "domain_mode": best_mode,
        "confidence": round(confidence, 4),
        "reason": f"keyword_signal:{best_mode.lower()}",
    }
