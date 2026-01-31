# -*- coding: utf-8 -*-
"""
Layer 4: Flow Session Models
============================
Pydantic models for the Knowledge Stream (Layer 4) API.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class FlowMode(str, Enum):
    """Flow session modes (maps to Horizon Slider)."""
    FOCUS = "FOCUS"           # 0-25%: Tight Context
    EXPAND = "EXPAND"         # 25-50%: Author's Mind
    DISCOVER = "DISCOVER"     # 50-75%: Syntopic Debate
    BRIDGE = "BRIDGE"         # 75-100%: Lateral Drift


class FlowStartRequest(BaseModel):
    """Request to start a new Flow session."""
    firebase_uid: str
    anchor_type: Literal["note", "book", "author", "topic"] = "note"
    anchor_id: str  # ID of the note, book_id, author name, or topic tag
    mode: FlowMode = FlowMode.FOCUS
    horizon_value: float = Field(default=0.25, ge=0.0, le=1.0)  # 0.0 to 1.0
    resource_type: Optional[str] = None


class FlowNextRequest(BaseModel):
    """Request to get the next batch of cards."""
    firebase_uid: str
    session_id: str
    batch_size: int = Field(default=5, ge=1, le=10)


class FlowFeedbackRequest(BaseModel):
    """User feedback on a shown card."""
    firebase_uid: str
    session_id: str
    chunk_id: str
    action: Literal["like", "dislike", "skip", "save"]


class FlowCard(BaseModel):
    """A single card in the Flow stream."""
    flow_id: str  # Unique ID for React key (UUID)
    chunk_id: str
    content: str
    title: str
    author: Optional[str] = None
    page_number: Optional[int] = None
    source_type: Literal["personal", "pdf_chunk", "graph_bridge", "external"]
    epistemic_level: Literal["A", "B", "C"] = "B"
    reason: Optional[str] = None  # "Connected via: Freedom"
    zone: int = 1  # 1-4 (Which phase generated this)


class FlowSessionState(BaseModel):
    """Internal state stored in Redis."""
    session_id: str
    firebase_uid: str
    global_anchor_id: str
    global_anchor_vector: Optional[List[float]] = None
    local_anchor_id: Optional[str] = None
    local_anchor_vector: Optional[List[float]] = None
    session_centroid: Optional[List[float]] = None
    horizon_value: float = 0.25
    mode: FlowMode = FlowMode.FOCUS
    cards_shown: int = 0
    resource_type: Optional[str] = None
    created_at: str


class FlowStartResponse(BaseModel):
    """Response after starting a Flow session."""
    session_id: str
    initial_cards: List[FlowCard]
    topic_label: str  # "Ethics in Camus" (Human-readable)


class PivotInfo(BaseModel):
    """Information about a discovery jump or automatic pivot."""
    type: str  # "discovery_gap", "discovery_dormant", "discovery_distant", "saturation_pivot"
    message: str  # "Jumping to a dormant book to freshen up..."


class FlowNextResponse(BaseModel):
    """Response with the next batch of cards."""
    cards: List[FlowCard]
    has_more: bool = True
    pivot_info: Optional[PivotInfo] = None
    session_state: Optional[dict] = None  # For UI debugging
