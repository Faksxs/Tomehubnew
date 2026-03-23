from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DiscoveryCategory(str, Enum):
    ACADEMIC = "ACADEMIC"
    RELIGIOUS = "RELIGIOUS"
    LITERARY = "LITERARY"
    CULTURE_HISTORY = "CULTURE_HISTORY"


class DiscoveryInnerSpaceSlot(str, Enum):
    CONTINUE_THIS = "continue_this"
    LATEST_SYNC = "latest_sync"
    DORMANT_GEM = "dormant_gem"
    THEME_PULSE = "theme_pulse"


class DiscoveryActionType(str, Enum):
    OPEN_SOURCE = "open_source"
    OPEN_ANCHOR = "open_anchor"
    ASK_LOGOSCHAT = "ask_logoschat"
    SEND_TO_FLUX = "send_to_flux"
    SAVE_FOR_LATER = "save_for_later"


class DiscoverySourceRef(BaseModel):
    label: str
    url: Optional[str] = None
    kind: Optional[str] = None


class DiscoveryAnchorRef(BaseModel):
    item_id: str
    title: str
    item_type: Optional[str] = None


class DiscoveryEvidence(BaseModel):
    kind: str
    label: str
    value: Optional[str] = None


class DiscoveryAction(BaseModel):
    type: DiscoveryActionType
    label: str
    url: Optional[str] = None
    prompt_seed: Optional[str] = None
    anchor_id: Optional[str] = None


class DiscoveryCard(BaseModel):
    id: str
    category: DiscoveryCategory
    family: str
    title: str
    summary: str
    why_seen: str
    confidence_label: str
    freshness_label: Optional[str] = None
    primary_source: str
    source_refs: List[DiscoverySourceRef] = Field(default_factory=list)
    image_url: Optional[str] = None
    anchor_refs: List[DiscoveryAnchorRef] = Field(default_factory=list)
    evidence: List[DiscoveryEvidence] = Field(default_factory=list)
    actions: List[DiscoveryAction] = Field(default_factory=list)
    score: float = 0.0


class DiscoveryFamilySection(BaseModel):
    family: str
    title: str
    description: str
    source_label: str
    cards: List[DiscoveryCard] = Field(default_factory=list)


class DiscoveryBoardMetadata(BaseModel):
    category_title: str
    category_description: str
    last_updated_at: str
    active_provider_names: List[str] = Field(default_factory=list)
    total_cards: int = 0


class DiscoveryBoardResponse(BaseModel):
    category: DiscoveryCategory
    featured_card: Optional[DiscoveryCard] = None
    family_sections: List[DiscoveryFamilySection] = Field(default_factory=list)
    metadata: DiscoveryBoardMetadata


class DiscoveryInnerSpaceCard(BaseModel):
    slot: DiscoveryInnerSpaceSlot
    family: str
    title: str
    summary: str
    sources: List[str] = Field(default_factory=list)
    item_id: Optional[str] = None
    item_type: Optional[str] = None
    progress_percent: Optional[int] = None
    badge: Optional[str] = None
    metadata: Optional[str] = None
    prompt_seed: Optional[str] = None
    focus_hint: Optional[str] = None
    score: float = 0.0


class DiscoveryInnerSpaceMetadata(BaseModel):
    last_updated_at: str
    active_theme_count: int = 0
    has_memory_profile: bool = False
    total_items_considered: int = 0


class DiscoveryInnerSpaceResponse(BaseModel):
    cards: List[DiscoveryInnerSpaceCard] = Field(default_factory=list)
    metadata: DiscoveryInnerSpaceMetadata


class DiscoveryPageBoards(BaseModel):
    academic: DiscoveryBoardResponse
    religious: DiscoveryBoardResponse
    literary: DiscoveryBoardResponse
    culture_history: DiscoveryBoardResponse


class DiscoveryPageMetadata(BaseModel):
    last_updated_at: str
    board_errors: List[str] = Field(default_factory=list)
    used_cached_fallbacks: bool = False


class DiscoveryPageResponse(BaseModel):
    inner_space: DiscoveryInnerSpaceResponse
    boards: DiscoveryPageBoards
    metadata: DiscoveryPageMetadata
