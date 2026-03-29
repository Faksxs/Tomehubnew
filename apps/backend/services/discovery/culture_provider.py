from __future__ import annotations
import concurrent.futures

from typing import Any, Dict, List, Optional, Tuple

from models.discovery_models import (
    DiscoveryCard,
    DiscoveryCategory,
    DiscoveryFamilySection,
)
from services import external_kb_service

from .core import (
    _Anchor,
    _CATEGORY_META,
    _build_card_from_candidate,
    _culture_evidence,
    _culture_summary_for_artifact,
    _culture_summary_for_lineage,
    _culture_summary_for_wild_card,
    _empty_family_card_map,
    _finalize_family_card_map,
    _merge_family_card_maps,
    _ordered_for_selection,
    _pick_variant,
    _safe_fetch_list,
    _safe_fetch_value,
    _seed_queries,
    _select_domain_anchors,
)


from config import settings
from services.llm_client import MODEL_TIER_FLASH, generate_text
from utils.logger import get_logger

logger = get_logger("discovery_culture_provider")


def _enrich_culture_card_with_llm(
    card: DiscoveryCard, 
    anchors: List[_Anchor]
) -> DiscoveryCard:
    """
    Optional: Uses LLM to create an intriguing, fact-based link between the 
    cultural artifact/history and the user's library context.
    """
    if not settings.GEMINI_API_KEY:
        return card

    # Take the most relevant anchor
    primary_anchor = anchors[0] if anchors else None
    anchor_context = f"Title: {primary_anchor.title}\nTags: {', '.join(primary_anchor.tags[:5])}" if primary_anchor else "history and culture"
    
    prompt = f"""
    Explain the REAL historical or cultural link between this user's library item and this discovery.
    
    USER'S ITEM:
    {anchor_context}
    
    CULTURAL DISCOVERY:
    Title: {card.title}
    Summary: {card.summary[:500]}
    
    TASK:
    In max 20 words, in Turkish, provide a STRIKING FACT or ANALYTICAL LINK. 
    NO fiction. NO uydurma. Strictly based on real history/culture.
    Tone: Scholarly curious, like a documentary narrator.
    
    Example: "Bu eser, kütüphanendeki 'Rönesans' notunda geçen ışık kullanımının Venedik ekolündeki ilk somut örneklerinden biridir."
    
    Return ONLY the Turkish explanation.
    """

    try:
        result = generate_text(
            model=settings.LLM_MODEL_FLASH,
            prompt=prompt,
            task="discovery_culture_enrichment",
            model_tier=MODEL_TIER_FLASH,
            temperature=0.2, # Low temp for factual accuracy
            timeout_s=4.0,
        )
        if result.text and len(result.text.strip()) > 5:
            card.why_seen = result.text.strip()
    except Exception as e:
        logger.warning("Culture LLM enrichment failed: %s", e)
    
    return card


def _build_culture_contextual_cards(
    queries: List[str],
    culture_anchor_pool: List[_Anchor],
    active_provider_names: List[str],
) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    family_cards: Dict[str, List[DiscoveryCard]] = {
        "Lineage": [],
    }
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_provider = {}
        for query in queries:
            if "WIKIDATA" in active:
                future = executor.submit(_safe_fetch_value, "WIKIDATA", external_kb_service._fetch_wikidata, query, None)
                future_to_provider[future] = ("WIKIDATA", query)
            if "DBPEDIA" in active:
                future = executor.submit(_safe_fetch_value, "DBPEDIA", external_kb_service._fetch_dbpedia, query, None)
                future_to_provider[future] = ("DBPEDIA", query)

        for future in concurrent.futures.as_completed(future_to_provider):
            provider_name, query = future_to_provider[future]
            try:
                result = future.result()
                if not result:
                    continue
                
                if provider_name == "WIKIDATA":
                    lineage_summary = _culture_summary_for_lineage(result)
                    candidate = {
                        "title": str(result.get("label") or query).strip(),
                        "content_chunk": " | ".join(
                            part for part in [
                                str(result.get("description") or "").strip(),
                                "Type: relation graph",
                            ] if part
                        ),
                        "provider": "WIKIDATA",
                        "reference": str(result.get("qid") or "").strip() or None,
                        "source_url": (
                            f"https://www.wikidata.org/wiki/{result.get('qid')}"
                            if result.get("qid") else None
                        ),
                        "summary": lineage_summary,
                        "instance_of_labels": list(result.get("instance_of_labels") or []),
                        "subclass_of_labels": list(result.get("subclass_of_labels") or []),
                        "part_of_labels": list(result.get("part_of_labels") or []),
                        "country_labels": list(result.get("country_labels") or []),
                        "image_url": str(result.get("image_url") or "").strip() or None,
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
                else: # DBPEDIA
                    lineage_summary = _culture_summary_for_lineage(result)
                    candidate = {
                        "title": str(result.get("label") or query).strip(),
                        "content_chunk": " | ".join(
                            part for part in [
                                str(result.get("description") or "").strip(),
                                f"Type: {', '.join((result.get('types') or [])[:3])}" if result.get('types') else "",
                            ] if part
                        ),
                        "provider": "DBPEDIA",
                        "reference": str(result.get("resource_uri") or "").strip() or None,
                        "source_url": str(result.get("resource_uri") or "").strip() or None,
                        "summary": lineage_summary,
                        "types": list(result.get("types") or []),
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
                    # ENRICHMENT: Apply fact-based AI link
                    if len(family_cards["Lineage"]) < 2:
                        card = _enrich_culture_card_with_llm(card, culture_anchor_pool)
                    family_cards["Lineage"].append(card)
            except Exception as e:
                logger.warning("Parallel culture fetch failed for %s: %s", provider_name, e)
                
    return family_cards


def _build_culture_external_cards(
    queries: List[str],
    culture_anchor_pool: List[_Anchor],
    active_provider_names: List[str],
) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    family_cards: Dict[str, List[DiscoveryCard]] = {"Archive Artifact": [], "Wild Card": []}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_provider = {}
        for query in queries:
            # Artifacts
            for provider_name, fetcher, provider_score_bonus in (
                ("ART_SEARCH_API", external_kb_service._search_artic_direct, 0.09),
                ("EUROPEANA", external_kb_service._search_europeana_direct, -0.03),
                ("INTERNET_ARCHIVE", external_kb_service._search_internet_archive_direct, 0.0),
            ):
                if provider_name in active:
                    future = executor.submit(_safe_fetch_list, provider_name, fetcher, query, limit=3)
                    future_to_provider[future] = (provider_name, "Archive Artifact", query, provider_score_bonus)

            # Wild Cards
            for provider_name, fetcher, provider_score_bonus in (
                ("EUROPEANA", external_kb_service._search_europeana_direct, -0.04),
                ("ART_SEARCH_API", external_kb_service._search_artic_direct, 0.01),
                ("POETRYDB", external_kb_service._search_poetrydb_direct, 0.04),
            ):
                if provider_name in active:
                    future = executor.submit(_safe_fetch_list, provider_name, fetcher, query, limit=2)
                    future_to_provider[future] = (provider_name, "Wild Card", query, provider_score_bonus)

        for future in concurrent.futures.as_completed(future_to_provider):
            provider_name, family, query, score_bonus = future_to_provider[future]
            try:
                candidates = future.result()
                for candidate in (candidates or []):
                    if family == "Archive Artifact":
                        summary = _culture_summary_for_artifact(candidate)
                        card = _build_card_from_candidate(
                            category=DiscoveryCategory.CULTURE_HISTORY,
                            family="Archive Artifact",
                            candidate=candidate,
                            anchors=culture_anchor_pool,
                            fallback_query=query,
                            require_date_or_type=True,
                            require_reference=True,
                            summary_override=summary,
                            extra_evidence=_culture_evidence(candidate, "Archive Artifact"),
                            score_bonus=0.03 + score_bonus,
                        )
                    else:
                        summary = _culture_summary_for_wild_card(candidate)
                        card = _build_card_from_candidate(
                            category=DiscoveryCategory.CULTURE_HISTORY,
                            family="Wild Card",
                            candidate=candidate,
                            anchors=culture_anchor_pool,
                            fallback_query=query,
                            summary_override=summary,
                            extra_evidence=_culture_evidence(candidate, "Wild Card"),
                            score_bonus=score_bonus,
                        )
                    if card:
                        if len(family_cards[family]) < 2:
                            card = _enrich_culture_card_with_llm(card, culture_anchor_pool)
                        family_cards[family].append(card)
            except Exception as e:
                logger.warning("Parallel culture artifact fetch failed: %s", e)

    return family_cards


def _build_culture_history_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    queries = _seed_queries(DiscoveryCategory.CULTURE_HISTORY, anchors)
    queries = _ordered_for_selection(queries, selection_token, "culture:queries")
    culture_anchor_pool = _select_domain_anchors(DiscoveryCategory.CULTURE_HISTORY, anchors) or anchors
    family_cards = _merge_family_card_maps(
        DiscoveryCategory.CULTURE_HISTORY,
        _build_culture_contextual_cards(queries, culture_anchor_pool, active_provider_names),
        _build_culture_external_cards(queries, culture_anchor_pool, active_provider_names),
    )
    return _finalize_family_card_map(
        DiscoveryCategory.CULTURE_HISTORY,
        family_cards,
        selection_token=selection_token,
    )

