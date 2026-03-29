from __future__ import annotations
import concurrent.futures

from typing import Any, Dict, List, Optional

from models.discovery_models import DiscoveryCard, DiscoveryCategory
from services import external_kb_service
from config import settings
from services.llm_client import (
    MODEL_TIER_FLASH,
    generate_text,
)
from utils.logger import get_logger

from .core import (
    _Anchor,
    _academic_anchor_pool,
    _academic_bridge_queries,
    _academic_fresh_signal_queries,
    _build_card_from_candidate,
    _finalize_family_card_map,
    _ordered_for_selection,
    _safe_fetch_list,
    _safe_fetch_value,
    _seed_queries,
)

_ACADEMIC_FAMILY_POOL_TARGET = 6
logger = get_logger("discovery_academic_provider")

def _enrich_academic_card_with_llm(
    card: DiscoveryCard, 
    anchors: List[_Anchor]
) -> DiscoveryCard:
    """
    Optional: Uses LLM to create a sophisticated 'Why this now?' link 
    between the academic paper and the user's specific notes.
    """
    if not settings.GEMINI_API_KEY:
        return card

    # Take the most relevant anchor
    primary_anchor = anchors[0] if anchors else None
    if not primary_anchor:
        return card

    anchor_context = f"Title: {primary_anchor.title}\nTags: {', '.join(primary_anchor.tags[:5])}"
    if primary_anchor.summary:
        anchor_context += f"\nSummary: {primary_anchor.summary[:300]}"

    prompt = f"""
    Analyze the link between this user's library item and this new academic paper.
    
    USER'S ITEM:
    {anchor_context}
    
    ACADEMIC PAPER:
    Title: {card.title}
    Summary: {card.summary[:500]}
    
    TASK:
    Briefly explain (max 20 words, in Turkish) why this paper matters to the user based on their specific item. 
    Be academic but insightful.
    
    Example: "Bu makale, kütüphanendeki İbn Rüşd notunda geçen akıl-vahiy gerilimini modern epistemolojiyle harmanlıyor."
    
    Return ONLY the Turkish explanation.
    """

    try:
        # Use a very short timeout for Discovery enrichment
        result = generate_text(
            model=settings.LLM_MODEL_FLASH,
            prompt=prompt,
            task="discovery_academic_enrichment",
            model_tier=MODEL_TIER_FLASH,
            temperature=0.3,
            timeout_s=4.0,
        )
        if result.text and len(result.text.strip()) > 5:
            card.why_seen = result.text.strip()
    except Exception as e:
        logger.warning("Academic LLM enrichment failed: %s", e)
    
    return card


def _build_academic_contextual_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    academic_anchors = _academic_anchor_pool(anchors, limit=10)
    fresh_queries = _academic_fresh_signal_queries(academic_anchors) or _seed_queries(DiscoveryCategory.ACADEMIC, anchors)
    bridge_queries = _academic_bridge_queries(academic_anchors)
    fresh_queries = _ordered_for_selection(fresh_queries, selection_token, "academic:fresh")
    bridge_queries = _ordered_for_selection(bridge_queries, selection_token, "academic:bridge")
    family_cards: Dict[str, List[DiscoveryCard]] = {"Fresh Signal": [], "Bridge": []}

    fresh_anchor_pool = academic_anchors[:4] or anchors[:4]
    bridge_anchor_pool = academic_anchors[:8] or anchors[:8]
    bridge_anchor_requirement = 2 if len(bridge_anchor_pool) >= 2 else 1
    bridge_signal_requirement = 2 if bridge_anchor_requirement == 1 else 0

    # 1. Process Fresh Signals (Parallelized)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_provider = {}
        for query in fresh_queries:
            if len(family_cards["Fresh Signal"]) >= _ACADEMIC_FAMILY_POOL_TARGET:
                break
            for provider_name, fetcher, score_bonus in (
                ("ARXIV", external_kb_service._search_arxiv_direct, 0.07),
                ("OPENALEX", external_kb_service._search_openalex_direct, 0.05),
                ("SEMANTIC_SCHOLAR", external_kb_service._search_semantic_scholar_direct, 0.04),
                ("CROSSREF", external_kb_service._search_crossref_direct, 0.03),
                ("SHARE", external_kb_service._search_share_direct, 0.02),
            ):
                if provider_name not in active:
                    continue
                future = executor.submit(_safe_fetch_list, provider_name, fetcher, query, limit=3)
                future_to_provider[future] = (provider_name, score_bonus, query)

        for future in concurrent.futures.as_completed(future_to_provider):
            provider_name, score_bonus, query = future_to_provider[future]
            try:
                candidates = future.result()
                for candidate in (candidates or []):
                    if len(family_cards["Fresh Signal"]) >= _ACADEMIC_FAMILY_POOL_TARGET:
                        break
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
                        # ENRICHMENT: Apply LLM intelligence to the top card of each query
                        if len(family_cards["Fresh Signal"]) < 2:
                            card = _enrich_academic_card_with_llm(card, fresh_anchor_pool)
                        family_cards["Fresh Signal"].append(card)
            except Exception as e:
                logger.warning("Parallel fetch failed for %s: %s", provider_name, e)

    # 2. Process Bridges (Connectors) (Parallelized)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_provider = {}
        for query in bridge_queries:
            if len(family_cards["Bridge"]) >= _ACADEMIC_FAMILY_POOL_TARGET:
                break
            for provider_name, fetcher, score_bonus in (
                ("OPENALEX", external_kb_service._search_openalex_direct, 0.06),
                ("CROSSREF", external_kb_service._search_crossref_direct, 0.04),
                ("SEMANTIC_SCHOLAR", external_kb_service._search_semantic_scholar_direct, 0.03),
                ("SHARE", external_kb_service._search_share_direct, 0.01),
            ):
                if provider_name not in active:
                    continue
                future = executor.submit(_safe_fetch_list, provider_name, fetcher, query, limit=3)
                future_to_provider[future] = (provider_name, score_bonus, query)

        for future in concurrent.futures.as_completed(future_to_provider):
            provider_name, score_bonus, query = future_to_provider[future]
            try:
                candidates = future.result()
                for candidate in (candidates or []):
                    if len(family_cards["Bridge"]) >= _ACADEMIC_FAMILY_POOL_TARGET:
                        break
                    card = _build_card_from_candidate(
                        category=DiscoveryCategory.ACADEMIC,
                        family="Bridge",
                        candidate=candidate,
                        anchors=bridge_anchor_pool,
                        fallback_query=query,
                        min_match_signals=bridge_signal_requirement,
                        require_date=True,
                        score_bonus=score_bonus,
                    )
                    if card:
                        family_cards["Bridge"].append(card)
            except Exception as e:
                logger.warning("Parallel bridge fetch failed for %s: %s", provider_name, e)

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

    return family_cards


def _build_academic_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    family_cards = _build_academic_contextual_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )
    return _finalize_family_card_map(
        DiscoveryCategory.ACADEMIC,
        family_cards,
        selection_token=selection_token,
    )

