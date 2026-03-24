from __future__ import annotations

import hashlib
import json
import random
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from models.discovery_models import (
    DiscoveryAction,
    DiscoveryActionType,
    DiscoveryAnchorRef,
    DiscoveryBoardMetadata,
    DiscoveryBoardResponse,
    DiscoveryCard,
    DiscoveryCategory,
    DiscoveryEvidence,
    DiscoveryFamilySection,
    DiscoverySourceRef,
)
from services import external_kb_service, islamic_api_service
from services.domain_policy_service import get_domain_policy, normalize_domain_mode, resolve_domain_mode
from services.tmdb_service import search_tmdb_media
from services.user_preferences_service import get_user_preferences
from utils.logger import get_logger

logger = get_logger("discovery_board_service")

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_DATE_RE = re.compile(r"\b(?:9\d{2}|1\d{3}|20\d{2})(?:[-/–]\d{2}(?:[-/–]\d{2})?)?\b")
_YEAR_LABEL_RE = re.compile(r"\b(?:Year|Published|Date):\s*([^|]{0,90})", re.IGNORECASE)
_CENTURY_RE = re.compile(r"\b(?:early|late|mid(?:dle)?)?\s*\d{1,2}(?:st|nd|rd|th)\s+century\b", re.IGNORECASE)
_TYPE_LABEL_RE = re.compile(r"\bType:\s*([A-Za-z][A-Za-z \-]+)", re.IGNORECASE)
_STOPWORDS = {
    "and", "the", "for", "with", "from", "that", "this", "your", "into", "their", "about",
    "ilgili", "ve", "bir", "icin", "gibi", "olan", "title", "author", "year", "date",
    "type", "topics", "authors", "categories", "published", "subjects", "provider",
}


class _Anchor:
    def __init__(
        self,
        *,
        item_id: str,
        item_type: str,
        title: str,
        author: str,
        summary: str,
        tags: List[str],
        reading_status: str,
        source_url: str,
        personal_note_category: str = "",
    ) -> None:
        self.item_id = item_id
        self.item_type = item_type
        self.title = title
        self.author = author
        self.summary = summary
        self.tags = tags
        self.reading_status = reading_status
        self.source_url = source_url
        self.personal_note_category = personal_note_category


_CATEGORY_META: Dict[DiscoveryCategory, Dict[str, Any]] = {
    DiscoveryCategory.ACADEMIC: {
        "title": "Academic",
        "description": "Fresh academic signals from your latest local themes, plus bridge papers that connect multiple archive threads.",
        "hero_family_order": ["Fresh Signal", "Bridge"],
        "families": {
            "Fresh Signal": {
                "description": "Recent papers and preprints inferred from your latest books, articles, and idea notes.",
                "source_label": "ArXiv + OpenAlex + Semantic Scholar + Crossref + SHARE",
            },
            "Bridge": {
                "description": "Works that genuinely connect two or more academic threads already present in your archive.",
                "source_label": "OpenAlex + Semantic Scholar + Crossref + ORKG + SHARE",
            },
        },
    },
    DiscoveryCategory.RELIGIOUS: {
        "title": "Religious",
        "description": "Source-anchored Quran and hadith discovery cards with minimal interpretation and clear references.",
        "hero_family_order": ["Ayet Card", "Ayet + Hadis Bridge"],
        "families": {
            "Ayet Card": {
                "description": "A random verse card with Arabic text, transliteration, and meal.",
                "source_label": "Quran providers",
            },
            "Ayet + Hadis Bridge": {
                "description": "A thematic bridge that combines verse, tafsir context, and related hadith.",
                "source_label": "QuranEnc + HadeethEnc",
            },
        },
    },
    DiscoveryCategory.LITERARY: {
        "title": "Literary",
        "description": "Author continuations, adjacent texts, and selective screen parallels grounded in your archive themes.",
        "hero_family_order": ["Same Author / Next Book", "Parallel Work", "Notes to Screen"],
        "families": {
            "Same Author / Next Book": {
                "description": "The clearest next reading candidate from the same author or a near literary neighbor.",
                "source_label": "Google Books + Gutendex + Open Library",
            },
            "Parallel Work": {
                "description": "Another work, medium, or open text that parallels your current theme.",
                "source_label": "Google Books + Gutendex + TMDb",
            },
            "Notes to Screen": {
                "description": "A film or series card only when the theme overlap is strong and explicit.",
                "source_label": "TMDb",
            },
        },
    },
    DiscoveryCategory.CULTURE_HISTORY: {
        "title": "Culture",
        "description": "Lineage, archive artifacts, and controlled cultural surprises with clear provenance.",
        "hero_family_order": ["Lineage", "Archive Artifact", "Wild Card"],
        "families": {
            "Lineage": {
                "description": "A concept, person, or movement placed inside a relation and origin graph.",
                "source_label": "Wikidata + DBpedia",
            },
            "Archive Artifact": {
                "description": "Objects, scans, and archive items that add time, place, and provenance.",
                "source_label": "Europeana + Internet Archive + Art Search API",
            },
            "Wild Card": {
                "description": "A controlled surprise card that still keeps source and rationale explicit.",
                "source_label": "Europeana + Art Search API + PoetryDB",
            },
        },
    },
}


def get_discovery_board(category: str, firebase_uid: str) -> DiscoveryBoardResponse:
    normalized = normalize_domain_mode(category)
    if normalized == "AUTO":
        raise ValueError("category must be one of ACADEMIC, RELIGIOUS, LITERARY, CULTURE_HISTORY")
    category_enum = DiscoveryCategory(normalized)
    anchors = _load_user_anchors(firebase_uid)
    preferences = _load_user_provider_preferences(firebase_uid)
    active_provider_names = _resolve_active_provider_names(normalized, preferences)

    family_cards = _build_family_cards(
        category_enum=category_enum,
        anchors=anchors,
        active_provider_names=active_provider_names,
    )

    featured_card, family_sections = _select_board_layout(category_enum, family_cards)
    total_cards = (1 if featured_card else 0) + sum(len(section.cards) for section in family_sections)
    meta = _CATEGORY_META[category_enum]
    return DiscoveryBoardResponse(
        category=category_enum,
        featured_card=featured_card,
        family_sections=family_sections,
        metadata=DiscoveryBoardMetadata(
            category_title=str(meta["title"]),
            category_description=str(meta["description"]),
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            active_provider_names=active_provider_names,
            total_cards=total_cards,
        ),
    )


def _build_family_cards(
    *,
    category_enum: DiscoveryCategory,
    anchors: List[_Anchor],
    active_provider_names: List[str],
) -> Dict[str, List[DiscoveryCard]]:
    if category_enum == DiscoveryCategory.ACADEMIC:
        return _build_academic_cards(anchors, active_provider_names)
    if category_enum == DiscoveryCategory.RELIGIOUS:
        return _build_religious_cards(anchors, active_provider_names)
    if category_enum == DiscoveryCategory.LITERARY:
        return _build_literary_cards(anchors, active_provider_names)
    return _build_culture_history_cards(anchors, active_provider_names)


def _load_user_provider_preferences(firebase_uid: str) -> Dict[str, bool]:
    try:
        prefs = get_user_preferences(firebase_uid)
        raw = prefs.get("api_preferences", {})
        return raw if isinstance(raw, dict) else {}
    except Exception as exc:
        logger.warning("discovery board falling back to default provider prefs for uid=%s: %s", firebase_uid, exc)
        return {}


def _resolve_active_provider_names(category: str, preferences: Dict[str, bool]) -> List[str]:
    policy = get_domain_policy(category)
    active = [str(p or "").strip().upper() for p in (policy.get("active_provider_names") or []) if str(p or "").strip()]
    return [provider for provider in active if preferences.get(provider, True)]


def _load_user_anchors(firebase_uid: str, limit: int = 120) -> List[_Anchor]:
    sql = """
        SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON, READING_STATUS, SOURCE_URL, PERSONAL_NOTE_CATEGORY
        FROM (
            SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON, READING_STATUS, SOURCE_URL, PERSONAL_NOTE_CATEGORY
            FROM TOMEHUB_LIBRARY_ITEMS
            WHERE FIREBASE_UID = :p_uid
              AND NVL(SEARCH_VISIBILITY, 'VISIBLE') <> 'EXCLUDED_BY_DEFAULT'
            ORDER BY NVL(UPDATED_AT, CREATED_AT) DESC NULLS LAST
        )
        WHERE ROWNUM <= :p_limit
    """
    anchors: List[_Anchor] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"p_uid": firebase_uid, "p_limit": max(1, min(int(limit), 200))})
                for row in cur.fetchall() or []:
                    item_id = str(row[0] or "").strip()
                    title = str(row[2] or "").strip()
                    if not item_id or not title:
                        continue
                    anchors.append(
                        _Anchor(
                            item_id=item_id,
                            item_type=str(row[1] or "").strip().upper(),
                            title=title,
                            author=str(row[3] or "").strip(),
                            summary=safe_read_clob(row[4])[:2000],
                            tags=_parse_tags(row[5]),
                            reading_status=str(row[6] or "").strip(),
                            source_url=str(row[7] or "").strip(),
                            personal_note_category=str(row[8] or "").strip(),
                        )
                    )
    except Exception as exc:
        logger.warning("discovery board anchor load failed for uid=%s: %s", firebase_uid, exc)
    return anchors


def _parse_tags(value: Any) -> List[str]:
    if value is None:
        return []
    raw = value if isinstance(value, str) else safe_read_clob(value)
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()][:16]
    except Exception:
        pass
    return [part.strip() for part in re.split(r"[;,]", text) if part.strip()][:16]


def _anchor_domain(anchor: _Anchor) -> str:
    combined = " ".join(
        part
        for part in [anchor.title, anchor.author, " ".join(anchor.tags), anchor.summary]
        if part
    )
    resolved = resolve_domain_mode(combined, requested_domain_mode="AUTO")
    return str(resolved.get("resolved_domain_mode") or "AUTO")


def _tokens(value: str) -> List[str]:
    out: List[str] = []
    for token in _TOKEN_RE.findall(str(value or "").lower()):
        token = token.strip()
        if len(token) < 3 or token in _STOPWORDS:
            continue
        out.append(token)
    return out


def _top_tags(anchors: Iterable[_Anchor], *, limit: int = 6) -> List[str]:
    counter: Counter[str] = Counter()
    for anchor in anchors:
        for tag in anchor.tags:
            norm = str(tag or "").strip()
            if norm:
                counter[norm] += 1
    return [tag for tag, _count in counter.most_common(limit)]


def _dedupe_text_values(values: Iterable[str], *, limit: int) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cleaned)
        if len(deduped) >= limit:
            break
    return deduped


def _anchor_title_terms(anchor: _Anchor, *, limit: int = 3) -> List[str]:
    return _dedupe_text_values(_tokens(anchor.title), limit=limit)


def _anchor_signal_terms(anchor: _Anchor, *, limit: int = 4) -> List[str]:
    values: List[str] = []
    values.extend(tag for tag in anchor.tags if str(tag or "").strip())
    if anchor.personal_note_category and anchor.personal_note_category.strip().upper() not in {"IDEAS", "GENERAL", "NOTES"}:
        values.append(anchor.personal_note_category.strip())
    if anchor.item_type == "ARTICLE" and anchor.title.strip():
        values.append(anchor.title.strip())
    if not values and anchor.title.strip():
        values.extend(_anchor_title_terms(anchor, limit=limit))
    return _dedupe_text_values(values, limit=limit)


def _is_academic_anchor(anchor: _Anchor) -> bool:
    if anchor.item_type == "ARTICLE":
        return True
    if anchor.item_type == "PERSONAL_NOTE" and anchor.personal_note_category.strip().upper() == "IDEAS" and bool(anchor.tags):
        return True
    if external_kb_service.compute_academic_scope(anchor.tags):
        return True
    return _anchor_domain(anchor) == DiscoveryCategory.ACADEMIC.value


def _academic_anchor_pool(anchors: List[_Anchor], *, limit: int = 10) -> List[_Anchor]:
    academic = [anchor for anchor in anchors if _is_academic_anchor(anchor)]
    return academic[:limit] if academic else anchors[: max(0, min(limit, len(anchors)))]


def _academic_fresh_signal_queries(anchors: List[_Anchor]) -> List[str]:
    queries: List[str] = []
    for anchor in anchors[:4]:
        signal_terms = _anchor_signal_terms(anchor, limit=4)
        if len(signal_terms) >= 2:
            queries.append(f"{signal_terms[0]} {signal_terms[1]}")
        if signal_terms:
            queries.append(f"{signal_terms[0]} research")
        if anchor.item_type == "ARTICLE" and anchor.title.strip():
            queries.append(anchor.title.strip())
    return _dedupe_text_values(queries, limit=5)


def _academic_bridge_queries(anchors: List[_Anchor]) -> List[str]:
    term_counts: Counter[str] = Counter()
    display_names: Dict[str, str] = {}
    term_anchor_ids: Dict[str, set[str]] = {}

    for anchor in anchors[:8]:
        anchor_terms = _anchor_signal_terms(anchor, limit=4)
        for term in anchor_terms:
            key = term.lower()
            display_names.setdefault(key, term)
            term_anchor_ids.setdefault(key, set()).add(anchor.item_id)

    for key, anchor_ids in term_anchor_ids.items():
        if len(anchor_ids) >= 2:
            term_counts[key] = len(anchor_ids)

    recurring_terms = [display_names[key] for key, _count in term_counts.most_common(4)]
    queries: List[str] = []
    if len(recurring_terms) >= 2:
        queries.append(f"{recurring_terms[0]} {recurring_terms[1]}")
        queries.append(f"{recurring_terms[0]} {recurring_terms[1]} research")
        queries.append(f"{recurring_terms[0]} {recurring_terms[1]} theory")
    elif recurring_terms:
        queries.append(f"{recurring_terms[0]} literature review")
        queries.append(f"{recurring_terms[0]} research")
    elif len(anchors) >= 2:
        first_terms = _anchor_signal_terms(anchors[0], limit=2)
        second_terms = _anchor_signal_terms(anchors[1], limit=2)
        if first_terms and second_terms:
            queries.append(f"{first_terms[0]} {second_terms[0]}")
            queries.append(f"{first_terms[0]} {second_terms[0]} research")

    return _dedupe_text_values(queries, limit=4)


def _select_domain_anchors(category: DiscoveryCategory, anchors: List[_Anchor]) -> List[_Anchor]:
    domain = category.value
    picked = [anchor for anchor in anchors if _anchor_domain(anchor) == domain]
    if picked:
        return picked[:12]
    return anchors[:12]


def _default_category_query(category: DiscoveryCategory) -> str:
    defaults = {
        DiscoveryCategory.ACADEMIC: "social theory research",
        DiscoveryCategory.RELIGIOUS: "rahmet ayet hadis",
        DiscoveryCategory.LITERARY: "memory and metaphor",
        DiscoveryCategory.CULTURE_HISTORY: "ottoman archive history",
    }
    return defaults[category]


def _seed_queries(category: DiscoveryCategory, anchors: List[_Anchor]) -> List[str]:
    domain_anchors = _select_domain_anchors(category, anchors)
    top_tags = _top_tags(domain_anchors)
    recent = domain_anchors[0] if domain_anchors else None
    queries: List[str] = []

    if recent and recent.title:
        queries.append(recent.title)
    if recent and recent.author and category == DiscoveryCategory.LITERARY:
        queries.append(recent.author)
    if top_tags:
        queries.extend(top_tags[:2])
    if recent and recent.tags:
        queries.extend(recent.tags[:2])

    category_specific: List[str] = []
    if category == DiscoveryCategory.ACADEMIC and top_tags:
        category_specific = [f"{top_tags[0]} literature review", f"{top_tags[0]} methodology"]
    elif category == DiscoveryCategory.RELIGIOUS and top_tags:
        category_specific = [f"{top_tags[0]} ayet", f"{top_tags[0]} hadis"]
    elif category == DiscoveryCategory.LITERARY and top_tags:
        category_specific = [f"{top_tags[0]} novel", f"{top_tags[0]} poetry"]
    elif category == DiscoveryCategory.CULTURE_HISTORY and top_tags:
        category_specific = [f"{top_tags[0]} archive", f"{top_tags[0]} history"]
    queries.extend(category_specific)

    if not queries:
        queries.append(_default_category_query(category))

    deduped: List[str] = []
    seen = set()
    for query in queries:
        normalized = re.sub(r"\s+", " ", str(query or "").strip())
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:4]


def _match_anchor(candidate_text: str, anchors: List[_Anchor]) -> Tuple[Optional[_Anchor], List[DiscoveryEvidence], int]:
    matches = _collect_anchor_matches(candidate_text, anchors, limit=1)
    if not matches:
        return None, [], 0
    anchor, evidence, score = matches[0]
    return anchor, evidence, score


def _collect_anchor_matches(
    candidate_text: str,
    anchors: List[_Anchor],
    *,
    limit: int = 3,
) -> List[Tuple[_Anchor, List[DiscoveryEvidence], int]]:
    candidate_tokens = set(_tokens(candidate_text))
    matches: List[Tuple[_Anchor, List[DiscoveryEvidence], int]] = []
    for anchor in anchors:
        evidence: List[DiscoveryEvidence] = []
        score = 0
        tag_hits = [tag for tag in anchor.tags if set(_tokens(tag)).intersection(candidate_tokens)]
        if tag_hits:
            evidence.append(DiscoveryEvidence(kind="tag_overlap", label="Theme overlap", value=", ".join(tag_hits[:2])))
            score += min(2, len(tag_hits))

        title_tokens = set(_tokens(anchor.title))
        title_overlap = title_tokens.intersection(candidate_tokens)
        if title_overlap:
            evidence.append(DiscoveryEvidence(kind="title_overlap", label="Anchor match", value=anchor.title))
            score += 1

        author_tokens = set(_tokens(anchor.author))
        author_overlap = author_tokens.intersection(candidate_tokens)
        if author_overlap and anchor.author:
            evidence.append(DiscoveryEvidence(kind="author_overlap", label="Author context", value=anchor.author))
            score += 1

        if score > 0:
            matches.append((anchor, evidence, score))

    matches.sort(key=lambda item: item[2], reverse=True)
    return matches[:limit]


def _parse_year_or_date(value: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    labeled = _YEAR_LABEL_RE.search(text)
    if labeled:
        label_text = str(labeled.group(1) or "").strip()
        raw = _DATE_RE.search(label_text)
        if raw:
            return str(raw.group(0) or "").strip()
        century = _CENTURY_RE.search(label_text)
        if century:
            return str(century.group(0) or "").strip()
    raw = _DATE_RE.search(text)
    if raw:
        return str(raw.group(0) or "").strip()
    century = _CENTURY_RE.search(text)
    if century:
        return str(century.group(0) or "").strip()
    return None


def _parse_type_label(value: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    match = _TYPE_LABEL_RE.search(text)
    if match:
        return str(match.group(1) or "").strip()
    return None


def _confidence_label(score: float) -> str:
    if score >= 0.76:
        return "Strong match"
    if score >= 0.61:
        return "Relevant"
    return "Exploratory"


def _card_id(category: DiscoveryCategory, family: str, provider: str, title: str, reference: str) -> str:
    raw = "||".join([category.value, family, provider, title, reference])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _summary_from_content(content: str) -> str:
    parts = [part.strip() for part in str(content or "").split("|") if part.strip()]
    if not parts:
        return ""
    cleaned = []
    for part in parts[:3]:
        cleaned.append(part.rstrip("."))
    return ". ".join(cleaned)[:280]


def _join_fragments(values: Iterable[str], *, limit: int = 3) -> str:
    parts = [str(value or "").strip() for value in values if str(value or "").strip()]
    return ". ".join(parts[:limit])[:280]


def _build_why_seen(
    *,
    category: DiscoveryCategory,
    provider: str,
    evidence: List[DiscoveryEvidence],
    fallback_query: str,
    anchor: Optional[_Anchor],
) -> str:
    if evidence and anchor:
        labels = ", ".join(e.value or e.label for e in evidence[:2] if (e.value or e.label))
        if labels:
            return f"Matches your archive through {labels} and extends that path via {provider.title()}."
    if anchor:
        return f"Extends your {category.value.replace('_', ' ').title()} archive around {anchor.title} using {provider.title()}."
    if fallback_query:
        return f"Built for the {category.value.replace('_', ' ').title()} board around the theme '{fallback_query}' using {provider.title()}."
    return f"Built for the {category.value.replace('_', ' ').title()} board using {provider.title()}."


def _source_refs_from_candidate(candidate: Dict[str, Any], *, extra_refs: Optional[List[DiscoverySourceRef]] = None) -> List[DiscoverySourceRef]:
    refs: List[DiscoverySourceRef] = []
    
    # 1. Resolve source URL, prioritizing valid public links over internal API endpoints
    raw_url = str(candidate.get("source_url") or "").strip()
    is_api_url = any(x in raw_url.lower() for x in [
        "api.", "/api/v1/", ".p.rapidapi.com", "special:entitydata", 
        "quranenc.com/api", "diyanet.gov.tr/api"
    ])
    
    source_url = ""
    if raw_url and not is_api_url:
        source_url = raw_url
    else:
        source_url = _fallback_source_url(candidate) or ""

    reference = str(candidate.get("reference") or candidate.get("canonical_reference") or "").strip()
    provider = str(candidate.get("provider") or "Source").strip()
    
    if source_url:
        refs.append(DiscoverySourceRef(label=f"{provider} source", url=source_url, kind="source"))
    if reference and not reference.startswith("http"):
        refs.append(DiscoverySourceRef(label=reference, url=None, kind="reference"))
    
    if extra_refs:
        refs.extend(extra_refs)
        
    deduped: List[DiscoverySourceRef] = []
    seen = set()
    for ref in refs:
        key = (ref.label, ref.url or "", ref.kind or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _fallback_source_url(candidate: Dict[str, Any]) -> Optional[str]:
    provider = str(candidate.get("provider") or "").strip().upper()
    reference = str(candidate.get("reference") or candidate.get("canonical_reference") or "").strip()
    title = str(candidate.get("title") or "").strip()

    if reference.startswith("http://") or reference.startswith("https://"):
        return reference
    if reference.startswith("10."):
        return f"https://doi.org/{quote(reference, safe='/:')}"
        
    # Religious Source Resolution
    if provider == "QURANENC" and ":" in reference:
        return f"https://quranenc.com/en/browse/turkish_rshd/{reference.replace(':', '/')}"
    if provider == "HADEETHENC" and reference.isdigit():
        return f"https://hadeethenc.com/tr/browse/hadith/{reference}"
    if provider == "QURAN_FOUNDATION" and ":" in reference:
        return f"https://quran.com/{reference}"
    if provider == "DIYANET_QURAN" and ":" in reference:
        # Diyanet uses a specific structure, fallback to a search if exact is hard
        return f"https://kuran.diyanet.gov.tr/mushaf"
    if provider == "ISLAMHOUSE" and reference.isdigit():
        return f"https://islamhouse.com/tr/main/{reference}"

    # Academic Source Resolution
    if provider == "ARXIV":
        arxiv_ref = reference.replace("arxiv:", "").replace("ARXIV:", "").strip()
        if arxiv_ref:
            return f"https://arxiv.org/abs/{quote(arxiv_ref)}"
    if provider == "OPENALEX" and reference:
        alex_id = reference.split("/")[-1] if "/" in reference else reference
        return f"https://openalex.org/{quote(alex_id)}"
    if provider == "SEMANTIC_SCHOLAR" and reference:
        return f"https://www.semanticscholar.org/paper/{quote(reference)}"
    if provider == "ORKG" and reference:
        return f"https://orkg.org/paper/{quote(reference)}"
    if provider == "CROSSREF" and reference:
        return f"https://doi.org/{quote(reference)}"

    # Culture & Literary Source Resolution
    if provider == "WIKIDATA" and reference and reference.upper().startswith("Q"):
        return f"https://www.wikidata.org/wiki/{quote(reference)}"
    if provider == "DBPEDIA" and reference:
        return f"https://dbpedia.org/page/{quote(reference)}"
    if provider == "EUROPEANA" and reference:
        return f"https://www.europeana.eu/item/{quote(reference)}"
    if provider == "INTERNET_ARCHIVE" and reference:
        return f"https://archive.org/details/{quote(reference)}"
    if provider == "GUTENDEX" and reference.isdigit():
        return f"https://www.gutenberg.org/ebooks/{reference}"
    if provider == "ART_SEARCH_API" and reference:
        return f"https://www.artic.edu/artworks/{quote(reference)}"
    if provider == "POETRYDB" and title:
        return f"https://poetrydb.org/title/{quote(title)}"

    # Entertainment/Media
    if provider == "TMDB" and reference.startswith("tmdb:"):
        parts = reference.split(":")
        if len(parts) == 3 and parts[2].isdigit():
            kind = "tv" if parts[1] == "tv" else "movie"
            return f"https://www.themoviedb.org/{kind}/{parts[2]}"
            
    # Fallbacks for titles
    if provider == "GOOGLE_BOOKS" and title:
        return f"https://books.google.com/books?q={quote(title)}"
    if provider == "OPEN_LIBRARY" and title:
        return f"https://openlibrary.org/search?q={quote(title)}"
    
    return None


def _safe_fetch_list(provider_name: str, fetcher: Any, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    try:
        result = fetcher(*args, **kwargs)
        if not result:
            return []
        return list(result)
    except Exception as exc:
        logger.warning("discovery board provider list fetch failed provider=%s error=%s", provider_name, exc)
        return []


def _safe_fetch_value(provider_name: str, fetcher: Any, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    try:
        result = fetcher(*args, **kwargs)
        return result if isinstance(result, dict) and result else None
    except Exception as exc:
        logger.warning("discovery board provider value fetch failed provider=%s error=%s", provider_name, exc)
        return None


def _safe_search_tmdb(query: str, max_results: int) -> List[Dict[str, Any]]:
    try:
        return list(search_tmdb_media(query, kind="multi", max_results=max_results) or [])
    except Exception as exc:
        logger.warning("discovery board TMDB fetch failed query=%s error=%s", query, exc)
        return []


def _safe_islamic_candidates(query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        candidates, _diag = islamic_api_service.get_islamic_external_candidates(query, limit=limit, force_religious=True)
        return list(candidates or [])
    except Exception as exc:
        logger.warning("discovery board islamic fetch failed query=%s error=%s", query, exc)
        return []


def _actions_for_card(
    *,
    title: str,
    summary: str,
    why_seen: str,
    source_refs: List[DiscoverySourceRef],
    anchor: Optional[_Anchor],
) -> List[DiscoveryAction]:
    prompt_seed = f"{title}\n\nWhy this now: {why_seen}\n\nSummary: {summary}".strip()
    actions: List[DiscoveryAction] = [
        DiscoveryAction(type=DiscoveryActionType.ASK_LOGOSCHAT, label="Ask in LogosChat", prompt_seed=prompt_seed),
        DiscoveryAction(
            type=DiscoveryActionType.SEND_TO_FLUX,
            label="Open in Flux",
            prompt_seed=anchor.title if anchor else title,
            anchor_id=anchor.item_id if anchor else None,
        ),
        DiscoveryAction(type=DiscoveryActionType.SAVE_FOR_LATER, label="Save for later", prompt_seed=prompt_seed),
    ]
    primary_ref = next((ref for ref in source_refs if ref.url), None)
    if primary_ref:
        actions.append(DiscoveryAction(type=DiscoveryActionType.OPEN_SOURCE, label="Open source", url=primary_ref.url))
    if anchor:
        actions.append(DiscoveryAction(type=DiscoveryActionType.OPEN_ANCHOR, label="Open anchor", anchor_id=anchor.item_id))
    return actions


_PROVIDER_BASE_SCORES: Dict[str, float] = {
    "ARXIV": 0.68,
    "OPENALEX": 0.7,
    "CROSSREF": 0.64,
    "SEMANTIC_SCHOLAR": 0.66,
    "SHARE": 0.61,
    "ORKG": 0.75,
    "QURANENC": 0.82,
    "QURAN_FOUNDATION": 0.8,
    "DIYANET_QURAN": 0.78,
    "HADEETHENC": 0.8,
    "ISLAMHOUSE": 0.67,
    "GOOGLE_BOOKS": 0.64,
    "OPEN_LIBRARY": 0.61,
    "BIG_BOOK_API": 0.58,
    "GUTENDEX": 0.65,
    "TMDB": 0.6,
    "WIKIDATA": 0.68,
    "DBPEDIA": 0.63,
    "EUROPEANA": 0.68,
    "INTERNET_ARCHIVE": 0.64,
    "ART_SEARCH_API": 0.66,
    "POETRYDB": 0.57,
}


def _provider_label(provider: str) -> str:
    text = str(provider or "").strip().replace("_", " ")
    return text.title() if text else "Source"


def _candidate_text(candidate: Dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            str(candidate.get("title") or "").strip(),
            str(candidate.get("summary") or "").strip(),
            str(candidate.get("content_chunk") or "").strip(),
            str(candidate.get("reference") or candidate.get("canonical_reference") or "").strip(),
        ]
        if part
    )


def _image_url_from_candidate(candidate: Dict[str, Any]) -> Optional[str]:
    for key in ("image_url", "coverUrl", "cover_url", "thumbnail", "thumbnail_url"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return None


def _build_card_from_candidate(
    *,
    category: DiscoveryCategory,
    family: str,
    candidate: Dict[str, Any],
    anchors: List[_Anchor],
    fallback_query: str,
    min_match_signals: int = 0,
    require_reference: bool = False,
    require_date: bool = False,
    require_date_or_type: bool = False,
    extra_refs: Optional[List[DiscoverySourceRef]] = None,
    extra_evidence: Optional[List[DiscoveryEvidence]] = None,
    score_bonus: float = 0.0,
    title_override: Optional[str] = None,
    summary_override: Optional[str] = None,
    anchor_override: Optional[_Anchor] = None,
    anchor_candidates: Optional[List[_Anchor]] = None,
    require_distinct_anchor_count: int = 0,
) -> Optional[DiscoveryCard]:
    provider = str(candidate.get("provider") or "").strip().upper()
    title = str(title_override or candidate.get("title") or "").strip()
    content = str(candidate.get("content_chunk") or "").strip()
    if not provider or not title:
        return None

    anchor = anchor_override
    evidence: List[DiscoveryEvidence] = list(extra_evidence or [])
    match_signals = 0
    anchor_refs: List[DiscoveryAnchorRef] = []
    if anchor_override:
        anchor_evidence = [
            DiscoveryEvidence(kind="anchor_override", label="Anchor context", value=anchor_override.title)
        ]
        evidence.extend(anchor_evidence)
        match_signals = len(anchor_evidence)
        anchor_refs.append(DiscoveryAnchorRef(item_id=anchor_override.item_id, title=anchor_override.title, item_type=anchor_override.item_type))
    else:
        candidate_anchor_pool = anchor_candidates if anchor_candidates is not None else anchors
        anchor_matches = _collect_anchor_matches(_candidate_text(candidate), candidate_anchor_pool, limit=3)
        if require_distinct_anchor_count and len(anchor_matches) < require_distinct_anchor_count:
            return None
        if anchor_matches:
            anchor = anchor_matches[0][0]
            evidence.extend(anchor_matches[0][1])
            match_signals = len(anchor_matches[0][1])
            for matched_anchor, _anchor_evidence, _score in anchor_matches:
                anchor_refs.append(
                    DiscoveryAnchorRef(item_id=matched_anchor.item_id, title=matched_anchor.title, item_type=matched_anchor.item_type)
                )
            if len(anchor_matches) > 1:
                bridge_titles = ", ".join(match[0].title for match in anchor_matches[:3])
                evidence.append(DiscoveryEvidence(kind="bridge_anchor", label="Bridge path", value=bridge_titles))

    if min_match_signals and match_signals < min_match_signals:
        return None

    parsed_date = _parse_year_or_date(content)
    parsed_type = _parse_type_label(content)
    if require_date and not parsed_date:
        return None
    if require_date_or_type and not (parsed_date or parsed_type):
        return None

    source_refs = _source_refs_from_candidate(candidate, extra_refs=extra_refs)
    if require_reference and not any((ref.kind or "").lower() == "reference" for ref in source_refs):
        return None
    if not source_refs:
        return None

    summary = str(summary_override or candidate.get("summary") or "").strip() or _summary_from_content(content)
    if not summary:
        summary = title
    why_seen = _build_why_seen(
        category=category,
        provider=provider,
        evidence=evidence,
        fallback_query=fallback_query,
        anchor=anchor,
    ).strip()
    if not why_seen:
        return None

    provider_score = _PROVIDER_BASE_SCORES.get(provider, 0.58)
    freshness_bonus = 0.04 if parsed_date else 0.0
    anchor_bonus = min(0.18, 0.05 * max(match_signals, len(anchor_refs)))
    metadata_penalty = -0.07 if len(summary) < 40 else 0.0
    score = max(0.0, min(0.98, provider_score + freshness_bonus + anchor_bonus + metadata_penalty + score_bonus))

    freshness_label: Optional[str] = None
    reference_text = str(candidate.get("reference") or candidate.get("canonical_reference") or "").strip()
    if parsed_date and parsed_type:
        freshness_label = f"{parsed_type} · {parsed_date}"
    elif parsed_date:
        freshness_label = parsed_date
    elif reference_text:
        freshness_label = reference_text

    return DiscoveryCard(
        id=_card_id(category, family, provider, title, reference_text or title),
        category=category,
        family=family,
        title=title,
        summary=summary,
        why_seen=why_seen,
        confidence_label=_confidence_label(score),
        freshness_label=freshness_label,
        primary_source=_provider_label(provider),
        source_refs=source_refs,
        image_url=_image_url_from_candidate(candidate),
        anchor_refs=anchor_refs,
        evidence=evidence,
        actions=_actions_for_card(
            title=title,
            summary=summary,
            why_seen=why_seen,
            source_refs=source_refs,
            anchor=anchor,
        ),
        score=score,
    )


def _culture_summary_for_lineage(candidate: Dict[str, Any]) -> str:
    description = str(candidate.get("summary") or candidate.get("description") or "").strip()
    fragments: List[str] = []
    if description:
        fragments.append(description)
    if candidate.get("instance_of_labels"):
        fragments.append("Instance of: " + ", ".join((candidate.get("instance_of_labels") or [])[:3]))
    elif candidate.get("subclass_of_labels"):
        fragments.append("Subclass of: " + ", ".join((candidate.get("subclass_of_labels") or [])[:3]))
    if candidate.get("part_of_labels"):
        fragments.append("Part of: " + ", ".join((candidate.get("part_of_labels") or [])[:2]))
    elif candidate.get("country_labels"):
        fragments.append("Context: " + ", ".join((candidate.get("country_labels") or [])[:2]))
    if candidate.get("types"):
        fragments.append("Type: " + ", ".join((candidate.get("types") or [])[:3]))
    return _join_fragments(fragments)


def _culture_summary_for_artifact(candidate: Dict[str, Any]) -> str:
    description = str(candidate.get("summary") or "").strip()
    fragments: List[str] = []
    if description:
        fragments.append(description)
    if candidate.get("provenance_provider"):
        fragments.append(f"Held by {candidate.get('provenance_provider')}")
    if candidate.get("creator"):
        fragments.append(f"Creator: {candidate.get('creator')}")
    if candidate.get("artist"):
        fragments.append(f"Artist: {candidate.get('artist')}")
    if candidate.get("country"):
        fragments.append(f"Country: {candidate.get('country')}")
    if candidate.get("mediatype"):
        fragments.append(f"Type: {candidate.get('mediatype')}")
    return _join_fragments(fragments)


def _culture_summary_for_wild_card(candidate: Dict[str, Any]) -> str:
    description = str(candidate.get("summary") or "").strip()
    if description:
        return description[:280]
    return _summary_from_content(str(candidate.get("content_chunk") or ""))


def _culture_evidence(candidate: Dict[str, Any], family: str) -> List[DiscoveryEvidence]:
    evidence: List[DiscoveryEvidence] = []
    provider = str(candidate.get("provider") or "").strip()
    if family == "Lineage":
        for label in (candidate.get("instance_of_labels") or [])[:2]:
            evidence.append(DiscoveryEvidence(kind="lineage_relation", label="Instance", value=str(label)))
        for label in (candidate.get("part_of_labels") or [])[:1]:
            evidence.append(DiscoveryEvidence(kind="lineage_relation", label="Part of", value=str(label)))
        for label in (candidate.get("country_labels") or [])[:1]:
            evidence.append(DiscoveryEvidence(kind="lineage_context", label="Context", value=str(label)))
        for label in (candidate.get("types") or [])[:1]:
            evidence.append(DiscoveryEvidence(kind="lineage_type", label="Type", value=str(label)))
    elif family == "Archive Artifact":
        if candidate.get("provenance_provider"):
            evidence.append(DiscoveryEvidence(kind="provenance", label="Collection", value=str(candidate.get("provenance_provider"))))
        if candidate.get("creator"):
            evidence.append(DiscoveryEvidence(kind="creator", label="Creator", value=str(candidate.get("creator"))))
        if candidate.get("artist"):
            evidence.append(DiscoveryEvidence(kind="creator", label="Artist", value=str(candidate.get("artist"))))
        if candidate.get("country"):
            evidence.append(DiscoveryEvidence(kind="place", label="Country", value=str(candidate.get("country"))))
        if candidate.get("rights"):
            evidence.append(DiscoveryEvidence(kind="rights", label="Rights", value=str(candidate.get("rights"))))
    elif family == "Wild Card":
        evidence.append(DiscoveryEvidence(kind="wild_card", label="Unexpected angle", value=provider.title()))
        if candidate.get("author"):
            evidence.append(DiscoveryEvidence(kind="author", label="Author", value=str(candidate.get("author"))))
        if candidate.get("artist"):
            evidence.append(DiscoveryEvidence(kind="creator", label="Artist", value=str(candidate.get("artist"))))
    return evidence[:4]


def _dedupe_and_limit(cards: Iterable[DiscoveryCard], *, limit: int) -> List[DiscoveryCard]:
    deduped: List[DiscoveryCard] = []
    seen = set()
    provider_counts: Dict[str, int] = {}
    for card in sorted(cards, key=lambda item: item.score, reverse=True):
        ref_key = card.source_refs[0].label if card.source_refs else card.title
        key = (card.family.lower(), card.title.strip().lower(), ref_key.strip().lower())
        if key in seen:
            continue
        provider_key = card.primary_source.lower()
        provider_count = provider_counts.get(provider_key, 0)
        if provider_count >= 2 and len(deduped) >= max(2, limit // 2):
            continue
        seen.add(key)
        provider_counts[provider_key] = provider_count + 1
        deduped.append(card)
        if len(deduped) >= limit:
            break
    return deduped


def _build_academic_cards(anchors: List[_Anchor], active_provider_names: List[str]) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    academic_anchors = _academic_anchor_pool(anchors, limit=10)
    fresh_queries = _academic_fresh_signal_queries(academic_anchors) or _seed_queries(DiscoveryCategory.ACADEMIC, anchors)
    bridge_queries = _academic_bridge_queries(academic_anchors)
    family_cards: Dict[str, List[DiscoveryCard]] = {"Fresh Signal": [], "Bridge": []}

    fresh_anchor_pool = academic_anchors[:4] or anchors[:4]
    bridge_anchor_pool = academic_anchors[:8] or anchors[:8]
    bridge_anchor_requirement = 2 if len(bridge_anchor_pool) >= 2 else 1
    bridge_signal_requirement = 2 if bridge_anchor_requirement == 1 else 0

    for query in fresh_queries:
        for provider_name, fetcher, score_bonus in (
            ("ARXIV", external_kb_service._search_arxiv_direct, 0.07),
            ("OPENALEX", external_kb_service._search_openalex_direct, 0.05),
            ("SEMANTIC_SCHOLAR", external_kb_service._search_semantic_scholar_direct, 0.04),
            ("CROSSREF", external_kb_service._search_crossref_direct, 0.03),
            ("SHARE", external_kb_service._search_share_direct, 0.02),
        ):
            if provider_name not in active:
                continue
            for candidate in _safe_fetch_list(provider_name, fetcher, query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Fresh Signal",
                    candidate=candidate,
                    anchors=fresh_anchor_pool,
                    fallback_query=query,
                    require_date=True,
                    score_bonus=score_bonus,
                )
                if card:
                    family_cards["Fresh Signal"].append(card)

    for query in bridge_queries:
        for provider_name, fetcher, score_bonus in (
            ("OPENALEX", external_kb_service._search_openalex_direct, 0.07),
            ("SEMANTIC_SCHOLAR", external_kb_service._search_semantic_scholar_direct, 0.06),
            ("CROSSREF", external_kb_service._search_crossref_direct, 0.05),
            ("SHARE", external_kb_service._search_share_direct, 0.04),
        ):
            if provider_name not in active:
                continue
            for candidate in _safe_fetch_list(provider_name, fetcher, query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Bridge",
                    candidate=candidate,
                    anchors=bridge_anchor_pool,
                    anchor_candidates=bridge_anchor_pool,
                    fallback_query=query,
                    min_match_signals=bridge_signal_requirement,
                    require_reference=True,
                    require_distinct_anchor_count=bridge_anchor_requirement,
                    score_bonus=score_bonus,
                )
                if card:
                    family_cards["Bridge"].append(card)

        if "ORKG" in active:
            orkg = _safe_fetch_value("ORKG", external_kb_service._fetch_orkg, query, None)
            if orkg and orkg.get("research_fields"):
                research_labels = [
                    str(field.get("label") or "").strip()
                    for field in (orkg.get("research_fields") or [])
                    if isinstance(field, dict) and str(field.get("label") or "").strip()
                ]
                authors = [
                    str(author.get("display_name") or "").strip()
                    for author in (orkg.get("authors") or [])
                    if isinstance(author, dict) and str(author.get("display_name") or "").strip()
                ]
                content_parts = []
                if authors:
                    content_parts.append(f"Authors: {', '.join(authors[:3])}")
                if research_labels:
                    content_parts.append(f"Research fields: {', '.join(research_labels[:4])}")
                content_parts.append("Type: structured research view")
                bridge_candidate = {
                    "title": str(orkg.get("title") or query).strip(),
                    "content_chunk": " | ".join(content_parts),
                    "provider": "ORKG",
                    "source_url": str(orkg.get("url") or "").strip() or None,
                    "reference": str(orkg.get("doi") or "").strip() or None,
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Bridge",
                    candidate=bridge_candidate,
                    anchors=bridge_anchor_pool,
                    anchor_candidates=bridge_anchor_pool,
                    fallback_query=query,
                    min_match_signals=bridge_signal_requirement,
                    require_distinct_anchor_count=bridge_anchor_requirement,
                    score_bonus=0.08,
                )
                if card:
                    family_cards["Bridge"].append(card)

    return {family: _dedupe_and_limit(cards, limit=4) for family, cards in family_cards.items()}


def _religious_theme_candidates(anchors: List[_Anchor]) -> List[Tuple[str, Optional[_Anchor]]]:
    weighted: Counter[str] = Counter()
    labels: Dict[str, str] = {}
    anchors_by_key: Dict[str, _Anchor] = {}
    for anchor in anchors[:24]:
        note_category = str(anchor.personal_note_category or "").strip().upper()
        base_weight = 5 if note_category == "IDEAS" else 4 if anchor.item_type in {"BOOK", "ARTICLE"} else 3
        if str(anchor.reading_status or "").strip().upper() == "READING":
            base_weight += 1
        for raw_tag in anchor.tags[:5]:
            label = re.sub(r"\s+", " ", str(raw_tag or "").strip())
            key = label.lower()
            if len(label) < 3 or key in _STOPWORDS:
                continue
            weighted[key] += base_weight
            labels.setdefault(key, label)
            anchors_by_key.setdefault(key, anchor)
    ordered = [(labels[key], anchors_by_key.get(key)) for key, _count in weighted.most_common(6)]
    if ordered:
        return ordered
    return [(topic, None) for topic in ["sabir", "rahmet", "hikmet", "dua", "adalet", "tevbe"]]



def _curated_random_verse_key() -> str:
    return random.choice([
        "2:152",
        "2:153",
        "2:186",
        "2:286",
        "3:159",
        "8:46",
        "13:28",
        "16:90",
        "24:35",
        "39:53",
        "39:10",
        "93:5",
        "94:5",
        "94:6",
    ])



def _pick_anchor_for_theme(theme: str, anchors: List[_Anchor]) -> Optional[_Anchor]:
    matches = _collect_anchor_matches(theme, anchors, limit=1)
    if matches:
        return matches[0][0]
    return anchors[0] if anchors else None



def _pick_religious_verse_candidate(theme: str, active_provider_names: List[str]) -> Optional[Dict[str, Any]]:
    active = set(active_provider_names)
    seen = set()
    candidates: List[Dict[str, Any]] = []
    for query in [f"{theme} ayet", f"{theme} kuran", theme]:
        for candidate in _safe_islamic_candidates(query, limit=10):
            provider = str(candidate.get("provider") or "").strip().upper()
            reference = str(candidate.get("canonical_reference") or candidate.get("reference") or "").strip()
            if provider not in active:
                continue
            if str(candidate.get("religious_source_kind") or "").strip().upper() != "QURAN":
                continue
            if ":" not in reference:
                continue
            key = (provider, reference)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    if candidates:
        return random.choice(candidates[: min(4, len(candidates))])

    reference = _curated_random_verse_key()
    fallback_candidates: List[Dict[str, Any]] = []
    quranenc_exact = islamic_api_service._normalize_quranenc_exact(islamic_api_service._quranenc_fetch_verse(reference) or {})
    if quranenc_exact:
        fallback_candidates.append(quranenc_exact)
    quran_foundation_exact = islamic_api_service._normalize_quran_foundation_exact(islamic_api_service._quran_foundation_fetch_verse(reference) or {})
    if quran_foundation_exact:
        fallback_candidates.append(quran_foundation_exact)
    diyanet_exact = islamic_api_service._diyanet_fetch_verse(reference)
    if diyanet_exact:
        fallback_candidates.append(diyanet_exact)
    return fallback_candidates[0] if fallback_candidates else None



def _contains_arabic_text(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(value or "")))



def _compact_text(value: str, limit: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."



def _extract_quran_meal(
    quranenc_verse: Optional[Dict[str, Any]],
    quran_foundation_verse: Optional[Dict[str, Any]],
    diyanet_candidate: Optional[Dict[str, Any]],
) -> str:
    translation = str((quranenc_verse or {}).get("translation") or "").strip()
    if translation:
        return translation
    translations = (quran_foundation_verse or {}).get("translations") or []
    if isinstance(translations, list):
        for item in translations:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if text:
                return text
    for line in str((diyanet_candidate or {}).get("content_chunk") or "").splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("Kaynak:") or _contains_arabic_text(cleaned):
            continue
        return cleaned
    return ""



def _extract_quran_arabic(
    quranenc_verse: Optional[Dict[str, Any]],
    quran_foundation_verse: Optional[Dict[str, Any]],
    diyanet_candidate: Optional[Dict[str, Any]],
) -> str:
    for candidate in [
        str((quran_foundation_verse or {}).get("text_uthmani") or "").strip(),
        str((quranenc_verse or {}).get("arabic_text") or "").strip(),
    ]:
        if candidate:
            return candidate
    for line in str((diyanet_candidate or {}).get("content_chunk") or "").splitlines():
        cleaned = line.strip()
        if _contains_arabic_text(cleaned):
            return cleaned
    return ""



def _extract_quran_transliteration(quran_foundation_verse: Optional[Dict[str, Any]]) -> str:
    words = (quran_foundation_verse or {}).get("words") or []
    if not isinstance(words, list):
        return ""
    parts: List[str] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        transliteration = word.get("transliteration") or {}
        if isinstance(transliteration, dict):
            text = str(transliteration.get("text") or "").strip()
        else:
            text = str(transliteration or "").strip()
        if text:
            parts.append(text)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()



def _religious_verse_refs(reference: str) -> List[DiscoverySourceRef]:
    refs: List[DiscoverySourceRef] = []
    verse_key = str(reference or "").strip()
    if verse_key:
        refs.append(DiscoverySourceRef(label=verse_key, kind="reference"))
        if ":" in verse_key:
            surah_id, ayah_id = verse_key.split(":", 1)
            refs.append(DiscoverySourceRef(label="Quran.com", url=f"https://quran.com/{verse_key}", kind="source"))
            refs.append(DiscoverySourceRef(label="QuranEnc", url=f"https://quranenc.com/tr/browse/turkish_rshd/{surah_id}/{ayah_id}", kind="source"))
    return refs



def _build_random_verse_card(anchors: List[_Anchor], active_provider_names: List[str]) -> Optional[DiscoveryCard]:
    theme_candidates = _religious_theme_candidates(anchors)
    random.shuffle(theme_candidates)
    for theme, suggested_anchor in theme_candidates:
        verse_candidate = _pick_religious_verse_candidate(theme, active_provider_names)
        if not verse_candidate:
            continue
        verse_key = str(verse_candidate.get("canonical_reference") or verse_candidate.get("reference") or "").strip()
        if ":" not in verse_key:
            continue
        quranenc_verse = _safe_fetch_value("QURANENC_EXACT", islamic_api_service._quranenc_fetch_verse, verse_key) or {}
        quran_foundation_verse = _safe_fetch_value("QURAN_FOUNDATION_EXACT", islamic_api_service._quran_foundation_fetch_verse, verse_key) or {}
        diyanet_candidate = _safe_fetch_value("DIYANET_EXACT", islamic_api_service._diyanet_fetch_verse, verse_key) or {}
        arabic = _extract_quran_arabic(quranenc_verse, quran_foundation_verse, diyanet_candidate)
        transliteration = _extract_quran_transliteration(quran_foundation_verse)
        meal = _extract_quran_meal(quranenc_verse, quran_foundation_verse, diyanet_candidate)
        if not arabic or not meal:
            continue
        anchor = suggested_anchor or _pick_anchor_for_theme(theme, anchors)
        source_refs = _religious_verse_refs(verse_key)
        summary = _compact_text(meal, limit=220)
        why_seen = f"Recent archive tags pointed this board toward '{theme}', so one verse card surfaced first."
        score = 0.84
        evidence = [
            DiscoveryEvidence(kind="theme", label="Theme", value=theme),
            DiscoveryEvidence(kind="arabic", label="Arabic", value=arabic),
            DiscoveryEvidence(kind="transliteration", label="Okunus", value=transliteration or "Okunus verisi alinmadi."),
            DiscoveryEvidence(kind="translation", label="Meal", value=meal),
        ]
        anchor_refs = [DiscoveryAnchorRef(item_id=anchor.item_id, title=anchor.title, item_type=anchor.item_type)] if anchor else []
        title = f"Ayet {verse_key}"
        return DiscoveryCard(
            id=_card_id(DiscoveryCategory.RELIGIOUS, "Ayet Card", "QURAN_STACK", title, verse_key),
            category=DiscoveryCategory.RELIGIOUS,
            family="Ayet Card",
            title=title,
            summary=summary,
            why_seen=why_seen,
            confidence_label=_confidence_label(score),
            freshness_label=verse_key,
            primary_source="Quran sources",
            source_refs=source_refs,
            anchor_refs=anchor_refs,
            evidence=evidence,
            actions=_actions_for_card(
                title=title,
                summary=summary,
                why_seen=why_seen,
                source_refs=source_refs,
                anchor=anchor,
            ),
            score=score,
        )
    return None



def _bridge_queries(theme: str) -> List[str]:
    return [
        f"{theme} ayet hadis",
        f"{theme} tefsir hadis",
        f"{theme} hadis",
    ]



def _build_verse_hadith_bridge_card(anchors: List[_Anchor], active_provider_names: List[str]) -> Optional[DiscoveryCard]:
    active = set(active_provider_names)
    theme_candidates = _religious_theme_candidates(anchors)
    random.shuffle(theme_candidates)
    for theme, suggested_anchor in theme_candidates:
        verse_candidates: List[Dict[str, Any]] = []
        hadith_candidates: List[Dict[str, Any]] = []
        interpretive_candidates: List[Dict[str, Any]] = []
        seen = set()
        for query in _bridge_queries(theme):
            for candidate in _safe_islamic_candidates(query, limit=10):
                provider = str(candidate.get("provider") or "").strip().upper()
                kind = str(candidate.get("religious_source_kind") or "").strip().upper()
                reference = str(candidate.get("canonical_reference") or candidate.get("reference") or "").strip()
                key = (provider, kind, reference)
                if provider not in active or key in seen:
                    continue
                seen.add(key)
                if kind == "QURAN" and ":" in reference:
                    verse_candidates.append(candidate)
                elif kind == "HADITH":
                    hadith_candidates.append(candidate)
                elif kind == "INTERPRETATION":
                    interpretive_candidates.append(candidate)
        if not verse_candidates or not (hadith_candidates or interpretive_candidates):
            continue

        verse = verse_candidates[0]
        hadith = hadith_candidates[0] if hadith_candidates else None
        tafsir = interpretive_candidates[0] if interpretive_candidates else None
        verse_key = str(verse.get("canonical_reference") or verse.get("reference") or "").strip()
        if ":" not in verse_key:
            continue
        quranenc_verse = _safe_fetch_value("QURANENC_EXACT", islamic_api_service._quranenc_fetch_verse, verse_key) or {}
        quran_foundation_verse = _safe_fetch_value("QURAN_FOUNDATION_EXACT", islamic_api_service._quran_foundation_fetch_verse, verse_key) or {}
        diyanet_candidate = _safe_fetch_value("DIYANET_EXACT", islamic_api_service._diyanet_fetch_verse, verse_key) or {}
        meal = _extract_quran_meal(quranenc_verse, quran_foundation_verse, diyanet_candidate) or _summary_from_content(str(verse.get("content_chunk") or ""))
        tafsir_text = _compact_text(str(tafsir.get("content_chunk") or ""), limit=320) if tafsir else ""
        hadith_text = _compact_text(str(hadith.get("content_chunk") or ""), limit=320) if hadith else ""
        if not meal or not (tafsir_text or hadith_text):
            continue

        hadith_ref = str((hadith or {}).get("canonical_reference") or (hadith or {}).get("reference") or "").strip()
        anchor = suggested_anchor or _pick_anchor_for_theme(theme, anchors)
        source_refs = _religious_verse_refs(verse_key)
        hadith_url = str((hadith or {}).get("source_url") or "").strip()
        tafsir_url = str((tafsir or {}).get("source_url") or "").strip()
        if hadith_url:
            source_refs.append(DiscoverySourceRef(label="HadeethEnc", url=hadith_url, kind="source"))
        if tafsir_url:
            source_refs.append(DiscoverySourceRef(label="IslamHouse", url=tafsir_url, kind="source"))
        if hadith_ref:
            source_refs.append(DiscoverySourceRef(label=f"Hadis {hadith_ref}", kind="reference"))

        bridge_parts = [part for part in ["ayet", "tefsir" if tafsir_text else "", "hadis" if hadith_text else ""] if part]
        bridge_label = ", ".join(bridge_parts)
        summary = f"{theme.title()} hattinda {bridge_label} ayni kartta toplandi."
        why_seen = f"'{theme}' temasi son arsiv akisinla eslesti; {bridge_label} ayni baglamda kuruldu."
        score = 0.88 if (tafsir_text and hadith_text) else 0.82
        evidence = [
            DiscoveryEvidence(kind="theme", label="Theme", value=theme),
            DiscoveryEvidence(kind="verse", label="Ayet", value=f"{verse_key} - {meal}"),
        ]
        if tafsir_text:
            evidence.append(DiscoveryEvidence(kind="tafsir", label="Tefsir", value=tafsir_text))
        if hadith_text:
            evidence.append(DiscoveryEvidence(kind="hadith", label="Hadis", value=hadith_text))
        anchor_refs = [DiscoveryAnchorRef(item_id=anchor.item_id, title=anchor.title, item_type=anchor.item_type)] if anchor else []
        title = f"{theme.title()} bridge"
        return DiscoveryCard(
            id=_card_id(DiscoveryCategory.RELIGIOUS, "Ayet + Hadis Bridge", "RELIGIOUS_BRIDGE", title, verse_key),
            category=DiscoveryCategory.RELIGIOUS,
            family="Ayet + Hadis Bridge",
            title=title,
            summary=summary,
            why_seen=why_seen,
            confidence_label=_confidence_label(score),
            freshness_label=verse_key,
            primary_source="Quran + Hadith",
            source_refs=source_refs,
            anchor_refs=anchor_refs,
            evidence=evidence,
            actions=_actions_for_card(
                title=title,
                summary=summary,
                why_seen=why_seen,
                source_refs=source_refs,
                anchor=anchor,
            ),
            score=score,
        )
    return None



def _build_curated_fallback_verse_card(anchors: List[_Anchor]) -> Optional[DiscoveryCard]:
    """Fallback: pick a curated well-known verse directly when live API queries fail."""
    verse_key = _curated_random_verse_key()
    quranenc_verse = _safe_fetch_value("QURANENC_EXACT", islamic_api_service._quranenc_fetch_verse, verse_key) or {}
    quran_foundation_verse = _safe_fetch_value("QURAN_FOUNDATION_EXACT", islamic_api_service._quran_foundation_fetch_verse, verse_key) or {}
    diyanet_candidate = _safe_fetch_value("DIYANET_EXACT", islamic_api_service._diyanet_fetch_verse, verse_key) or {}
    arabic = _extract_quran_arabic(quranenc_verse, quran_foundation_verse, diyanet_candidate)
    transliteration = _extract_quran_transliteration(quran_foundation_verse)
    meal = _extract_quran_meal(quranenc_verse, quran_foundation_verse, diyanet_candidate)
    if not arabic or not meal:
        return None
    anchor = anchors[0] if anchors else None
    source_refs = _religious_verse_refs(verse_key)
    summary = _compact_text(meal, limit=220)
    why_seen = "A curated verse card surfaced as a fallback while live discovery sources were unavailable."
    score = 0.78
    evidence = [
        DiscoveryEvidence(kind="theme", label="Theme", value="curated"),
        DiscoveryEvidence(kind="arabic", label="Arabic", value=arabic),
        DiscoveryEvidence(kind="transliteration", label="Okunus", value=transliteration or "Okunus verisi alinmadi."),
        DiscoveryEvidence(kind="translation", label="Meal", value=meal),
    ]
    anchor_refs = [DiscoveryAnchorRef(item_id=anchor.item_id, title=anchor.title, item_type=anchor.item_type)] if anchor else []
    title = f"Ayet {verse_key}"
    return DiscoveryCard(
        id=_card_id(DiscoveryCategory.RELIGIOUS, "Ayet Card", "QURAN_STACK", title, verse_key),
        category=DiscoveryCategory.RELIGIOUS,
        family="Ayet Card",
        title=title,
        summary=summary,
        why_seen=why_seen,
        confidence_label=_confidence_label(score),
        freshness_label=verse_key,
        primary_source="Quran sources",
        source_refs=source_refs,
        anchor_refs=anchor_refs,
        evidence=evidence,
        actions=_actions_for_card(
            title=title,
            summary=summary,
            why_seen=why_seen,
            source_refs=source_refs,
            anchor=anchor,
        ),
        score=score,
    )



def _build_religious_cards(anchors: List[_Anchor], active_provider_names: List[str]) -> Dict[str, List[DiscoveryCard]]:
    family_cards: Dict[str, List[DiscoveryCard]] = {"Ayet Card": [], "Ayet + Hadis Bridge": []}

    verse_card = _build_random_verse_card(anchors, active_provider_names)
    if verse_card:
        family_cards["Ayet Card"].append(verse_card)
    else:
        # Curated fallback: pick a random well-known verse directly
        fallback_card = _build_curated_fallback_verse_card(anchors)
        if fallback_card:
            family_cards["Ayet Card"].append(fallback_card)

    bridge_card = _build_verse_hadith_bridge_card(anchors, active_provider_names)
    if bridge_card:
        family_cards["Ayet + Hadis Bridge"].append(bridge_card)

    return family_cards


def _build_literary_cards(anchors: List[_Anchor], active_provider_names: List[str]) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    queries = _seed_queries(DiscoveryCategory.LITERARY, anchors)
    family_cards: Dict[str, List[DiscoveryCard]] = {
        "Same Author / Next Book": [],
        "Parallel Work": [],
        "Notes to Screen": [],
    }

    metadata_providers = [provider for provider in active_provider_names if provider in {"GOOGLE_BOOKS", "OPEN_LIBRARY", "BIG_BOOK_API"}]
    for query in queries:
        if metadata_providers:
            metadata_candidates = _safe_fetch_list(
                "LITERARY_METADATA",
                external_kb_service._search_literary_book_metadata_direct,
                query,
                limit=4,
                active_providers=metadata_providers,
            )
            for candidate in metadata_candidates:
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.LITERARY,
                    family="Same Author / Next Book",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    score_bonus=0.03,
                )
                if card:
                    family_cards["Same Author / Next Book"].append(card)

            for candidate in metadata_candidates:
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.LITERARY,
                    family="Parallel Work",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    min_match_signals=1,
                    score_bonus=0.01,
                )
                if card:
                    family_cards["Parallel Work"].append(card)

        if "GUTENDEX" in active:
            for candidate in _safe_fetch_list("GUTENDEX", external_kb_service._search_gutendex_direct, query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.LITERARY,
                    family="Parallel Work",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    min_match_signals=1,
                    score_bonus=0.04,
                )
                if card:
                    family_cards["Parallel Work"].append(card)

        if "TMDB" in active:
            for row in _safe_search_tmdb(query, max_results=4):
                tmdb_id = row.get("tmdbId")
                tmdb_kind = str(row.get("tmdbKind") or "").strip()
                candidate = {
                    "title": str(row.get("title") or "").strip(),
                    "content_chunk": " | ".join(
                        part for part in [
                            f"Type: {'series' if tmdb_kind == 'tv' else 'film'}",
                            f"Year: {row.get('year')}" if row.get("year") else "",
                            str(row.get("summary") or "").strip(),
                        ] if part
                    ),
                    "provider": "TMDB",
                    "reference": str(row.get("tmdbToken") or "").strip(),
                    "source_url": (
                        f"https://www.themoviedb.org/{'tv' if tmdb_kind == 'tv' else 'movie'}/{tmdb_id}"
                        if tmdb_id else None
                    ),
                    "image_url": str(row.get("coverUrl") or "").strip() or None,
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.LITERARY,
                    family="Notes to Screen",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    min_match_signals=2,
                    require_reference=True,
                    score_bonus=0.02,
                )
                if card:
                    family_cards["Notes to Screen"].append(card)

    return {family: _dedupe_and_limit(cards, limit=4) for family, cards in family_cards.items()}


def _build_culture_history_cards(anchors: List[_Anchor], active_provider_names: List[str]) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    queries = _seed_queries(DiscoveryCategory.CULTURE_HISTORY, anchors)
    family_cards: Dict[str, List[DiscoveryCard]] = {"Lineage": [], "Archive Artifact": [], "Wild Card": []}
    culture_anchor_pool = _select_domain_anchors(DiscoveryCategory.CULTURE_HISTORY, anchors) or anchors

    for query in queries:
        if "WIKIDATA" in active:
            wikidata = _safe_fetch_value("WIKIDATA", external_kb_service._fetch_wikidata, query, None)
            if wikidata:
                lineage_summary = _culture_summary_for_lineage(wikidata)
                candidate = {
                    "title": str(wikidata.get("label") or query).strip(),
                    "content_chunk": " | ".join(
                        part for part in [
                            str(wikidata.get("description") or "").strip(),
                            f"Type: relation graph",
                        ] if part
                    ),
                    "provider": "WIKIDATA",
                    "reference": str(wikidata.get("qid") or "").strip() or None,
                    "source_url": (
                        f"https://www.wikidata.org/wiki/{wikidata.get('qid')}"
                        if wikidata.get("qid") else None
                    ),
                    "summary": lineage_summary,
                    "instance_of_labels": list(wikidata.get("instance_of_labels") or []),
                    "subclass_of_labels": list(wikidata.get("subclass_of_labels") or []),
                    "part_of_labels": list(wikidata.get("part_of_labels") or []),
                    "country_labels": list(wikidata.get("country_labels") or []),
                    "image_url": str(wikidata.get("image_url") or "").strip() or None,
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Lineage",
                    candidate=candidate,
                    anchors=culture_anchor_pool,
                    fallback_query=query,
                    summary_override=lineage_summary,
                    extra_evidence=_culture_evidence(candidate, "Lineage"),
                    score_bonus=0.05,
                )
                if card:
                    family_cards["Lineage"].append(card)
        if "DBPEDIA" in active:
            dbpedia = _safe_fetch_value("DBPEDIA", external_kb_service._fetch_dbpedia, query, None)
            if dbpedia:
                lineage_summary = _culture_summary_for_lineage(dbpedia)
                candidate = {
                    "title": str(dbpedia.get("label") or query).strip(),
                    "content_chunk": " | ".join(
                        part for part in [
                            str(dbpedia.get("description") or "").strip(),
                            f"Type: {', '.join((dbpedia.get('types') or [])[:3])}" if dbpedia.get("types") else "",
                        ] if part
                    ),
                    "provider": "DBPEDIA",
                    "reference": str(dbpedia.get("resource_uri") or "").strip() or None,
                    "source_url": str(dbpedia.get("resource_uri") or "").strip() or None,
                    "summary": lineage_summary,
                    "types": list(dbpedia.get("types") or []),
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Lineage",
                    candidate=candidate,
                    anchors=culture_anchor_pool,
                    fallback_query=query,
                    summary_override=lineage_summary,
                    extra_evidence=_culture_evidence(candidate, "Lineage"),
                    score_bonus=0.02,
                )
                if card:
                    family_cards["Lineage"].append(card)

        for provider_name, fetcher in (
            ("EUROPEANA", external_kb_service._search_europeana_direct),
            ("INTERNET_ARCHIVE", external_kb_service._search_internet_archive_direct),
            ("ART_SEARCH_API", external_kb_service._search_artic_direct),
        ):
            if provider_name not in active:
                continue
            for candidate in _safe_fetch_list(provider_name, fetcher, query, limit=3):
                artifact_summary = _culture_summary_for_artifact(candidate)
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Archive Artifact",
                    candidate=candidate,
                    anchors=culture_anchor_pool,
                    fallback_query=query,
                    require_date_or_type=True,
                    require_reference=True,
                    summary_override=artifact_summary,
                    extra_evidence=_culture_evidence(candidate, "Archive Artifact"),
                    score_bonus=0.03,
                )
                if card:
                    family_cards["Archive Artifact"].append(card)

        for provider_name, fetcher, provider_score_bonus in (
            ("EUROPEANA", external_kb_service._search_europeana_direct, -0.04),
            ("ART_SEARCH_API", external_kb_service._search_artic_direct, 0.01),
            ("POETRYDB", external_kb_service._search_poetrydb_direct, 0.04),
        ):
            if provider_name not in active:
                continue
            for candidate in _safe_fetch_list(provider_name, fetcher, query, limit=2):
                wild_summary = _culture_summary_for_wild_card(candidate)
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Wild Card",
                    candidate=candidate,
                    anchors=culture_anchor_pool,
                    fallback_query=query,
                    summary_override=wild_summary,
                    extra_evidence=_culture_evidence(candidate, "Wild Card"),
                    score_bonus=provider_score_bonus,
                )
                if card:
                    family_cards["Wild Card"].append(card)

    return {family: _dedupe_and_limit(cards, limit=4) for family, cards in family_cards.items()}


def _select_board_layout(
    category_enum: DiscoveryCategory,
    family_cards: Dict[str, List[DiscoveryCard]],
) -> Tuple[Optional[DiscoveryCard], List[DiscoveryFamilySection]]:
    meta = _CATEGORY_META[category_enum]
    all_cards = [card for cards in family_cards.values() for card in cards]
    featured_card = max(all_cards, key=lambda card: card.score, default=None)
    featured_id = featured_card.id if featured_card else None
    family_sections: List[DiscoveryFamilySection] = []
    remaining_budget = 6

    for family_name in meta["hero_family_order"]:
        cards = [card for card in family_cards.get(family_name, []) if card.id != featured_id]
        if remaining_budget <= 0:
            cards = []
        else:
            cards = cards[: min(2, remaining_budget)]
            remaining_budget -= len(cards)
        family_meta = meta["families"][family_name]
        family_sections.append(
            DiscoveryFamilySection(
                family=family_name,
                title=family_name,
                description=str(family_meta["description"]),
                source_label=str(family_meta["source_label"]),
                cards=cards,
            )
        )

    return featured_card, family_sections
