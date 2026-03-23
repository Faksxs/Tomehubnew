from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from models.discovery_models import (
    DiscoveryInnerSpaceCard,
    DiscoveryInnerSpaceMetadata,
    DiscoveryInnerSpaceResponse,
    DiscoveryInnerSpaceSlot,
)
from services.library_service import _content_table_shape, resolve_active_content_table
from services.memory_profile_service import get_memory_profile
from utils.logger import get_logger

logger = get_logger("discovery_inner_space_service")

_LIBRARY_TABLE = "TOMEHUB_LIBRARY_ITEMS"
_STOP_TAGS = {
    "book", "books", "article", "articles", "note", "notes", "movie", "movies", "series",
    "personal", "archive", "reading", "finished", "to read", "digital", "private",
    "daily", "ideas", "bookmark",
}


@dataclass
class _InnerSpaceItem:
    item_id: str
    item_type: str
    title: str
    author: str
    summary: str
    tags: List[str]
    reading_status: str
    source_url: str
    updated_at: Optional[datetime]
    created_at: Optional[datetime]
    page_count: Optional[int]
    personal_note_category: Optional[str]
    total_signals: int = 0
    highlight_count: int = 0
    insight_count: int = 0
    note_count: int = 0
    last_signal_at: Optional[datetime] = None
    max_page_number: Optional[int] = None

    @property
    def last_activity_at(self) -> Optional[datetime]:
        candidates = [value for value in (self.updated_at, self.last_signal_at, self.created_at) if value is not None]
        if not candidates:
            return None
        return max(candidates)


def get_discovery_inner_space(firebase_uid: str) -> DiscoveryInnerSpaceResponse:
    items = _load_inner_space_items(firebase_uid)
    profile = get_memory_profile(firebase_uid) or {}
    active_themes = _resolve_active_themes(items, profile)

    continue_item = _pick_continue_item(items)
    latest_item = _pick_latest_sync_item(items, exclude_ids={continue_item.item_id} if continue_item else set())
    dormant_item = _pick_dormant_gem_item(
        items,
        active_themes,
        exclude_ids={item_id for item_id in (continue_item.item_id if continue_item else None, latest_item.item_id if latest_item else None) if item_id},
    )

    cards = [
        _build_continue_card(continue_item),
        _build_latest_sync_card(latest_item),
        _build_dormant_gem_card(dormant_item, active_themes),
        _build_theme_pulse_card(active_themes, profile, items),
    ]

    return DiscoveryInnerSpaceResponse(
        cards=cards,
        metadata=DiscoveryInnerSpaceMetadata(
            last_updated_at=datetime.now(timezone.utc).isoformat(),
            active_theme_count=len(active_themes),
            has_memory_profile=bool(profile),
            total_items_considered=len(items),
        ),
    )


def _load_inner_space_items(firebase_uid: str, limit: int = 120) -> List[_InnerSpaceItem]:
    lib_cols = _table_columns(_LIBRARY_TABLE)
    if not lib_cols:
        return []

    def _select(col: str, alias: Optional[str] = None) -> str:
        resolved_alias = alias or col
        if col in lib_cols:
            return f"{col} AS {resolved_alias}"
        return f"NULL AS {resolved_alias}"

    filters = ["FIREBASE_UID = :p_uid"]
    if "IS_DELETED" in lib_cols:
        filters.append("NVL(IS_DELETED, 0) = 0")
    if "SEARCH_VISIBILITY" in lib_cols:
        filters.append("NVL(SEARCH_VISIBILITY, 'VISIBLE') <> 'EXCLUDED_BY_DEFAULT'")

    order_expr = "NVL(UPDATED_AT, CREATED_AT) DESC NULLS LAST"
    if "UPDATED_AT" not in lib_cols and "CREATED_AT" not in lib_cols:
        order_expr = "ITEM_ID DESC"
    elif "UPDATED_AT" not in lib_cols:
        order_expr = "CREATED_AT DESC NULLS LAST"
    elif "CREATED_AT" not in lib_cols:
        order_expr = "UPDATED_AT DESC NULLS LAST"

    sql = f"""
        SELECT ITEM_ID, ITEM_TYPE, TITLE, AUTHOR, SUMMARY_TEXT, TAGS_JSON, READING_STATUS,
               SOURCE_URL, UPDATED_AT, CREATED_AT, PAGE_COUNT, PERSONAL_NOTE_CATEGORY
        FROM (
            SELECT
                {_select("ITEM_ID")},
                {_select("ITEM_TYPE")},
                {_select("TITLE")},
                {_select("AUTHOR")},
                {_select("SUMMARY_TEXT")},
                {_select("TAGS_JSON")},
                {_select("READING_STATUS")},
                {_select("SOURCE_URL")},
                {_select("UPDATED_AT")},
                {_select("CREATED_AT")},
                {_select("PAGE_COUNT")},
                {_select("PERSONAL_NOTE_CATEGORY")}
            FROM {_LIBRARY_TABLE}
            WHERE {' AND '.join(filters)}
            ORDER BY {order_expr}
        )
        WHERE ROWNUM <= :p_limit
    """

    items: List[_InnerSpaceItem] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"p_uid": firebase_uid, "p_limit": max(1, min(int(limit), 200))})
                for row in cur.fetchall() or []:
                    item_id = str(row[0] or "").strip()
                    title = str(row[2] or "").strip()
                    if not item_id or not title:
                        continue
                    items.append(
                        _InnerSpaceItem(
                            item_id=item_id,
                            item_type=str(row[1] or "").strip().upper() or "BOOK",
                            title=title,
                            author=str(row[3] or "").strip(),
                            summary=(safe_read_clob(row[4]) or "").strip(),
                            tags=_parse_tags(row[5]),
                            reading_status=str(row[6] or "").strip(),
                            source_url=str(row[7] or "").strip(),
                            updated_at=_to_datetime(row[8]),
                            created_at=_to_datetime(row[9]),
                            page_count=_to_int(row[10]),
                            personal_note_category=str(row[11] or "").strip() or None,
                        )
                    )
    except Exception as exc:
        logger.warning("Failed to load inner space items for uid=%s: %s", firebase_uid, exc)
        return []

    _hydrate_content_stats(firebase_uid, items)
    return items


def _hydrate_content_stats(firebase_uid: str, items: List[_InnerSpaceItem]) -> None:
    table_name = resolve_active_content_table()
    if not table_name or not items:
        return

    shape = _content_table_shape(table_name)
    item_col = shape.get("item_col")
    type_col = shape.get("type_col")
    created_at_col = shape.get("created_at_col")
    page_col = shape.get("page_col")
    if not item_col or not type_col:
        return

    item_ids = [item.item_id for item in items if item.item_id]
    if not item_ids:
        return

    binds: Dict[str, Any] = {"p_uid": firebase_uid}
    placeholders: List[str] = []
    for index, item_id in enumerate(item_ids):
        bind_name = f"p_item_{index}"
        binds[bind_name] = item_id
        placeholders.append(f":{bind_name}")

    last_signal_expr = f"MAX({created_at_col})" if created_at_col else "NULL"
    max_page_expr = f"MAX({page_col})" if page_col else "NULL"

    sql = f"""
        SELECT
            {item_col} AS ITEM_ID,
            COUNT(*) AS TOTAL_SIGNALS,
            SUM(CASE WHEN UPPER({type_col}) = 'HIGHLIGHT' THEN 1 ELSE 0 END) AS HIGHLIGHT_COUNT,
            SUM(CASE WHEN UPPER({type_col}) = 'INSIGHT' THEN 1 ELSE 0 END) AS INSIGHT_COUNT,
            SUM(CASE WHEN UPPER({type_col}) = 'PERSONAL_NOTE' THEN 1 ELSE 0 END) AS NOTE_COUNT,
            {last_signal_expr} AS LAST_SIGNAL_AT,
            {max_page_expr} AS MAX_PAGE_NUMBER
        FROM {table_name}
        WHERE FIREBASE_UID = :p_uid
          AND {item_col} IN ({', '.join(placeholders)})
        GROUP BY {item_col}
    """

    item_map = {item.item_id: item for item in items}
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, binds)
                for row in cur.fetchall() or []:
                    item = item_map.get(str(row[0] or "").strip())
                    if item is None:
                        continue
                    item.total_signals = _to_int(row[1]) or 0
                    item.highlight_count = _to_int(row[2]) or 0
                    item.insight_count = _to_int(row[3]) or 0
                    item.note_count = _to_int(row[4]) or 0
                    item.last_signal_at = _to_datetime(row[5])
                    item.max_page_number = _to_int(row[6])
    except Exception as exc:
        logger.warning("Failed to hydrate inner space content stats for uid=%s: %s", firebase_uid, exc)


def _pick_continue_item(items: List[_InnerSpaceItem]) -> Optional[_InnerSpaceItem]:
    ranked = sorted(
        [item for item in items if item.item_type != "PERSONAL_NOTE"],
        key=lambda item: (
            1 if item.reading_status.upper() == "READING" else 0,
            1 if item.total_signals > 0 else 0,
            _datetime_score(item.last_activity_at),
        ),
        reverse=True,
    )
    return ranked[0] if ranked else None


def _pick_latest_sync_item(items: List[_InnerSpaceItem], exclude_ids: set[str]) -> Optional[_InnerSpaceItem]:
    ranked = sorted(
        [item for item in items if item.item_id not in exclude_ids],
        key=lambda item: (
            _datetime_score(item.last_activity_at),
            item.total_signals,
        ),
        reverse=True,
    )
    return ranked[0] if ranked else None


def _pick_dormant_gem_item(
    items: List[_InnerSpaceItem],
    active_themes: List[str],
    exclude_ids: set[str],
) -> Optional[_InnerSpaceItem]:
    now = datetime.now(timezone.utc)
    dormant_cutoff = now - timedelta(days=21)
    candidates = [item for item in items if item.item_id not in exclude_ids and (item.last_activity_at or item.created_at or now) <= dormant_cutoff]
    if not candidates:
        candidates = [item for item in items if item.item_id not in exclude_ids]
    ranked = sorted(
        candidates,
        key=lambda item: (
            _theme_overlap(item, active_themes),
            1 if item.total_signals > 0 else 0,
            -_datetime_score(item.last_activity_at),
        ),
        reverse=True,
    )
    return ranked[0] if ranked else None


def _resolve_active_themes(items: List[_InnerSpaceItem], profile: Dict[str, Any]) -> List[str]:
    profile_themes = [str(theme or "").strip() for theme in (profile.get("active_themes") or []) if str(theme or "").strip()]
    if profile_themes:
        return profile_themes[:4]

    counts: Counter[str] = Counter()
    display_names: Dict[str, str] = {}
    for item in items[:40]:
        for tag in item.tags:
            cleaned = str(tag or "").strip()
            if not cleaned:
                continue
            normalized = cleaned.lower()
            if normalized in _STOP_TAGS or len(normalized) < 3:
                continue
            counts[normalized] += 1
            display_names.setdefault(normalized, cleaned)
    return [display_names[key] for key, _count in counts.most_common(4)]


def _build_continue_card(item: Optional[_InnerSpaceItem]) -> DiscoveryInnerSpaceCard:
    if item is None:
        return DiscoveryInnerSpaceCard(
            slot=DiscoveryInnerSpaceSlot.CONTINUE_THIS,
            family="CONTINUE THIS",
            title="Your archive is ready for a first thread",
            summary="Add a book, article, note, or film to start building an active continuation lane here.",
            sources=["Local Library"],
            prompt_seed="Suggest the best next item to add to my archive so Discovery can start connecting themes.",
        )

    progress = _annotation_progress(item)
    signal_bits = []
    if item.insight_count:
        signal_bits.append(f"{item.insight_count} insight{'s' if item.insight_count != 1 else ''}")
    if item.highlight_count:
        signal_bits.append(f"{item.highlight_count} highlight{'s' if item.highlight_count != 1 else ''}")

    if progress is not None and item.max_page_number:
        summary = f"Tracked up to around page {item.max_page_number}. {' and '.join(signal_bits) if signal_bits else 'Reading activity is already attached to this thread.'}"
    elif signal_bits:
        summary = f"Still active in your archive. {' and '.join(signal_bits)} already point back to this item."
    else:
        summary = "Still marked as active reading. Resume this thread and extend it with new notes or highlights."

    return DiscoveryInnerSpaceCard(
        slot=DiscoveryInnerSpaceSlot.CONTINUE_THIS,
        family="CONTINUE THIS",
        title=item.title,
        summary=summary,
        sources=_item_sources(item),
        item_id=item.item_id,
        item_type=item.item_type,
        progress_percent=progress,
        metadata=_item_meta_label(item),
        prompt_seed=f'Continue from "{item.title}" and reconstruct the main thread, attached notes, and the best next question.',
        focus_hint="highlights" if item.total_signals > 0 else "info",
        score=_base_item_score(item),
    )


def _build_latest_sync_card(item: Optional[_InnerSpaceItem]) -> DiscoveryInnerSpaceCard:
    if item is None:
        return DiscoveryInnerSpaceCard(
            slot=DiscoveryInnerSpaceSlot.LATEST_SYNC,
            family="LATEST SYNC",
            title="No recent sync yet",
            summary="As soon as new library activity lands, the freshest thread will appear here with direct context.",
            sources=["Recent Activity"],
            prompt_seed="Show me the most recent meaningful changes in my archive.",
        )

    age_label = _age_label(item.last_activity_at)
    sync_count = item.insight_count + item.highlight_count + item.note_count
    if sync_count > 0:
        summary = f"Updated {age_label}. {sync_count} archive signal{'s' if sync_count != 1 else ''} are connected to this source."
    else:
        summary = f"Updated {age_label}. This is the freshest item in your archive right now."

    return DiscoveryInnerSpaceCard(
        slot=DiscoveryInnerSpaceSlot.LATEST_SYNC,
        family="LATEST SYNC",
        title=item.title,
        summary=summary,
        sources=_item_sources(item),
        item_id=item.item_id,
        item_type=item.item_type,
        badge=age_label,
        metadata=_item_meta_label(item),
        prompt_seed=f'What changed most recently around "{item.title}", and how does it connect to the rest of my archive?',
        focus_hint="highlights" if item.total_signals > 0 else "info",
        score=_base_item_score(item),
    )


def _build_dormant_gem_card(item: Optional[_InnerSpaceItem], active_themes: List[str]) -> DiscoveryInnerSpaceCard:
    if item is None:
        return DiscoveryInnerSpaceCard(
            slot=DiscoveryInnerSpaceSlot.DORMANT_GEM,
            family="DORMANT GEM",
            title="Dormant links will surface here",
            summary="Once older material accumulates, Discovery will recover overlooked items that still fit your current themes.",
            sources=["Archive Vault"],
            prompt_seed="Find an older item in my archive that is still worth resurfacing.",
        )

    overlap = [theme for theme in active_themes if theme.lower() in {tag.lower() for tag in item.tags}]
    overlap_text = ", ".join(overlap[:2]) if overlap else "your current archive"
    quiet_since = _age_label(item.last_activity_at or item.created_at)
    summary = f"Quiet for {quiet_since}, but it still overlaps with {overlap_text}. This is a strong resurfacing candidate."

    return DiscoveryInnerSpaceCard(
        slot=DiscoveryInnerSpaceSlot.DORMANT_GEM,
        family="DORMANT GEM",
        title=item.title,
        summary=summary,
        sources=_item_sources(item),
        item_id=item.item_id,
        item_type=item.item_type,
        metadata=_item_meta_label(item),
        prompt_seed=f'Resurface "{item.title}" and explain why it still matters to my current themes.',
        focus_hint="info",
        score=_base_item_score(item) + float(_theme_overlap(item, active_themes)),
    )


def _build_theme_pulse_card(
    active_themes: List[str],
    profile: Dict[str, Any],
    items: List[_InnerSpaceItem],
) -> DiscoveryInnerSpaceCard:
    themes = active_themes[:2]
    recurring_sources = [str(value or "").strip() for value in (profile.get("recurring_sources") or []) if str(value or "").strip()]
    if themes:
        summary = f'Your recent archive leans toward "{themes[0]}"'
        if len(themes) > 1:
            summary += f' and "{themes[1]}".'
        else:
            summary += "."
    else:
        summary = "Theme pulse will strengthen as more tagged material and memory profile signals accumulate."

    if recurring_sources:
        summary += f" Repeating sources: {', '.join(recurring_sources[:2])}."

    badge = f"{len(active_themes)} active theme{'s' if len(active_themes) != 1 else ''}" if active_themes else None
    metadata = "MEMORY PROFILE" if profile else f"{len(items)} archive item{'s' if len(items) != 1 else ''}"

    return DiscoveryInnerSpaceCard(
        slot=DiscoveryInnerSpaceSlot.THEME_PULSE,
        family="THEME PULSE",
        title="OBSIDIAN_PULSE" if active_themes else "THEME_PULSE",
        summary=summary,
        sources=["Synapse Analytics" if profile else "Recent Archive"],
        badge=badge,
        metadata=metadata,
        prompt_seed="Map the strongest active themes in my recent archive and show the best next connections.",
        score=float(len(active_themes)),
    )


def _table_columns(table_name: str) -> set[str]:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COLUMN_NAME
                    FROM USER_TAB_COLUMNS
                    WHERE TABLE_NAME = :p_table
                    """,
                    {"p_table": table_name.upper()},
                )
                return {str(row[0] or "").upper() for row in cur.fetchall() or []}
    except Exception:
        return set()


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
            return [str(item).strip() for item in parsed if str(item).strip()][:20]
    except Exception:
        pass
    return [part.strip() for part in text.split(",") if part.strip()][:20]


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _datetime_score(value: Optional[datetime]) -> float:
    return value.timestamp() if value else 0.0


def _annotation_progress(item: _InnerSpaceItem) -> Optional[int]:
    if not item.page_count or not item.max_page_number or item.page_count <= 0:
        return None
    ratio = max(0.0, min(float(item.max_page_number) / float(item.page_count), 1.0))
    percent = int(round(ratio * 100))
    return percent if percent > 0 else None


def _item_sources(item: _InnerSpaceItem) -> List[str]:
    primary = {
        "BOOK": "Local Library",
        "ARTICLE": "Articles",
        "MOVIE": "Cinema",
        "SERIES": "Cinema",
        "PERSONAL_NOTE": "Personal Notes",
    }.get(item.item_type, "Archive")

    secondary = item.author.strip() if item.author else ""
    if item.item_type == "PERSONAL_NOTE":
        secondary = item.personal_note_category or "Ideas"

    sources = [primary]
    if secondary:
        sources.append(secondary)
    return sources


def _item_meta_label(item: _InnerSpaceItem) -> Optional[str]:
    if item.reading_status.strip():
        return item.reading_status.strip().upper()
    if item.item_type == "PERSONAL_NOTE" and item.personal_note_category:
        return item.personal_note_category.upper()
    return item.item_type


def _theme_overlap(item: _InnerSpaceItem, active_themes: List[str]) -> int:
    if not active_themes or not item.tags:
        return 0
    item_tags = {tag.lower() for tag in item.tags}
    return sum(1 for theme in active_themes if theme.lower() in item_tags)


def _age_label(value: Optional[datetime]) -> str:
    if value is None:
        return "recently"
    now = datetime.now(timezone.utc)
    delta = now - value
    if delta < timedelta(minutes=1):
        return "just now"
    if delta < timedelta(hours=1):
        minutes = max(1, int(delta.total_seconds() // 60))
        return f"{minutes}m ago"
    if delta < timedelta(days=1):
        hours = max(1, int(delta.total_seconds() // 3600))
        return f"{hours}h ago"
    if delta < timedelta(days=14):
        return f"{delta.days}d ago"
    return value.strftime("%b %d")


def _base_item_score(item: _InnerSpaceItem) -> float:
    return float(item.total_signals + item.insight_count + item.highlight_count) + (_datetime_score(item.last_activity_at) / 1_000_000_000)
