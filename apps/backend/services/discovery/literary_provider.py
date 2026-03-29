from __future__ import annotations
import concurrent.futures

from typing import Any, Dict, List, Optional

from models.discovery_models import DiscoveryCard, DiscoveryCategory
from services import external_kb_service

from .core import (
    _Anchor,
    _build_card_from_candidate,
    _finalize_family_card_map,
    _ordered_for_selection,
    _safe_fetch_list,
    _safe_search_tmdb,
    _seed_queries,
)


from config import settings
from services.llm_client import MODEL_TIER_FLASH, generate_text
from utils.logger import get_logger

logger = get_logger("discovery_literary_provider")


def _enrich_literary_card_with_llm(
    card: DiscoveryCard, 
    anchors: List[_Anchor]
) -> DiscoveryCard:
    """
    Optional: Uses LLM to create a fun, storytelling link between the 
    literary/film suggestion and the user's library.
    """
    if not settings.GEMINI_API_KEY:
        return card

    # Take the most relevant anchor
    primary_anchor = anchors[0] if anchors else None
    anchor_context = f"Title: {primary_anchor.title}" if primary_anchor else "recent favorites"
    
    prompt = f"""
    Create a fun and engaging 'Discovery Hook' for this book/film suggestion.
    
    USER'S RECENT ITEM:
    {anchor_context}
    
    SUGGESTED ITEM:
    Title: {card.title}
    Summary: {card.summary[:400]}
    
    TASK:
    Briefly explain (max 20 words, in Turkish) why this is a fun next step. 
    Tone: Enthusiastic, intriguing, like a smart friend sharing a secret gem.
    
    Example: "Bu eserin atmosferi, kütüphanendeki '{anchor_context}' içindeki o gizemli havayı harika bir şekilde tamamlıyor!"
    
    Return ONLY the Turkish hook.
    """

    try:
        result = generate_text(
            model=settings.LLM_MODEL_FLASH,
            prompt=prompt,
            task="discovery_literary_enrichment",
            model_tier=MODEL_TIER_FLASH,
            temperature=0.7, 
            timeout_s=4.0,
        )
        if result.text and len(result.text.strip()) > 5:
            card.why_seen = result.text.strip()
    except Exception as e:
        logger.warning("Literary LLM enrichment failed: %s", e)
    
    return card


def _build_literary_mixed_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    active = set(active_provider_names)
    queries = _seed_queries(DiscoveryCategory.LITERARY, anchors)
    queries = _ordered_for_selection(queries, selection_token, "literary:queries")
    family_cards: Dict[str, List[DiscoveryCard]] = {
        "Same Author / Next Book": [],
        "Parallel Work": [],
        "Notes to Screen": [],
    }

    metadata_providers = [provider for provider in active_provider_names if provider in {"GOOGLE_BOOKS", "OPEN_LIBRARY", "BIG_BOOK_API"}]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_info = {}
        for query in queries:
            if metadata_providers:
                future = executor.submit(
                    _safe_fetch_list,
                    "LITERARY_METADATA",
                    external_kb_service._search_literary_book_metadata_direct,
                    query,
                    limit=4,
                    active_providers=metadata_providers,
                )
                future_to_info[future] = ("METADATA", query)
            
            if "GUTENDEX" in active:
                future = executor.submit(_safe_fetch_list, "GUTENDEX", external_kb_service._search_gutendex_direct, query, limit=3)
                future_to_info[future] = ("GUTENDEX", query)
                
            if "TMDB" in active:
                future = executor.submit(_safe_search_tmdb, query, max_results=4)
                future_to_info[future] = ("TMDB", query)

        for future in concurrent.futures.as_completed(future_to_info):
            kind, query = future_to_info[future]
            try:
                results = future.result()
                if not results:
                    continue
                    
                if kind == "METADATA":
                    for candidate in results:
                        # Same Author / Next Book
                        card = _build_card_from_candidate(
                            category=DiscoveryCategory.LITERARY,
                            family="Same Author / Next Book",
                            candidate=candidate,
                            anchors=anchors,
                            fallback_query=query,
                            score_bonus=0.03,
                        )
                        if card:
                            if len(family_cards["Same Author / Next Book"]) < 2:
                                card = _enrich_literary_card_with_llm(card, anchors)
                            family_cards["Same Author / Next Book"].append(card)
                        
                        # Parallel Work
                        card_parallel = _build_card_from_candidate(
                            category=DiscoveryCategory.LITERARY,
                            family="Parallel Work",
                            candidate=candidate,
                            anchors=anchors,
                            fallback_query=query,
                            min_match_signals=1,
                            score_bonus=0.01,
                        )
                        if card_parallel:
                            if len(family_cards["Parallel Work"]) < 2:
                                card_parallel = _enrich_literary_card_with_llm(card_parallel, anchors)
                            family_cards["Parallel Work"].append(card_parallel)
                
                elif kind == "GUTENDEX":
                    for candidate in results:
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
                            if len(family_cards["Parallel Work"]) < 2:
                                card = _enrich_literary_card_with_llm(card, anchors)
                            family_cards["Parallel Work"].append(card)
                            
                elif kind == "TMDB":
                    for row in results:
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
                            if len(family_cards["Notes to Screen"]) < 2:
                                card = _enrich_literary_card_with_llm(card, anchors)
                            family_cards["Notes to Screen"].append(card)
            except Exception as e:
                logger.warning("Parallel literary fetch failed for %s: %s", kind, e)

    return family_cards


def _build_literary_cards(
    anchors: List[_Anchor],
    active_provider_names: List[str],
    *,
    selection_token: Optional[str] = None,
) -> Dict[str, List[DiscoveryCard]]:
    family_cards = _build_literary_mixed_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )
    return _finalize_family_card_map(
        DiscoveryCategory.LITERARY,
        family_cards,
        selection_token=selection_token,
    )

