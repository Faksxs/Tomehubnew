"""
Backward-compatibility facade for discovery_board_service.

The implementation was split into services/discovery/* modules, but callers and
tests still import and monkeypatch symbols from this legacy path. This module
keeps those old patch points working by synchronizing facade-level overrides
back into the underlying modules before delegation.
"""
from __future__ import annotations

from services import islamic_api_service
from services.discovery import academic_provider as _academic_provider
from services.discovery import core as _core
from services.discovery import culture_provider as _culture_provider
from services.discovery import literary_provider as _literary_provider
from services.discovery import religious_provider as _religious_provider
import random

# Re-export core internals used by callers/tests.
_Anchor = _core._Anchor
_CATEGORY_META = _core._CATEGORY_META
_academic_anchor_pool = _core._academic_anchor_pool
_academic_bridge_queries = _core._academic_bridge_queries
_academic_fresh_signal_queries = _core._academic_fresh_signal_queries
_build_card_from_candidate = _core._build_card_from_candidate
_build_family_cards = _core._build_family_cards
_build_why_seen = _core._build_why_seen
_card_id = _core._card_id
_collect_anchor_matches = _core._collect_anchor_matches
_confidence_label = _core._confidence_label
_dedupe_and_limit = _core._dedupe_and_limit
_dedupe_text_values = _core._dedupe_text_values
_empty_family_card_map = _core._empty_family_card_map
_fallback_source_url = _core._fallback_source_url
_finalize_family_card_map = _core._finalize_family_card_map
_join_fragments = _core._join_fragments
_load_user_anchors = _core._load_user_anchors
_load_user_provider_preferences = _core._load_user_provider_preferences
_match_anchor = _core._match_anchor
_merge_family_card_maps = _core._merge_family_card_maps
_ordered_for_selection = _core._ordered_for_selection
_parse_tags = _core._parse_tags
_parse_type_label = _core._parse_type_label
_parse_year_or_date = _core._parse_year_or_date
_pick_variant = _core._pick_variant
_resolve_active_provider_names = _core._resolve_active_provider_names
_safe_fetch_list = _core._safe_fetch_list
_safe_fetch_value = _core._safe_fetch_value
_safe_islamic_candidates = _core._safe_islamic_candidates
_safe_search_tmdb = _core._safe_search_tmdb
_seed_queries = _core._seed_queries
_select_board_layout = _core._select_board_layout
_select_domain_anchors = _core._select_domain_anchors
_selection_offset = _core._selection_offset
_source_refs_from_candidate = _core._source_refs_from_candidate
_summary_from_content = _core._summary_from_content
_tokens = _core._tokens
_top_tags = _core._top_tags


def _sync_compat_exports() -> None:
    # Core patch points
    _core._build_family_cards = _build_family_cards
    _core._load_user_anchors = _load_user_anchors
    _core._load_user_provider_preferences = _load_user_provider_preferences
    _core._resolve_active_provider_names = _resolve_active_provider_names
    _core._safe_islamic_candidates = _safe_islamic_candidates
    _core._seed_queries = _seed_queries

    # Provider modules that import helpers directly from core need refreshed refs.
    _academic_provider._seed_queries = _seed_queries
    _religious_provider._safe_islamic_candidates = _safe_islamic_candidates
    _culture_provider._seed_queries = _seed_queries


def get_discovery_board(category: str, firebase_uid: str, *, selection_token: str | None = None):
    _sync_compat_exports()
    return _core.get_discovery_board(category, firebase_uid, selection_token=selection_token)


def _build_academic_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _academic_provider._build_academic_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_academic_contextual_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _academic_provider._build_academic_contextual_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_religious_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _religious_provider._build_religious_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_religious_curated_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _religious_provider._build_religious_curated_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_verse_card(*, verse_key, theme, anchor, active_provider_names):
    _sync_compat_exports()
    return _religious_provider._build_verse_card(
        verse_key=verse_key,
        theme=theme,
        anchor=anchor,
        active_provider_names=active_provider_names,
    )


def _build_literary_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _literary_provider._build_literary_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_literary_mixed_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _literary_provider._build_literary_mixed_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_culture_history_cards(anchors, active_provider_names, *, selection_token=None):
    _sync_compat_exports()
    return _culture_provider._build_culture_history_cards(
        anchors,
        active_provider_names,
        selection_token=selection_token,
    )


def _build_culture_contextual_cards(queries, culture_anchor_pool, active_provider_names):
    _sync_compat_exports()
    return _culture_provider._build_culture_contextual_cards(
        queries,
        culture_anchor_pool,
        active_provider_names,
    )


def _build_culture_external_cards(queries, culture_anchor_pool, active_provider_names):
    _sync_compat_exports()
    return _culture_provider._build_culture_external_cards(
        queries,
        culture_anchor_pool,
        active_provider_names,
    )
