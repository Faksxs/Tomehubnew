from __future__ import annotations

import random
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from models.discovery_models import (
    DiscoveryAnchorRef,
    DiscoveryCard,
    DiscoveryCategory,
    DiscoveryEvidence,
    DiscoverySourceRef,
)
from services.llm_client import (
    MODEL_TIER_FLASH,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    generate_text,
)
from services import islamic_api_service
from config import settings
from utils.logger import get_logger

from .core import (
    _Anchor,
    _STOPWORDS,
    _actions_for_card,
    _card_id,
    _collect_anchor_matches,
    _confidence_label,
    _fallback_source_url,
    _finalize_family_card_map,
    _ordered_for_selection,
    _pick_variant,
    _safe_fetch_value,
    _safe_islamic_candidates,
    _selection_offset,
)

logger = get_logger("discovery_religious_provider")
_TURKISH_HINT_RE = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_ENGLISH_HINT_RE = re.compile(r"\b(the|and|with|from|into|about|verse|tafsir|commentary|translation|chapter)\b", re.IGNORECASE)
_RELIGIOUS_VERSE_VARIANT_TARGET = 4


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



def _curated_random_verse_key(selection_token: Optional[str] = None, *, salt: str = "verse") -> str:
    candidates = [
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
    ]
    if selection_token:
        return candidates[_selection_offset(selection_token, salt, len(candidates))]
    return random.choice(candidates)



def _pick_anchor_for_theme(theme: str, anchors: List[_Anchor]) -> Optional[_Anchor]:
    matches = _collect_anchor_matches(theme, anchors, limit=1)
    if matches:
        return matches[0][0]
    return anchors[0] if anchors else None



def _pick_religious_verse_candidate(
    theme: str,
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    active = set(active_provider_names)
    seen = set()
    for query in [f"{theme} ayet", f"{theme} kuran", theme]:
        query_candidates: List[Dict[str, Any]] = []
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
            query_candidates.append(candidate)
            if len(query_candidates) >= _RELIGIOUS_VERSE_VARIANT_TARGET:
                break
        if query_candidates:
            top_candidates = query_candidates[: min(_RELIGIOUS_VERSE_VARIANT_TARGET, len(query_candidates))]
            return _pick_variant(top_candidates, selection_token, f"verse:{theme}")

    reference = _curated_random_verse_key(selection_token, salt=f"curated:{theme}")
    fallback_candidates: List[Dict[str, Any]] = []
    quranenc_exact = islamic_api_service._normalize_quranenc_exact(islamic_api_service._quranenc_fetch_verse(reference) or {})
    if quranenc_exact:
        fallback_candidates.append(quranenc_exact)
    quran_foundation_exact = islamic_api_service._normalize_quran_foundation_exact(islamic_api_service._quran_foundation_fetch_verse(reference) or {})
    if quran_foundation_exact:
        fallback_candidates.append(quran_foundation_exact)
    
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
    return ""



def _extract_quran_arabic(
    quranenc_verse: Optional[Dict[str, Any]],
    quran_foundation_verse: Optional[Dict[str, Any]],
) -> str:
    for candidate in [
        str((quran_foundation_verse or {}).get("text_uthmani") or "").strip(),
        str((quranenc_verse or {}).get("arabic_text") or "").strip(),
    ]:
        if candidate:
            return candidate
    return ""



def _extract_quran_transliteration(quran_foundation_verse: Optional[Dict[str, Any]]) -> str:
    words = (quran_foundation_verse or {}).get("words") or []
    if not isinstance(words, list):
        return ""
    parts: List[str] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        # Check standard transliteration field
        trans = word.get("transliteration") or {}
        text = ""
        if isinstance(trans, dict):
            text = str(trans.get("text") or "").strip()
        else:
            text = str(trans or "").strip()
        
        # Fallback to other possible fields if empty
        if not text:
            text = str(word.get("text_imlaei") or "").strip()
            
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



def _extract_tafsir_text(candidate: Optional[Dict[str, Any]]) -> str:
    if not isinstance(candidate, dict):
        return ""
    
    # Prioritize content_chunk if it has actual text
    raw_content = str(candidate.get("content_chunk") or "").strip()
    
    # Filter out common metadata-only chunks (e.g. just PDF info)
    lines = [l.strip() for l in raw_content.splitlines() if l.strip()]
    filtered_lines = [
        l for l in lines 
        if not any(x in l.lower() for x in ["pdf |", "kb hazirlayan:", "kategori:", "tur:"])
    ]
    
    body_text = "\n".join(filtered_lines).strip()
    
    # If we have a decent body, use it. Otherwise fallback to title but check it too.
    if len(body_text) > 50:
        return body_text
        
    title = str(candidate.get("title") or "").strip()
    # If title is all we have and it looks like a document link, try to at least return it
    # but prefer body if available at all.
    return body_text if body_text else title


def _needs_turkish_translation(text: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) < 24:
        return False
    lowered = cleaned.casefold()
    if _TURKISH_HINT_RE.search(cleaned):
        return False
    if any(token in lowered for token in (" bir ", " ve ", " için ", " olarak ", " olan ", " bu ", " daha ")):
        return False
    if _ENGLISH_HINT_RE.search(cleaned):
        return True
    if cleaned.isascii() and len(cleaned.split()) >= 6:
        return True
    return False


def _translate_religious_text_llm(text: str, context: str = "Tafsir") -> str:
    """
    Translates religious text (Verse/Tafsir) to Turkish faithfully.
    Preserves Arabic script and special terminology.
    """
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned or not any(c.isalpha() for c in cleaned):
        return cleaned
    if _contains_arabic_text(cleaned):
        return cleaned
    if not _needs_turkish_translation(cleaned):
        return cleaned

    prompt = f"""
    Translate the following {context} into Turkish faithfully ("birebir").
    
    CRITICAL RULES:
    1. Preserve all Arabic script (Quranic verses in Arabic) EXACTLY as they are.
    2. Maintain religious terminology and specific names.
    3. The tone must be formal and scholarly, appropriate for a Tafsir.
    4. Do not summarize or simplify; provide a complete and faithful translation.
    
    TEXT TO TRANSLATE:
    {cleaned}
    
    Return ONLY the Turkish translation. No explanations.
    """
    
    try:
        result = generate_text(
            model=settings.LLM_MODEL_FLASH,
            prompt=prompt,
            task="discovery_religious_translation",
            model_tier=MODEL_TIER_FLASH,
            temperature=0.1,
            timeout_s=12.0,
        )
        translated = result.text.strip()
        return translated if translated else cleaned
    except Exception as e:
        logger.warning("Religious translation failed: %s", e)
        return cleaned


def _pick_tafsir_candidate(theme: str, verse_key: str, active_provider_names: List[str]) -> Optional[Dict[str, Any]]:
    active = set(active_provider_names)
    seen = set()
    for query in _verse_tafsir_queries(theme, verse_key):
        query_candidates: List[Dict[str, Any]] = []
        for candidate in _safe_islamic_candidates(query, limit=8):
            provider = str(candidate.get("provider") or "").strip().upper()
            kind = str(candidate.get("religious_source_kind") or "").strip().upper()
            reference = str(candidate.get("canonical_reference") or candidate.get("reference") or "").strip()
            key = (provider, kind, reference)
            if provider not in active or key in seen or kind != "INTERPRETATION":
                continue
            seen.add(key)
            query_candidates.append(candidate)
        if query_candidates:
            query_candidates.sort(
                key=lambda item: (
                    len(_extract_tafsir_text(item)),
                    float(item.get("score") or 0.0),
                ),
                reverse=True,
            )
            return query_candidates[0]
    return None


def _resolve_verse_tafsir_candidate(
    theme: str,
    verse_key: str,
    active_provider_names: List[str],
) -> Optional[Dict[str, Any]]:
    active = {str(provider).strip().upper() for provider in active_provider_names}

    if "QURAN_FOUNDATION" in active:
        exact_tafsir = _safe_fetch_value(
            "QURAN_FOUNDATION_TAFSIR_EXACT",
            islamic_api_service._quran_foundation_fetch_tafsir,
            verse_key,
        )
        if isinstance(exact_tafsir, dict):
            exact_text = _extract_tafsir_text(exact_tafsir)
            if exact_text:
                return exact_tafsir

    return _pick_tafsir_candidate(theme, verse_key, active_provider_names)


def _enrich_religious_card_with_llm(
    card: DiscoveryCard, 
    anchor: Optional[_Anchor],
    theme: str
) -> DiscoveryCard:
    """
    Optional: Uses LLM to bridge the Quranic verse/tafsir with the user's specific 
    philosophical ideas or tags.
    """
    if not settings.GEMINI_API_KEY or not anchor:
        return card

    anchor_context = f"Title: {anchor.title}\nTags: {', '.join(anchor.tags[:5])}"
    if anchor.summary:
        anchor_context += f"\nSummary: {anchor.summary[:300]}"

    prompt = f"""
    Analyze the intellectual link between this user's library item and this Quranic verse/tafsir.
    
    USER'S ITEM:
    {anchor_context}
    
    RELIGIOUS CONTEXT ({card.freshness_label}):
    {card.summary[:600]}
    
    TASK:
    Briefly explain (max 20 words, in Turkish) why this verse matters to the user based on their specific item.
    Be respectful, academic and profound.
    
    Example: "Bu ayet, kütüphanendeki 'adalet' notunu ilahi bir perspektifle derinleştirerek mülk-hak ilişkisine vurgu yapıyor."
    
    Return ONLY the Turkish explanation.
    """

    try:
        result = generate_text(
            model=settings.LLM_MODEL_FLASH,
            prompt=prompt,
            task="discovery_religious_enrichment",
            model_tier=MODEL_TIER_FLASH,
            temperature=0.2,
            timeout_s=4.0,
        )
        if result.text and len(result.text.strip()) > 5:
            card.why_seen = result.text.strip()
    except Exception as e:
        logger.warning("Religious LLM enrichment failed: %s", e)
    
    return card


def _build_verse_card(
    *,
    verse_key: str,
    theme: str,
    anchor: Optional[_Anchor],
    active_provider_names: List[str],
) -> Optional[DiscoveryCard]:
    if ":" not in verse_key:
        return None

    quranenc_verse = _safe_fetch_value("QURANENC_EXACT", islamic_api_service._quranenc_fetch_verse, verse_key) or {}
    quran_foundation_verse = _safe_fetch_value("QURAN_FOUNDATION_EXACT", islamic_api_service._quran_foundation_fetch_verse, verse_key) or {}
    
    arabic = _extract_quran_arabic(quranenc_verse, quran_foundation_verse)
    transliteration = _extract_quran_transliteration(quran_foundation_verse)
    meal = _extract_quran_meal(quranenc_verse, quran_foundation_verse)
    if not arabic or not meal:
        return None

    tafsir = _resolve_verse_tafsir_candidate(theme, verse_key, active_provider_names)
    tafsir_text = _extract_tafsir_text(tafsir)
    tafsir_text = _translate_religious_text_llm(tafsir_text, context=f"Tafsir for {verse_key}")
    if not tafsir_text:
        return None

    source_refs = _religious_verse_refs(verse_key)
    tafsir_url = str((tafsir or {}).get("source_url") or _fallback_source_url(tafsir or {}) or "").strip()
    if tafsir_url:
        source_refs.append(DiscoverySourceRef(label="Tefsir", url=tafsir_url, kind="source"))

    summary = "" # 'sil' - Remove redundant summary as requested
    why_seen = f"'{theme}' izine göre seçilen bu ayet kartı, mealin yanına doğrudan tefsir kanıtını da ekler."
    score = 0.86 if str((tafsir or {}).get("provider") or "").strip().upper() == "QURAN_FOUNDATION" else 0.82
    evidence = [
        DiscoveryEvidence(kind="arabic", label="Arabic", value=arabic),
    ]
    if transliteration and transliteration != "Okunuş verisi alınmadı.":
        evidence.append(DiscoveryEvidence(kind="transliteration", label="Okunuş", value=transliteration))
        
    evidence.extend([
        DiscoveryEvidence(kind="translation", label="Meal", value=meal),
        DiscoveryEvidence(kind="tafsir", label="Tefsir", value=tafsir_text),
    ])
    anchor_refs = [DiscoveryAnchorRef(item_id=anchor.item_id, title=anchor.title, item_type=anchor.item_type)] if anchor else []
    title = f"Ayet {verse_key}"
    
    card = DiscoveryCard(
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
            summary="",
            why_seen=why_seen,
            source_refs=source_refs,
            anchor=anchor,
        ),
        score=score,
    )

    # ENRICHMENT: Add AI-powered reasoning bridge
    return _enrich_religious_card_with_llm(card, anchor, theme)


def _build_random_verse_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    limit: int = 3,
    selection_token: Optional[str] = None,
) -> List[DiscoveryCard]:
    theme_candidates = _ordered_for_selection(
        _religious_theme_candidates(anchors),
        selection_token,
        "religious:themes:verse",
    )
    if not selection_token:
        random.shuffle(theme_candidates)
    cards: List[DiscoveryCard] = []
    seen_verse_keys = set()
    for theme, suggested_anchor in theme_candidates:
        verse_candidate = _pick_religious_verse_candidate(
            theme,
            active_provider_names,
            selection_token=selection_token,
        )
        if not verse_candidate:
            continue
        verse_key = str(verse_candidate.get("canonical_reference") or verse_candidate.get("reference") or "").strip()
        if ":" not in verse_key or verse_key in seen_verse_keys:
            continue
        anchor = suggested_anchor or _pick_anchor_for_theme(theme, anchors)
        card = _build_verse_card(
            verse_key=verse_key,
            theme=theme,
            anchor=anchor,
            active_provider_names=active_provider_names,
        )
        if not card:
            continue
        seen_verse_keys.add(verse_key)
        cards.append(card)
        if len(cards) >= limit:
            break
    return cards


def _verse_tafsir_queries(theme: str, verse_key: str) -> List[str]:
    return [
        f"{verse_key} tefsir",
        f"{theme} tefsir",
        f"{theme} ayet tefsir",
    ]
def _build_curated_fallback_verse_card(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    verse_key: Optional[str] = None,
    selection_token: Optional[str] = None,
) -> Optional[DiscoveryCard]:
    """Fallback: pick a curated well-known verse directly when live API queries fail."""
    verse_key = verse_key or _curated_random_verse_key(selection_token, salt="fallback")
    anchor = anchors[0] if anchors else None
    card = _build_verse_card(
        verse_key=verse_key,
        theme="curated",
        anchor=anchor,
        active_provider_names=active_provider_names,
    )
    if card:
        card.why_seen = "A curated verse card surfaced as a fallback, but only after Arabic, transliteration, meal, and tafsir all resolved together."
        card.summary = _compact_text(
            next((item.value for item in card.evidence if item.label == "Tefsir" and item.value), card.summary),
            limit=2000,
        )
        card.score = max(card.score, 0.79)
        card.confidence_label = _confidence_label(card.score)
    return card



def _build_religious_curated_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    family_cards: Dict[str, List[DiscoveryCard]] = {"Ayet Card": []}

    verse_cards = _build_random_verse_cards(
        anchors,
        active_provider_names,
        limit=1,
        selection_token=selection_token,
    )
    if verse_cards:
        family_cards["Ayet Card"].extend(verse_cards)
        return family_cards

    curated_keys = _ordered_for_selection(
        [
            "24:35",
            "17:12",
            "2:255",
            "36:58",
            "39:53",
        ],
        selection_token,
        "religious:curated:fallback",
    )
    for verse_key in curated_keys:
        fallback_card = _build_curated_fallback_verse_card(
            anchors,
            active_provider_names,
            verse_key=verse_key,
            selection_token=selection_token,
        )
        if fallback_card:
            family_cards["Ayet Card"].append(fallback_card)
        if len(family_cards["Ayet Card"]) >= 3:
            break

    return family_cards


def _build_religious_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    family_cards = _build_religious_curated_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )
    return _finalize_family_card_map(
        DiscoveryCategory.RELIGIOUS,
        family_cards,
        selection_token=selection_token,
    )

