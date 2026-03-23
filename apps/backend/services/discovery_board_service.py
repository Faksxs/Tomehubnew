from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
_DATE_RE = re.compile(r"\b(19|20)\d{2}(?:-\d{2}-\d{2})?\b")
_YEAR_LABEL_RE = re.compile(r"\b(?:Year|Published|Date):\s*((?:19|20)\d{2}(?:-\d{2}-\d{2})?)", re.IGNORECASE)
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
    ) -> None:
        self.item_id = item_id
        self.item_type = item_type
        self.title = title
        self.author = author
        self.summary = summary
        self.tags = tags
        self.reading_status = reading_status
        self.source_url = source_url


_CATEGORY_META: Dict[DiscoveryCategory, Dict[str, Any]] = {
    DiscoveryCategory.ACADEMIC: {
        "title": "Academic",
        "description": "Fresh papers, bridge candidates, and structured research context from external academic sources.",
        "hero_family_order": ["Fresh Signal", "Bridge", "Deepen"],
        "families": {
            "Fresh Signal": {
                "description": "Recent papers and preprints that fit the current research direction.",
                "source_label": "ArXiv + OpenAlex",
            },
            "Bridge": {
                "description": "Works that connect directly to your active notes, themes, or highlights.",
                "source_label": "OpenAlex + Crossref + Semantic Scholar",
            },
            "Deepen": {
                "description": "Method, dataset, and research-structure views for going deeper.",
                "source_label": "ORKG + SHARE + Crossref",
            },
        },
    },
    DiscoveryCategory.RELIGIOUS: {
        "title": "Religious",
        "description": "Source-anchored Quran and hadith discovery cards with minimal interpretation and clear references.",
        "hero_family_order": ["Ayet Card", "Ayet + Hadis Bridge"],
        "families": {
            "Ayet Card": {
                "description": "A verse-first card with reference, translation, and a short grounded context.",
                "source_label": "Quran providers",
            },
            "Ayet + Hadis Bridge": {
                "description": "A verse and hadith pair carried by the same theme.",
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
        SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON, READING_STATUS, SOURCE_URL
        FROM (
            SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON, READING_STATUS, SOURCE_URL
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
    candidate_tokens = set(_tokens(candidate_text))
    best_anchor: Optional[_Anchor] = None
    best_score = -1
    best_evidence: List[DiscoveryEvidence] = []
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

        if score > best_score:
            best_score = score
            best_anchor = anchor
            best_evidence = evidence

    return best_anchor, best_evidence, max(0, best_score)


def _parse_year_or_date(value: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    labeled = _YEAR_LABEL_RE.search(text)
    if labeled:
        return str(labeled.group(1) or "").strip()
    raw = _DATE_RE.search(text)
    if raw:
        return str(raw.group(0) or "").strip()
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
    source_url = str(candidate.get("source_url") or "").strip()
    reference = str(candidate.get("reference") or candidate.get("canonical_reference") or "").strip()
    provider = str(candidate.get("provider") or "Source").strip()
    if source_url:
        refs.append(DiscoverySourceRef(label=f"{provider} source", url=source_url, kind="source"))
    if reference:
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
) -> Optional[DiscoveryCard]:
    provider = str(candidate.get("provider") or "").strip().upper()
    title = str(title_override or candidate.get("title") or "").strip()
    content = str(candidate.get("content_chunk") or "").strip()
    if not provider or not title:
        return None

    anchor = anchor_override
    evidence: List[DiscoveryEvidence] = list(extra_evidence or [])
    match_signals = 0
    if anchor_override:
        anchor_evidence = [
            DiscoveryEvidence(kind="anchor_override", label="Anchor context", value=anchor_override.title)
        ]
        evidence.extend(anchor_evidence)
        match_signals = len(anchor_evidence)
    else:
        matched_anchor, anchor_evidence, _anchor_score = _match_anchor(_candidate_text(candidate), anchors)
        anchor = matched_anchor
        evidence.extend(anchor_evidence)
        match_signals = len(anchor_evidence)

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

    summary = str(summary_override or "").strip() or _summary_from_content(content)
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
    anchor_bonus = min(0.16, 0.06 * match_signals)
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
        anchor_refs=(
            [DiscoveryAnchorRef(item_id=anchor.item_id, title=anchor.title, item_type=anchor.item_type)]
            if anchor else []
        ),
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
    queries = _seed_queries(DiscoveryCategory.ACADEMIC, anchors)
    family_cards: Dict[str, List[DiscoveryCard]] = {"Fresh Signal": [], "Bridge": [], "Deepen": []}

    for query in queries:
        if "ARXIV" in active:
            for candidate in external_kb_service._search_arxiv_direct(query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Fresh Signal",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    require_date=True,
                    score_bonus=0.05,
                )
                if card:
                    family_cards["Fresh Signal"].append(card)
        if "OPENALEX" in active:
            for candidate in external_kb_service._search_openalex_direct(query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Fresh Signal",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    require_date=True,
                    score_bonus=0.02,
                )
                if card:
                    family_cards["Fresh Signal"].append(card)

        for provider_name, fetcher in (
            ("OPENALEX", external_kb_service._search_openalex_direct),
            ("CROSSREF", external_kb_service._search_crossref_direct),
            ("SEMANTIC_SCHOLAR", external_kb_service._search_semantic_scholar_direct),
        ):
            if provider_name not in active:
                continue
            for candidate in fetcher(query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Bridge",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    min_match_signals=2,
                    require_reference=True,
                    score_bonus=0.05,
                )
                if card:
                    family_cards["Bridge"].append(card)

        if "ORKG" in active:
            orkg = external_kb_service._fetch_orkg(query, None)
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
                deep_candidate = {
                    "title": str(orkg.get("title") or query).strip(),
                    "content_chunk": " | ".join(content_parts),
                    "provider": "ORKG",
                    "source_url": str(orkg.get("url") or "").strip() or None,
                    "reference": str(orkg.get("doi") or "").strip() or None,
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Deepen",
                    candidate=deep_candidate,
                    anchors=anchors,
                    fallback_query=query,
                    score_bonus=0.08,
                )
                if card:
                    family_cards["Deepen"].append(card)
        for provider_name, fetcher in (
            ("SHARE", external_kb_service._search_share_direct),
            ("CROSSREF", external_kb_service._search_crossref_direct),
        ):
            if provider_name not in active:
                continue
            for candidate in fetcher(query, limit=2):
                content = str(candidate.get("content_chunk") or "")
                if not (_parse_type_label(content) or str(candidate.get("reference") or "").strip()):
                    continue
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.ACADEMIC,
                    family="Deepen",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    score_bonus=0.03,
                )
                if card:
                    family_cards["Deepen"].append(card)

    return {family: _dedupe_and_limit(cards, limit=4) for family, cards in family_cards.items()}


def _build_religious_cards(anchors: List[_Anchor], active_provider_names: List[str]) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    queries = _seed_queries(DiscoveryCategory.RELIGIOUS, anchors)
    family_cards: Dict[str, List[DiscoveryCard]] = {"Ayet Card": [], "Ayet + Hadis Bridge": []}

    for query in queries:
        candidates, _diag = islamic_api_service.get_islamic_external_candidates(query, limit=8, force_religious=True)
        filtered = [
            candidate for candidate in candidates
            if str(candidate.get("provider") or "").strip().upper() in active
        ]
        verse_candidates = [
            candidate for candidate in filtered
            if str(candidate.get("religious_source_kind") or "").strip().upper() == "QURAN"
        ]
        hadith_candidates = [
            candidate for candidate in filtered
            if str(candidate.get("religious_source_kind") or "").strip().upper() == "HADITH"
        ]

        for candidate in verse_candidates[:3]:
            card = _build_card_from_candidate(
                category=DiscoveryCategory.RELIGIOUS,
                family="Ayet Card",
                candidate=candidate,
                anchors=anchors,
                fallback_query=query,
                require_reference=True,
                score_bonus=0.08,
            )
            if card:
                family_cards["Ayet Card"].append(card)

        if verse_candidates and hadith_candidates:
            verse = verse_candidates[0]
            hadith = hadith_candidates[0]
            verse_ref = str(verse.get("canonical_reference") or verse.get("reference") or "").strip()
            hadith_ref = str(hadith.get("canonical_reference") or hadith.get("reference") or "").strip()
            if verse_ref and hadith_ref:
                bridge_candidate = {
                    "title": f"Theme bridge: {verse_ref} with {hadith_ref}",
                    "content_chunk": " | ".join(
                        part for part in [
                            str(verse.get("content_chunk") or "").strip(),
                            str(hadith.get("content_chunk") or "").strip(),
                        ] if part
                    ),
                    "provider": "QURANENC",
                    "source_url": str(verse.get("source_url") or hadith.get("source_url") or "").strip() or None,
                    "reference": verse_ref,
                }
                extra_refs = [
                    DiscoverySourceRef(label=verse_ref, url=str(verse.get("source_url") or "").strip() or None, kind="reference"),
                    DiscoverySourceRef(label=hadith_ref, url=str(hadith.get("source_url") or "").strip() or None, kind="reference"),
                ]
                extra_evidence = [
                    DiscoveryEvidence(kind="bridge", label="Verse", value=verse_ref),
                    DiscoveryEvidence(kind="bridge", label="Hadith", value=hadith_ref),
                ]
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.RELIGIOUS,
                    family="Ayet + Hadis Bridge",
                    candidate=bridge_candidate,
                    anchors=anchors,
                    fallback_query=query,
                    require_reference=True,
                    extra_refs=extra_refs,
                    extra_evidence=extra_evidence,
                    score_bonus=0.1,
                )
                if card:
                    family_cards["Ayet + Hadis Bridge"].append(card)

    return {family: _dedupe_and_limit(cards, limit=3) for family, cards in family_cards.items()}


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
            metadata_candidates = external_kb_service._search_literary_book_metadata_direct(
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
            for candidate in external_kb_service._search_gutendex_direct(query, limit=3):
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
            for row in search_tmdb_media(query, kind="multi", max_results=4):
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

    for query in queries:
        if "WIKIDATA" in active:
            wikidata = external_kb_service._fetch_wikidata(query, None)
            if wikidata:
                candidate = {
                    "title": str(wikidata.get("label") or query).strip(),
                    "content_chunk": " | ".join(
                        part for part in [
                            str(wikidata.get("description") or "").strip(),
                            f"Type: relation graph" if (wikidata.get("author_ids") or wikidata.get("genre_ids")) else "",
                        ] if part
                    ),
                    "provider": "WIKIDATA",
                    "reference": str(wikidata.get("qid") or "").strip() or None,
                    "source_url": (
                        f"https://www.wikidata.org/wiki/{wikidata.get('qid')}"
                        if wikidata.get("qid") else None
                    ),
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Lineage",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    score_bonus=0.05,
                )
                if card:
                    family_cards["Lineage"].append(card)
        if "DBPEDIA" in active:
            dbpedia = external_kb_service._fetch_dbpedia(query, None)
            if dbpedia:
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
                }
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Lineage",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
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
            for candidate in fetcher(query, limit=3):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Archive Artifact",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    require_date_or_type=True,
                    require_reference=True,
                    score_bonus=0.03,
                )
                if card:
                    family_cards["Archive Artifact"].append(card)

        for provider_name, fetcher in (
            ("EUROPEANA", external_kb_service._search_europeana_direct),
            ("ART_SEARCH_API", external_kb_service._search_artic_direct),
            ("POETRYDB", external_kb_service._search_poetrydb_direct),
        ):
            if provider_name not in active:
                continue
            for candidate in fetcher(query, limit=2):
                card = _build_card_from_candidate(
                    category=DiscoveryCategory.CULTURE_HISTORY,
                    family="Wild Card",
                    candidate=candidate,
                    anchors=anchors,
                    fallback_query=query,
                    score_bonus=-0.02,
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
