# -*- coding: utf-8 -*-
"""
Layer 4: Flow Service (The Flux Engine)
=====================================================
Orchestrates the "Expanding Horizons" algorithm with Dual Anchor gravity.

"""

import logging
import re
from typing import List, Optional, Tuple, Set, Dict, Any  # Added Dict explicit import
from datetime import datetime
import numpy as np
import array
import uuid

from models.flow_models import (
    FlowMode, FlowCard, FlowSessionState,
    FlowStartRequest, FlowStartResponse,
    FlowNextRequest, FlowNextResponse, PivotInfo
)
from services.flow_session_service import (
    FlowSessionManager, get_flow_session_manager
)
from services.embedding_service import get_embedding, get_query_embedding
from services.flow_text_repair_service import repair_for_flow_card
from infrastructure.db_manager import DatabaseManager, safe_read_clob
import oracledb  # For DatabaseError exception handling
from config import settings
from utils.text_utils import normalize_text

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_note_content(raw_content: str) -> str:
    """
    Extract clean note content from database format.
    Personal notes are stored with metadata prefix like:
    'Title: X Author: Y Content/Notes: <actual content>'
    
    This function extracts only the actual content.
    """
    if not raw_content:
        return ""
    
    import re
    # Check if content has the metadata prefix pattern
    if raw_content.startswith("Title:"):
        # Extract content after "Content/Notes:" marker
        match = re.search(r'Content/Notes:\s*(.*)', raw_content, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    # If no pattern found, return as-is
    return raw_content.strip()


# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

# Zone Configuration (Maps to Horizon Slider: 0.0 - 1.0)
ZONE_CONFIG = {
    1: {"name": "Focus", "horizon_min": 0.0, "horizon_max": 0.33},
    2: {"name": "Syntopic", "horizon_min": 0.33, "horizon_max": 0.66},
    3: {"name": "Discovery", "horizon_min": 0.66, "horizon_max": 1.0},
}

# How many candidates to fetch per zone
ZONE_FETCH_LIMITS = {1: 15, 2: 15, 3: 10}

# Minimum similarity threshold for semantic matches
SIMILARITY_THRESHOLDS = {
    "syntopic": 0.60,  # Zone 3
    "discovery": 0.45, # Zone 4
    "dedup": 0.90,     # Semantic deduplication
}

# Resource type helper constants
BOOK_SOURCE_TYPES = ("PDF", "EPUB", "PDF_CHUNK", "BOOK", "HIGHLIGHT", "INSIGHT")
ALL_NOTES_SOURCE_TYPES = ("HIGHLIGHT", "INSIGHT")
DEFAULT_ANCHOR_ID = "General Discovery"
DEFAULT_TOPIC_LABEL = "Flux"
INITIAL_BATCH_SIZE = 5
FLOW_CONTENT_CHAR_LIMIT = 650
FLOW_CONTENT_FORWARD_WINDOW = 120
LIMITED_SOURCE_TYPES = {"PDF", "EPUB", "PDF_CHUNK", "ARTICLE", "WEBSITE"}


def _is_numeric_session_id(session_id: str) -> bool:
    """Check if session_id can be used in TOMEHUB_FLOW_SEEN queries (NUMBER column)."""
    if session_id is None:
        return False
    return str(session_id).strip().isdigit()


def _build_seen_exclusion_sql(session_id: str, params: dict, column_name: str = "id") -> tuple:
    """
    Build SQL exclusion clause for FLOW_SEEN table.
    
    Returns (sql_clause, updated_params) where sql_clause is either:
    - The exclusion subquery if session_id is numeric
    - Empty string if session_id is UUID (can't query FLOW_SEEN)
    
    This prevents ORA-01722 errors when UUID session_ids are used.
    """
    if not _is_numeric_session_id(session_id):
        # UUID session_id - can't query NUMBER column, skip exclusion
        return "", params
    
    # Numeric session_id - safe to add exclusion (NOT EXISTS is faster than NOT IN on Oracle)
    sql_clause = f" AND NOT EXISTS (SELECT 1 FROM TOMEHUB_FLOW_SEEN fs WHERE fs.chunk_id = {column_name} AND fs.session_id = :p_sid) "
    new_params = {**params, "p_sid": int(session_id)}
    return sql_clause, new_params


def _normalize_flow_text(text: str) -> str:
    """Normalize whitespace for card-safe display text."""
    return re.sub(r"\s+", " ", str(text or "")).strip()



def _limit_flow_content(text: str, limit: int = FLOW_CONTENT_CHAR_LIMIT) -> str:
    """
    Limit long card text with sentence-aware boundaries.

    Strategy:
    1. Normalize whitespace.
    2. If length <= limit, return as-is.
    3. Prefer the last sentence end within [0, limit].
    4. Else look for first sentence end in [limit, limit + 120].
    5. Else cut on last whitespace and append "...".
    """
    normalized = _normalize_flow_text(text)
    if not normalized:
        return ""

    if len(normalized) <= limit:
        # Start-Trimming Logic (New)
        # If text does not start with upper case and is not a quote, find first full sentence.
        if normalized and len(normalized) > 10 and not normalized[0].isupper() and not normalized.startswith(('"', "'", "“", "‘")):
             # Look for ". X" pattern
             match = re.search(r'[.!?]\s+([A-ZĞÜŞİÖÇ])', normalized)
             if match:
                 # Start from the capital letter found
                 normalized = normalized[match.start(1):]

        return normalized

    sentence_end_pattern = r"[.!?\u2026]"
    left_window = normalized[:limit]

    left_matches = list(re.finditer(sentence_end_pattern, left_window))
    if left_matches:
        cut_idx = left_matches[-1].end()
        candidate = normalized[:cut_idx].strip()
        if candidate:
            return candidate

    right_window = normalized[limit:limit + FLOW_CONTENT_FORWARD_WINDOW]
    right_match = re.search(sentence_end_pattern, right_window)
    if right_match:
        cut_idx = limit + right_match.end()
        candidate = normalized[:cut_idx].strip()
        if candidate:
            return candidate

    fallback_idx = left_window.rfind(" ")
    if fallback_idx <= 0:
        fallback_idx = limit

    candidate = normalized[:fallback_idx].strip()
    if not candidate:
        candidate = normalized[:limit].strip()
    if not candidate:
        candidate = normalized[:limit].strip()
    
    # Start-Trimming Logic (Applied to result)
    if candidate and len(candidate) > 10 and not candidate[0].isupper() and not candidate.startswith(('"', "'", "“", "‘")):
         match = re.search(r'[.!?]\s+([A-ZĞÜŞİÖÇ])', candidate)
         if match:
             candidate = candidate[match.start(1):]
             
    return f"{candidate}..."


def _prepare_flow_card_content(content: str, source_type: Optional[str]) -> str:
    """Apply source-aware text limiting for flow cards."""
    source = str(source_type or "").strip().upper()
    safe_content = "" if content is None else str(content)
    repaired = repair_for_flow_card(safe_content, source)
    if source in LIMITED_SOURCE_TYPES:
        return _limit_flow_content(repaired, FLOW_CONTENT_CHAR_LIMIT)
    return repaired


class FlowService:
    """
    The Knowledge Stream Engine.

    Responsibilities:
    - Start a new Flow session from an anchor (note, book, topic)
    - Generate candidates from multiple zones based on Horizon Slider
    - Filter using session state (dedup, negative feedback)
    - Orchestrate prefetching for smooth UX
    """
    def __init__(self):
        self.session_manager: FlowSessionManager = get_flow_session_manager()

    def start_session(self, request: FlowStartRequest | None = None, **kwargs) -> FlowStartResponse:
        """
        Start a new Flow session and return the initial batch.
        Accepts either a FlowStartRequest or kwargs for legacy/debug callers.
        """
        if request is None:
            # Backwards-compatibility: allow "horizon" alias
            if "horizon" in kwargs and "horizon_value" not in kwargs:
                kwargs["horizon_value"] = kwargs.pop("horizon")
            request = FlowStartRequest(**kwargs)

        anchor_type = request.anchor_type
        anchor_id = request.anchor_id or DEFAULT_ANCHOR_ID

        # Resolve anchor vector + label
        anchor_vector, label, resolved_id = self._resolve_anchor(
            anchor_type=anchor_type,
            anchor_id=anchor_id,
            firebase_uid=request.firebase_uid,
            resource_type=request.resource_type,
            category=request.category
        )

        resolved_anchor_id = resolved_id or anchor_id
        topic_label = label or anchor_id or DEFAULT_TOPIC_LABEL

        # Create session
        state = self.session_manager.create_session(
            firebase_uid=request.firebase_uid,
            anchor_id=resolved_anchor_id,
            anchor_vector=anchor_vector,
            horizon_value=request.horizon_value,
            mode=request.mode,
            resource_type=request.resource_type,
            category=request.category
        )

        # Generate initial cards
        initial_cards = self._generate_batch(
            session_id=state.session_id,
            firebase_uid=request.firebase_uid,
            batch_size=INITIAL_BATCH_SIZE
        )

        # LIGHTWEIGHT OPTIMIZATION: Periodically prune old seen records (approx. 5% of new sessions)
        import random
        import threading
        if random.random() < 0.05:
            logger.info(f"Triggering background pruning for UID: {request.firebase_uid}")
            threading.Thread(target=self._prune_old_seen_records, args=(request.firebase_uid,), daemon=True).start()

        return FlowStartResponse(
            session_id=state.session_id,
            initial_cards=initial_cards,
            topic_label=topic_label
        )
    
    def reset_anchor(self, session_id: str, anchor_type: str, anchor_id: str, firebase_uid: str, resource_type: Optional[str] = None, category: Optional[str] = None) -> Tuple[str, Optional[PivotInfo]]:
        """
        Manually pivot the session to a new anchor.
        Supports 'discovery' type for automated discovery jumps.
        """
        state = self.session_manager.get_session(session_id)
        if not state:
            raise ValueError(f"Session not found: {session_id}")

        logger.info(f"[FLOW] Manual reset: type={anchor_type}, id={anchor_id}")
        
        pivot_info = None
        if anchor_type == "discovery":
            # POWER DISCOVERY JUMP
            new_vector, new_label, resolved_id, pivot_info = self._discovery_pivot(state)
            if not new_vector:
                raise ValueError("Could not find a valid discovery jump target.")
        else:
            # Standard Manual Pivot
            new_vector, new_label, resolved_id = self._resolve_anchor(
                anchor_type, anchor_id, firebase_uid, resource_type, category
            )
            if not new_vector and anchor_type == "topic" and category:
                # Category filter can legitimately yield no candidate content.
                # Fallback to an unfiltered topic anchor instead of failing the pivot.
                logger.warning(
                    "[FLOW] reset_anchor fallback: no topic anchor with category=%s, retrying unfiltered",
                    category,
                )
                new_vector, new_label, resolved_id = self._resolve_anchor(
                    anchor_type, anchor_id, firebase_uid, resource_type, None
                )
            if not new_vector:
                raise ValueError(f"Could not resolve new anchor: {anchor_id}")

        # Update session state via manager
        self.session_manager.update_session_anchor(
            session_id=session_id,
            anchor_id=resolved_id,
            anchor_vector=new_vector
        )
        
        # Persist category and resource filters so subsequent fetches use them
        self.session_manager.update_session_filters(
            session_id=session_id,
            resource_type=resource_type,
            category=category
        )
        
        return new_label or f"Pivoted to {anchor_id}", pivot_info

    def prefetch_batch(self, session_id: str, firebase_uid: str, batch_size: int = 10):
        """
        Generate cards in background and push to session prefetch queue.
        """
        # Generate cards without consuming them (check_queue=False implicitly)
        cards = self._generate_batch(
            session_id=session_id,
            firebase_uid=firebase_uid,
            batch_size=batch_size
        )
        
        if cards:
            logger.info(f"[FLOW] Enqueuing {len(cards)} prefetched cards for session {session_id}")
            self.session_manager.enqueue_prefetch(session_id, cards)

    def get_next_batch(self, request: FlowNextRequest) -> FlowNextResponse:
        """
        Get the next batch of cards. Triggers Discovery Pivot if saturated.
        """
        state = self.session_manager.get_session(request.session_id)
        if not state:
            logger.error(f"Session not found: {request.session_id}")
            return FlowNextResponse(cards=[], has_more=False)
        
        # 1. Try to get from Prefetch Queue first
        cached_data = self.session_manager.dequeue_prefetch(request.session_id, request.batch_size)
        if cached_data:
            logger.info(f"[FLOW] Returning {len(cached_data)} cached cards for session {request.session_id}")
            # Rehydrate FlowCard objects from dicts
            cards = [FlowCard(**c) for c in cached_data]
            
            # Since these were already "seen" logic-wise when generated? 
            # Wait, _generate_batch marks them seen. So we don't need to mark them again.
            # But we might want to verify they haven't been seen in the meantime?
            # For simpler logic, we assume queue content is valid.
            
            # Update local anchor logic for the resumed batch
            if cards:
                state.local_anchor_id = cards[-1].chunk_id
                # cards_shown was handled at generation time? 
                # PROPOSAL: Move cards_shown increment to here (Delivery time).
                # But _generate_batch does it. If we persist 'state' in _generate_batch, it's done.
                # Let's keep it simple: If it's in queue, it's ready to go.
                self.session_manager.update_session(state)
                
            return FlowNextResponse(
                cards=cards,
                has_more=True,
                session_state={"cards_shown": state.cards_shown}
            )

        # 2. If queue empty, generate on demand
        cards = self._generate_batch(
            session_id=state.session_id,
            firebase_uid=state.firebase_uid,
            batch_size=request.batch_size
        )
        
        # SATURATION DETECTION: If 0 cards, attempt an automated Discovery Jump
        if not cards:
            logger.info(f"[FLOW] Saturation detected for session {state.session_id}. Attempting Discovery Jump...")
            new_vector, new_label, resolved_id, pivot_info = self._discovery_pivot(state)
            
            if new_vector:
                # Update session anchor
                self.session_manager.update_session_anchor(
                    session_id=state.session_id,
                    anchor_id=resolved_id,
                    anchor_vector=new_vector
                )
                
                # Create a specialized pivot card to show the transition
                pivot_card = FlowCard(
                    flow_id=str(uuid.uuid4()),
                    chunk_id=f"pivot_{resolved_id}",
                    content=pivot_info.message,
                    title="Yönlendirilmiş Keşif",
                    source_type="external",
                    epistemic_level="A",
                    zone=4,
                    reason=f"[Kesif]: {new_label}"
                )
                
                return FlowNextResponse(
                    cards=[pivot_card],
                    has_more=True,
                    pivot_info=pivot_info,
                    session_state={"status": "pivoted", "anchor_id": resolved_id}
                )
        
        return FlowNextResponse(
            cards=cards,
            has_more=len(cards) > 0,
            session_state={"cards_shown": state.cards_shown}
        )

    def _discovery_pivot(self, state: FlowSessionState) -> Tuple[Optional[List[float]], str, str, PivotInfo]:
        """
        Hierarchical Discovery Logic:
        1. Distant but related (2-3 graph hops from seen content)
        2. Dormant Books (User has them but hasn't seen them in ages)
        3. Epistemic Gaps (High centrality concepts unseen by this user)
        """
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    # PRIORITY 1: Epistemic Gaps (High centrality concepts NOT in seen history)
                    # This satisfies "hiç dokunulmamış ama merkezi concept"
                    params = {"p_uid": state.firebase_uid, "p_sid": state.session_id}
                    
                    sql = """
                        SELECT DISTINCT c.id, c.name, ct.id as content_id, ct.title
                        FROM TOMEHUB_CONCEPTS c
                        JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c.id = cc.concept_id
                        JOIN TOMEHUB_CONTENT_V2 ct ON cc.content_id = ct.id
                        WHERE ct.firebase_uid = :p_uid
                        AND ct.ai_eligible = 1
                        AND NOT EXISTS (
                            SELECT 1 FROM TOMEHUB_FLOW_SEEN fs WHERE fs.chunk_id = ct.id AND TO_CHAR(fs.session_id) = :p_sid
                        )
                        AND c.id NOT IN (
                            SELECT concept_id FROM TOMEHUB_CONCEPT_CHUNKS 
                            WHERE content_id IN (SELECT fs.chunk_id FROM TOMEHUB_FLOW_SEEN fs WHERE fs.firebase_uid = :p_uid)
                        )
                        AND (cc.strength IS NULL OR cc.strength >= :p_strength)
                    """
                    params["p_strength"] = settings.CONCEPT_STRENGTH_MIN
                    sql, params = self._apply_resource_filter(sql, params, state.resource_type)
                    sql, params = self._apply_category_filter(sql, params, state.category)
                        
                    sql += " ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 1 ROW ONLY "
                    cursor.execute(sql, params)
                    
                    row = cursor.fetchone()
                    if row:
                        concept_id, concept_name, content_id, title = row
                        cursor.execute("SELECT VEC_EMBEDDING FROM TOMEHUB_CONTENT_V2 WHERE id = :p_id", {"p_id": content_id})
                        vec_row = cursor.fetchone()
                        if vec_row:
                            return (
                                self._to_list(vec_row[0]), 
                                f"Temel: {concept_name}", 
                                str(content_id),
                                PivotInfo(type="discovery_gap", message=f"Henüz incelemediğiniz temel bir kavrama geçiş yapılıyor: '{title}' içinde '{concept_name}'.")
                            )

                    # PRIORITY 2: Dormant Books / Distant Content
                    # (Simplified: Random discovery of unseen books/authors for now)
                    params = {"p_uid": state.firebase_uid}
                    sql = """
                        SELECT id, title, VEC_EMBEDDING
                        FROM TOMEHUB_CONTENT_V2
                        WHERE firebase_uid = :p_uid
                        AND ai_eligible = 1
                        AND title NOT IN (
                            SELECT title FROM TOMEHUB_CONTENT_V2 
                            WHERE id IN (SELECT fs.chunk_id FROM TOMEHUB_FLOW_SEEN fs WHERE fs.firebase_uid = :p_uid)
                        )
                    """
                    sql, params = self._apply_resource_filter(sql, params, state.resource_type)
                    sql, params = self._apply_category_filter(sql, params, state.category)
                        
                    sql += " ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 1 ROW ONLY "
                    cursor.execute(sql, params)
                    
                    row = cursor.fetchone()
                    if row:
                        content_id, title, vec_data = row
                        return (
                            self._to_list(vec_data),
                            title,
                            str(content_id),
                            PivotInfo(type="discovery_dormant", message=f"Jumping to a dormant path in your library: '{title}'.")
                        )
                        
        except Exception as e:
            logger.warning(f"Discovery Jump selection failed: {e}")
            
        return None, "", "", None
    
    # -------------------------------------------------------------------------
    # INTERNAL: ANCHOR RESOLUTION
    # -------------------------------------------------------------------------
    
    def _to_list(self, vec_data) -> Optional[List[float]]:
        """Helper to robustly convert Oracle vector data to Python list of floats."""
        if vec_data is None:
            return None
        if isinstance(vec_data, (list, tuple)):
            return [float(x) for x in vec_data]
        if hasattr(vec_data, 'tolist'): # For numpy/other types
            return [float(x) for x in vec_data.tolist()]
        if hasattr(vec_data, 'read'):
            # This handles LOBs (CLOB or BLOB)
            try:
                content = vec_data.read()
                if isinstance(content, str):
                    import json
                    data = json.loads(content)
                    return [float(x) for x in data] if isinstance(data, list) else None
                if isinstance(content, bytes):
                    # Handle binary vector (4-byte floats)
                    import struct
                    return list(struct.unpack(f"{len(content)//4}f", content))
            except Exception as e:
                logger.warning(f"Vector conversion error: {e}")
                return None
        return None

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Calculate cosine similarity."""
        a = np.array(vec_a)
        b = np.array(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def _apply_resource_filter(
        sql: str,
        params: dict,
        resource_type: Optional[str]
    ) -> Tuple[str, dict]:
        """
        Append resource-type filters to a SQL query.

        - BOOK: PDF/EPUB/PDF_CHUNK + BOOK + HIGHLIGHT/INSIGHT
        - ALL_NOTES: HIGHLIGHT/INSIGHT
        - PERSONAL_NOTE: PERSONAL_NOTE only
        - ARTICLE/WEBSITE: strict source_type match
        """
        if resource_type == 'PERSONAL_NOTE':
            sql += " AND content_type = 'PERSONAL_NOTE' "
        elif resource_type == 'ALL_NOTES':
            sql += " AND content_type IN ('HIGHLIGHT', 'INSIGHT') "
        elif resource_type == 'BOOK':
            sql += " AND content_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT') "
        elif resource_type in ('ARTICLE', 'WEBSITE'):
            sql += " AND content_type = :p_type "
            params["p_type"] = resource_type
        return sql, params

    @staticmethod
    def _apply_category_filter(
        sql: str,
        params: dict,
        category: Optional[str]
    ) -> Tuple[str, dict]:
        """
        Append category filter if active using normalized category table.
        """
        if category:
            norm = normalize_text(category)
            if not norm:
                return sql, params

            # Resolve content table alias from FROM/JOIN clauses.
            # This prevents invalid SQL like `TOMEHUB_CONTENT_V2.id` when table alias is used (e.g. `... FROM TOMEHUB_CONTENT_V2 t`).
            alias = "TOMEHUB_CONTENT_V2"
            alias_match = re.search(
                r"\b(?:FROM|JOIN)\s+TOMEHUB_CONTENT_V2\s+([A-Za-z_][A-Za-z0-9_$#]*)\b",
                sql,
                re.IGNORECASE,
            )
            if alias_match:
                alias = alias_match.group(1)
            else:
                legacy_match = re.search(
                    r"\b(?:FROM|JOIN)\s+TOMEHUB_CONTENT\s+([A-Za-z_][A-Za-z0-9_$#]*)\b",
                    sql,
                    re.IGNORECASE,
                )
                if legacy_match:
                    alias = legacy_match.group(1)

            sql += f"""
                AND EXISTS (
                    SELECT 1 FROM TOMEHUB_CONTENT_CATEGORIES cc
                    WHERE cc.content_id = {alias}.id
                    AND cc.category_norm = :p_cat_norm
                )
            """
            params["p_cat_norm"] = norm
        return sql, params

    def _select_low_engagement_note_anchor(
        self,
        firebase_uid: str,
        category: Optional[str] = None
    ) -> Tuple[Optional[List[float]], Optional[str], Optional[str]]:
        """
        Pick a low-engagement anchor from All Notes (highlights/insights).
        Heuristics:
        - Least seen in Flow (TOMEHUB_FLOW_SEEN)
        - Least context produced (fewest concept links)
        """
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    params = {"p_uid": firebase_uid}
                    sql = """
                        SELECT
                            t.id,
                            t.title,
                            t.content_chunk,
                            t.vec_embedding,
                            NVL(s.seen_count, 0) AS seen_count,
                            NVL(c.ctx_count, 0) AS ctx_count
                        FROM TOMEHUB_CONTENT_V2 t
                        LEFT JOIN (
                            SELECT chunk_id, COUNT(*) AS seen_count
                            FROM TOMEHUB_FLOW_SEEN
                            WHERE firebase_uid = :p_uid
                            GROUP BY chunk_id
                        ) s ON TO_CHAR(s.chunk_id) = TO_CHAR(t.id)
                        LEFT JOIN (
                            SELECT content_id, COUNT(*) AS ctx_count
                            FROM TOMEHUB_CONCEPT_CHUNKS
                            GROUP BY content_id
                        ) c ON c.content_id = t.id
                        WHERE LOWER(TRIM(t.firebase_uid)) = LOWER(TRIM(:p_uid))
                        AND t.ai_eligible = 1
                        AND t.content_type IN ('HIGHLIGHT', 'INSIGHT')
                        AND DBMS_LOB.GETLENGTH(t.content_chunk) > 12
                    """
                    sql, params = self._apply_category_filter(sql, params, category)
                    sql += """
                        ORDER BY
                            NVL(s.seen_count, 0) ASC,
                            NVL(c.ctx_count, 0) ASC,
                            DBMS_RANDOM.VALUE
                        FETCH FIRST 1 ROW ONLY
                    """
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    if not row:
                        return None, None, None

                    content_id, title, content_chunk, vec_data, seen_count, ctx_count = row
                    vec = self._to_list(vec_data)
                    if vec is None:
                        content = safe_read_clob(content_chunk)
                        if content:
                            try:
                                vec = list(get_embedding(content[:2000]))
                            except Exception:
                                vec = None

                    if not vec:
                        return None, None, None

                    label = title or "Düşük etkileşimli not"
                    logger.info(
                        f"[FLOW] Low-engagement anchor selected: id={content_id} "
                        f"seen={seen_count} ctx={ctx_count}"
                    )
                    return vec, label, str(content_id)
        except Exception as e:
            logger.warning(f"Low-engagement anchor selection failed: {e}")

        return None, None, None

    def _resolve_anchor(
        self, 
        anchor_type: str, 
        anchor_id: str, 
        firebase_uid: str,
        resource_type: Optional[str] = None,
        category: Optional[str] = None
    ) -> Tuple[Optional[List[float]], Optional[str], Optional[str]]:
        """
        Resolve an anchor to its embedding vector, label, and database ID.
        
        Returns: (vector, label, resolved_id)
        """
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    if anchor_type == "note":
                        # Fetch the note's content and existing vector
                        # Safety: Only use database ID if it's numeric
                        if not anchor_id.isdigit():
                            logger.warning(f"Skipping note anchor lookup for non-numeric ID: {anchor_id}")
                            return None, None, anchor_id
                        
                        cursor.execute("""
                            SELECT content_chunk, title, VEC_EMBEDDING, id
                            FROM TOMEHUB_CONTENT_V2
                            WHERE id = :p_id AND firebase_uid = :p_uid
                        """, {"p_id": int(anchor_id), "p_uid": firebase_uid})
                        row = cursor.fetchone()
                        if row:
                            content = safe_read_clob(row[0])
                            title = row[1]
                            resolved_id = str(row[3])
                            # Try to use stored embedding
                            vec = self._to_list(row[2])
                            if vec:
                                return vec, title, resolved_id
                            # Generate if not stored
                            vec = get_embedding(content[:2000])
                            return list(vec) if vec else None, title, resolved_id
                    
                    elif anchor_type == "book":
                        # Get representative chunk from book
                        cursor.execute("""
                            SELECT content_chunk, title, VEC_EMBEDDING, id
                            FROM TOMEHUB_CONTENT_V2
                            WHERE title = :p_title AND firebase_uid = :p_uid
                            AND (content_type = 'PDF' OR content_type = 'PDF_CHUNK' OR content_type = 'EPUB')
                            ORDER BY page_number
                            FETCH FIRST 1 ROW ONLY
                        """, {"p_title": anchor_id, "p_uid": firebase_uid})
                        row = cursor.fetchone()
                        if row:
                            content = safe_read_clob(row[0])
                            resolved_id = str(row[3])
                            vec = self._to_list(row[2])
                            if vec is None:
                                vec = list(get_embedding(content[:2000]))
                            return vec, anchor_id, resolved_id
                            
                    elif anchor_type == "topic":
                        # AUTO-BOOTSTRAP: General Discovery -> Use Interest Profile (Centroid) -> Low Engagement -> Random
                        if anchor_id == "General Discovery" or not anchor_id:
                            logger.info(f"*** DEBUG: Bootstrapping 'General Discovery' for UID: [{firebase_uid}] ***")
                            
                            # 1. User Interest Model (Zero Gravity Profile) - Average of top 10 recent notes/highlights
                            sql_centroid = """
                                SELECT VEC_EMBEDDING
                                FROM TOMEHUB_CONTENT_V2
                                WHERE firebase_uid = :p_uid
                                AND ai_eligible = 1
                                AND content_type IN ('HIGHLIGHT', 'INSIGHT', 'PERSONAL_NOTE')
                                AND VEC_EMBEDDING IS NOT NULL
                                ORDER BY id DESC
                                FETCH FIRST 10 ROWS ONLY
                            """
                            cursor.execute(sql_centroid, {"p_uid": firebase_uid})
                            recent_vectors = []
                            for row in cursor.fetchall():
                                vec = self._to_list(row[0])
                                if vec:
                                    recent_vectors.append(vec)
                                    
                            if len(recent_vectors) >= 3:
                                # Calculate centroid (average vector)
                                import numpy as np
                                centroid = np.mean(recent_vectors, axis=0)
                                norm = np.linalg.norm(centroid)
                                if norm > 0:
                                    centroid = centroid / norm
                                    logger.info(f"[FLOW] Zero Gravity Profile generated using {len(recent_vectors)} recent notes for UID {firebase_uid}")
                                    return centroid.tolist(), "Kişisel İlgi Profiliniz", "General Discovery"
                                    
                            # 2. Fallback to low engagement note anchor
                            vec, label, resolved_id = self._select_low_engagement_note_anchor(
                                firebase_uid=firebase_uid,
                                category=category
                            )
                            if vec:
                                return vec, label, resolved_id

                            # 3. Fallback to random content if no suitable note anchor
                            logger.info(f"Auto-bootstrapping fallback to random for UID: {firebase_uid}, Scope: {resource_type}")
                            
                            # Build dynamic bootstrap SQL
                            sql = """
                                SELECT id, title, VEC_EMBEDDING
                                FROM TOMEHUB_CONTENT_V2
                                WHERE LOWER(TRIM(firebase_uid)) = LOWER(TRIM(:p_uid))
                                AND ai_eligible = 1
                                AND VEC_EMBEDDING IS NOT NULL
                            """
                            params = {"p_uid": firebase_uid}
                            
                            sql, params = self._apply_resource_filter(sql, params, resource_type)
                            sql, params = self._apply_category_filter(sql, params, category)
                                
                            sql += " ORDER BY DBMS_RANDOM.VALUE FETCH FIRST 1 ROW ONLY "
                            cursor.execute(sql, params)
                            
                            recent_row = cursor.fetchone()
                            if recent_row:
                                # Found recent content! Use it as the anchor.
                                new_id, title, vec_data = recent_row
                                logger.info(f"Bootstrapped to recent: {title} ({new_id})")
                                
                                # Read vector properly using helper
                                vec = self._to_list(vec_data)
                                if vec:
                                    return vec, f"Devam ediyor: {title}", str(new_id)
                                else:
                                    logger.warning(f"Failed to read vector for bootstrapped item {new_id}")
                            
                            # If we reach here, bootstrap failed (no content or no valid vector)
                            # Strict Data Isolation Policy: Do not fallback to other users.
                            logger.info(f"UID {firebase_uid} has no content. Returning empty state.")

                            # Empty Library Case
                            logger.warning(f"Empty Library or vector-less items for UID: {firebase_uid}")
                            vec = get_query_embedding(anchor_id or "Knowledge Discovery")
                            return list(vec) if vec else None, "Waiting for Content...", anchor_id
                        
        
        except Exception as e:
            import traceback
            logger.error(f"Failed to resolve anchor: {e}\n{traceback.format_exc()}")
        
        return None, None, anchor_id
    
    # -------------------------------------------------------------------------
    # FEED SEEDING ARCHITECTURE (SEED-FIRST LOGIC)
    # -------------------------------------------------------------------------

    def _seed_candidates(
        self,
        firebase_uid: str,
        session_id: str,
        target_vector: Optional[List[float]],
        resource_type: Optional[str],
        category: Optional[str] = None,
        limit: int = 15
    ) -> List[FlowCard]:
        """
        Generate candidates using a Multi-Seed approach (Feed Logic).
        3 Pools:
        1. Gravity (Semantic match to anchor) - Only if target_vector exists
        2. Recency (New highlights/notes)
        3. Serendipity (Random quality chunks)
        """
        seeds = []
        
        # 1. Gravity Seed (if applicable)
        if target_vector:
            gravity_candidates = self._fetch_seed_gravity(
                firebase_uid, session_id, target_vector, resource_type, category, limit=5
            )
            seeds.extend(gravity_candidates)
            
        # 2. Recency Seed (Contextual Anchoring)
        recency_candidates = self._fetch_seed_recency(
            firebase_uid, session_id, resource_type, category, limit=5
        )
        seeds.extend(recency_candidates)
        
        # 3. Serendipity Seed (Discovery)
        # If we have very few gravity matches, boost serendipity
        needed = limit - len(seeds)
        if needed > 0:
            # Always fetch at least 5 random to ensure variety
            fetch_count = max(needed, 5) 
            serendipity_candidates = self._fetch_seed_serendipity(
                firebase_uid, session_id, resource_type, category, limit=fetch_count
            )
            seeds.extend(serendipity_candidates)
            
        return seeds

    def _fetch_seed_gravity(
        self, uid: str, sid: str, vec: List[float], r_type: Optional[str], category: Optional[str], limit: int
    ) -> List[FlowCard]:
        """Fetch semantically related items (Soft thresholds)."""
        # We reuse Zone 1/2 logic but with relaxed constraints
        # Effectively finding "Related" content
        # For simplicity, we blindly fetch nearest neighbors regardless of zone
        vec_array = array.array('f', vec)
        params = {"p_uid": uid, "p_vec": vec_array, "p_sid": sid, "p_limit": limit}
        
        sql = """
            SELECT id, content_chunk, title, content_type AS source_type, page_number,
                   VECTOR_DISTANCE(VEC_EMBEDDING, :p_vec, COSINE) as distance
            FROM TOMEHUB_CONTENT_V2
            WHERE firebase_uid = :p_uid
            AND VEC_EMBEDDING IS NOT NULL
            AND DBMS_LOB.GETLENGTH(content_chunk) > 12
            AND NOT EXISTS (SELECT 1 FROM TOMEHUB_FLOW_SEEN fs WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid)
        """
        if r_type == 'BOOK':
             # Books = PDFs + Highlights
             sql += " AND content_type IN ('PDF','EPUB','PDF_CHUNK','BOOK','HIGHLIGHT','INSIGHT') "
        elif r_type == 'PERSONAL_NOTE':
             sql += " AND content_type = 'PERSONAL_NOTE' "
        elif r_type in (None, 'ALL_NOTES', 'ALL'):
             # All Notes = Highlights/Insights ONLY
             sql += " AND content_type IN ('HIGHLIGHT','INSIGHT') "
        else:
             sql += " AND content_type = :p_type "
             params["p_type"] = r_type
             
        # Apply Category Filter
        sql, params = self._apply_category_filter(sql, params, category)
             
        sql += " ORDER BY distance ASC FETCH FIRST :p_limit ROWS ONLY "
        
        cards = []
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    raw_content = safe_read_clob(row[1])
                    content = extract_note_content(raw_content)
                    content = _prepare_flow_card_content(content, row[3])
                    sim = 1 - row[5]
                    
                    # Tag based on similarity (No drop!)
                    tag = "🎯 Precision" if sim > 0.6 else "🔗 Related" if sim > 0.3 else "🌊 Flow"
                    
                    cards.append(FlowCard(
                        flow_id=str(uuid.uuid4()),
                        chunk_id=str(row[0]),
                        content=content,
                        title=row[2] or "Untitled",
                        page_number=row[4],
                        source_type="pdf_chunk" if row[3] in ['PDF','PDF_CHUNK','EPUB'] else 'personal',
                        zone=1, # Treat as "Gravity" zone
                        epistemic_level="A",
                        reason=f"{tag} ({sim:.0%})"
                    ))
                    # Attach sim for ranking
                    cards[-1]._similarity = sim
        return cards

    def _fetch_seed_recency(self, uid: str, sid: str, r_type: Optional[str], category: Optional[str], limit: int) -> List[FlowCard]:
        """Fetch recently added content (Highlights/Notes)."""
        sql = """
            SELECT id, content_chunk, title, content_type AS source_type, page_number
            FROM TOMEHUB_CONTENT_V2
            WHERE firebase_uid = :p_uid
            AND DBMS_LOB.GETLENGTH(content_chunk) > 12
            AND NOT EXISTS (SELECT 1 FROM TOMEHUB_FLOW_SEEN fs WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid)
        """
        params = {"p_uid": uid, "p_sid": sid, "p_limit": limit}
        
        if r_type == 'BOOK':
             # Books = Highlights + PDFs
             sql += " AND content_type IN ('PDF','EPUB','PDF_CHUNK','BOOK','HIGHLIGHT','INSIGHT') "
        elif r_type == 'PERSONAL_NOTE':
             sql += " AND content_type = 'PERSONAL_NOTE' "
        elif r_type in (None, 'ALL_NOTES', 'ALL'):
             # All Notes = Highlights/Insights ONLY
             sql += " AND content_type IN ('HIGHLIGHT','INSIGHT') "
        elif r_type:
             sql += " AND content_type = :p_type "
             params["p_type"] = r_type

        # Apply Category Filter
        sql, params = self._apply_category_filter(sql, params, category)
             
        sql += " ORDER BY id DESC FETCH FIRST :p_limit ROWS ONLY "
        
        # Recency = Zone 2 (High priority but below strong semantic matches)
        return self._execute_simple_fetch(sql, params, "✨ Recent", zone=2)

    def _fetch_seed_serendipity(self, uid: str, sid: str, r_type: Optional[str], category: Optional[str], limit: int) -> List[FlowCard]:
        """Fetch random high-quality chunks."""
        sql = """
            SELECT id, content_chunk, title, content_type AS source_type, page_number
            FROM TOMEHUB_CONTENT_V2
            WHERE firebase_uid = :p_uid
            AND DBMS_LOB.GETLENGTH(content_chunk) > 12
            AND NOT EXISTS (SELECT 1 FROM TOMEHUB_FLOW_SEEN fs WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid)
        """
        params = {"p_uid": uid, "p_sid": sid, "p_limit": limit}

        if r_type == 'BOOK':
             # Books = Highlights + PDFs
             sql += " AND content_type IN ('PDF','EPUB','PDF_CHUNK','BOOK','HIGHLIGHT','INSIGHT') "
        elif r_type == 'PERSONAL_NOTE':
             sql += " AND content_type = 'PERSONAL_NOTE' "
        elif r_type in (None, 'ALL_NOTES', 'ALL'):
             # All Notes = Highlights/Insights ONLY
             sql += " AND content_type IN ('HIGHLIGHT','INSIGHT') "
        elif r_type:
             sql += " AND content_type = :p_type "
             params["p_type"] = r_type

        # Apply Category Filter
        sql, params = self._apply_category_filter(sql, params, category)

        sql += " ORDER BY DBMS_RANDOM.VALUE FETCH FIRST :p_limit ROWS ONLY "
        
        # Discovery = Zone 3 (Discovery / Low priority)
        return self._execute_simple_fetch(sql, params, "🎲 Serendipity", zone=3)

    def _execute_simple_fetch(self, sql: str, params: dict, reason_prefix: str, zone: int) -> List[FlowCard]:
         cards = []
         with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    raw_content = safe_read_clob(row[1])
                    content = extract_note_content(raw_content)
                    content = _prepare_flow_card_content(content, row[3])
                    cards.append(FlowCard(
                        flow_id=str(uuid.uuid4()),
                        chunk_id=str(row[0]),
                        content=content,
                        title=row[2] or "Untitled",
                        page_number=row[4],
                        source_type="pdf_chunk" if row[3] in ['PDF','PDF_CHUNK','EPUB'] else 'personal',
                        zone=zone, 
                        epistemic_level="B",
                        reason=reason_prefix
                    ))
                    # Zero similarity (pure diversity)
                    cards[-1]._similarity = 0.0
         return cards

    # -------------------------------------------------------------------------
    # INTERNAL: CANDIDATE GENERATION
    # -------------------------------------------------------------------------
    
    def _generate_batch(
        self,
        session_id: str,
        firebase_uid: str,
        batch_size: int = 5
    ) -> List[FlowCard]:
        """
        Generate a batch of cards using the Expanding Horizons algorithm.
        """
        state = self.session_manager.get_session(session_id)
        if not state:
            return []
        
        # SPECIAL CASE: Sparse Categories (Bypass Vector Flow)
        # If user selects Personal Notes, Websites, or Articles, just show what we have randomly.
        if state.resource_type in ['PERSONAL_NOTE', 'WEBSITE', 'ARTICLE']:
            return self._fetch_simple_random_by_type(
                firebase_uid, session_id, state.resource_type, batch_size, state.category
            )

        
        # Determine Flow Mode (Gravity vs Zero Gravity)
        target_vector = None
        is_zero_gravity = (state.global_anchor_id == "General Discovery") or (not state.global_anchor_id)
        
        if not is_zero_gravity:
             # Calculate target vector using Dual Anchor
             target_vector = self._calculate_target_vector(state)
        else:
             logger.info("[FLOW] Zero Gravity Mode (General Discovery) - Skipping vector bias")
        
        # 1. Fetch Candidates (Seed-First Architecture)
        all_candidates = self._seed_candidates(
            firebase_uid=firebase_uid,
            session_id=session_id,
            target_vector=target_vector,
            resource_type=state.resource_type,
            category=state.category,
            limit=batch_size * 3  # Fetch 3x to allow for filtering/ranking fallout
        )
        
        logger.info(f"[FLOW-METRICS] Funnel Start: {len(all_candidates)} candidates via Seeding.")
        
        # Source Distribution Analysis
        source_dist = {"highlights": 0, "pdf_chunks": 0}
        for c in all_candidates:
            if c.source_type == 'personal':
                source_dist["highlights"] += 1
            else:
                source_dist["pdf_chunks"] += 1
        logger.info(f"[FLOW-METRICS] Source Dist: {source_dist}")

        # Filter: Dedup, Seen, Negative feedback
        filtered = self._filter_candidates(all_candidates, state, session_id, target_vector)
        
        logger.info(f"[FLOW-METRICS] Funnel Filtered: {len(filtered)} candidates (Dropped {len(all_candidates) - len(filtered)})")

        # Fallback: if filtering is too strict, allow globally seen items (still avoid session duplicates)
        if len(filtered) < batch_size and all_candidates:
            fallback = self._filter_candidates(
                all_candidates,
                state,
                session_id,
                target_vector,
                allow_global_seen=True,
                skip_ids={card.chunk_id for card in filtered}
            )
            if fallback:
                logger.info(f"[FLOW] Relaxed filter added {len(fallback)} candidates after global-seen fallback.")
                filtered.extend(fallback)
        
        # Rank and select top N
        ranked = self._rank_candidates(filtered, target_vector)
        final_cards = ranked[:batch_size]
        
        logger.info(f"[FLOW-METRICS] Funnel Final: {len(final_cards)} cards returned")
        
        # Update session state
        for card in final_cards:
            self.session_manager.add_seen_chunk(session_id, card.chunk_id)
            self._record_seen_chunk(firebase_uid, session_id, card.chunk_id)
            # Update centroid if available (future)
        
        # Update local anchor to the last shown card
        if final_cards:
            state.local_anchor_id = final_cards[-1].chunk_id
            state.cards_shown += len(final_cards)
            self.session_manager.update_session(state)
        
        return final_cards

    
    def _calculate_target_vector(self, state: FlowSessionState) -> Optional[List[float]]:
        """
        Calculate the target vector using Dual Anchor gravity.
        
        V_target = α * V_global + (1-α) * V_local
        
        α is inversely proportional to horizon_value:
        - Low horizon (Focus): α ≈ 0.8 (Strong global gravity)
        - High horizon (Explore): α ≈ 0.3 (Weak global gravity)
        """
        if not state.global_anchor_vector:
            return None
        
        # Calculate alpha based on horizon value
        # horizon=0 -> alpha=0.9, horizon=1 -> alpha=0.3
        alpha = 0.9 - (state.horizon_value * 0.6)
        
        global_vec = np.array(state.global_anchor_vector)
        
        if state.local_anchor_vector:
            local_vec = np.array(state.local_anchor_vector)
            target = alpha * global_vec + (1 - alpha) * local_vec
            # Normalize
            target = target / np.linalg.norm(target)
            return target.tolist()
        
        return state.global_anchor_vector
    
    def _get_active_zones(self, horizon_value: float) -> List[int]:
        """
        Determine which zones are active based on horizon slider.
        
        Zone 1 is always active.
        Higher zones activate as horizon increases.
        """
        active = [1]  # Zone 1 always active
        
        if horizon_value >= 0.33:
            active.append(2)
        if horizon_value >= 0.66:
            active.append(3)
        
        return active
    
    def _fetch_zone_candidates(
        self,
        zone: int,
        target_vector: Optional[List[float]],
        state: FlowSessionState,
        firebase_uid: str,
        resource_type: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Fetch candidates from a specific zone.
        """
        limit = ZONE_FETCH_LIMITS.get(zone, 10)
        
        candidates = []
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    if zone == 1:
                        # ZONE 1: Tight Context (Same book, nearby pages)
                        candidates = self._fetch_zone1_tight_context(
                            cursor, state, firebase_uid, limit, resource_type, state.category
                        )
                    
                    elif zone == 2:
                        # ZONE 2: Author's Mind (Same author, graph 1-hop)
                        candidates = self._fetch_zone2_authors_mind(
                            cursor, state, firebase_uid, limit, resource_type, state.category
                        )
                    
                    elif zone == 3:
                        # ZONE 3: Syntopic Debate (Vector similarity to Global Anchor)
                        candidates = self._fetch_zone3_syntopic(
                            cursor, target_vector, firebase_uid, state.session_id, limit, resource_type, state.category
                        )
                    
                    elif zone == 4:
                        # ZONE 4: Discovery Bridge (Looser similarity, high centrality)
                        candidates = self._fetch_zone4_discovery(
                            cursor, target_vector, firebase_uid, state.session_id, limit, state.cards_shown, resource_type, state.category
                        )
        
        except Exception as e:
            logger.error(f"Zone {zone} fetch failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return candidates
        
        return candidates
    
    # -------------------------------------------------------------------------
    # PERSONAL NOTES SIMPLE FETCHER
    # -------------------------------------------------------------------------
    
    def _fetch_simple_random_by_type(
        self, firebase_uid: str, session_id: str, resource_type: str, batch_size: int, category: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Simple fetcher for Sparse Categories (Personal Notes, Websites, Articles).
        Bypasses vector search and returns random unseen content from that category.
        """
        cards = []
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT id, content_chunk, title, page_number, content_type AS source_type
                        FROM TOMEHUB_CONTENT_V2
                        WHERE firebase_uid = :p_uid
                    """
                    
                    params = {
                        "p_uid": firebase_uid,
                        "p_sid": session_id,
                        "p_limit": batch_size
                    }

                    # Category specific filters
                    if resource_type == 'PERSONAL_NOTE':
                         sql += " AND content_type = 'PERSONAL_NOTE' "
                    elif resource_type == 'WEBSITE':
                         sql += " AND content_type = 'WEBSITE' "
                    elif resource_type == 'ARTICLE':
                         sql += " AND content_type = 'ARTICLE' "
                    elif resource_type:
                         # Generic fallback
                         sql += " AND content_type = :p_type "
                         params["p_type"] = resource_type

                    # Apply Category Filter
                    sql, params = self._apply_category_filter(sql, params, category)
                    sql += """
                        AND NOT EXISTS (
                            SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                            WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
                        )
                        ORDER BY DBMS_RANDOM.VALUE
                        FETCH FIRST :p_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, params)
                    
                    for row in cursor.fetchall():
                        raw_content = safe_read_clob(row[1])
                        clean_content = extract_note_content(raw_content)
                        clean_content = _prepare_flow_card_content(clean_content, row[4])
                        
                        cards.append(FlowCard(
                            flow_id=str(uuid.uuid4()),
                            chunk_id=str(row[0]),
                            content=clean_content,
                            title=row[2] or "Untitled",
                            page_number=row[3], # Correct index for page_number if it is 4th col? No, row[3] is page_number in SELECT list
                            source_type="personal" if resource_type == 'PERSONAL_NOTE' else row[4].lower(),
                            zone=1,
                            epistemic_level="A",
                            reason=f"🎲 Random {resource_type.title().replace('_', ' ')}"
                        ))
        except Exception as e:
            logger.error(f"Simple fetch failed for {resource_type}: {e}")
        
        return cards
    
    # -------------------------------------------------------------------------
    # ZONE FETCHERS
    # -------------------------------------------------------------------------
    
    def _fetch_zone1_tight_context(
        self, cursor, state: FlowSessionState, firebase_uid: str, limit: int,
        resource_type: Optional[str] = None, category: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Zone 1: Fetch chunks from the same book, near the anchor's page.
        """
        # Safety check: Is the anchor ID a numeric database ID?
        # UUIDs and topic strings should skip database lookups
        is_numeric_id = state.global_anchor_id and state.global_anchor_id.isdigit()
        
        anchor_row = None
        if is_numeric_id:
            try:
                cursor.execute("""
                    SELECT title, page_number FROM TOMEHUB_CONTENT_V2
                    WHERE id = :p_id AND firebase_uid = :p_uid
                """, {"p_id": int(state.global_anchor_id), "p_uid": firebase_uid})
                anchor_row = cursor.fetchone()
            except (ValueError, oracledb.DatabaseError) as e:
                logger.warning(f"Failed to fetch anchor row for ID {state.global_anchor_id}: {e}")
                anchor_row = None
        if not anchor_row:
            # Fallback: If anchor ID isn't found (e.g., Topic Anchor), use strict vector search
            if state.global_anchor_vector:
                # Use loose threshold (0.40) to ensure content for Topic Anchors like "General Discovery"
                vec_array = array.array('f', state.global_anchor_vector)
                params = {
                    "p_uid": firebase_uid,
                    "p_vec": vec_array,
                    "p_limit": limit,
                    "p_sid": state.session_id
                }
                sql = """
                    SELECT id, content_chunk, title, content_type AS source_type, page_number,
                           VECTOR_DISTANCE(VEC_EMBEDDING, :p_vec, COSINE) as distance
                    FROM TOMEHUB_CONTENT_V2
                    WHERE firebase_uid = :p_uid
                    AND VEC_EMBEDDING IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                        WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
                    )
                """
                # Apply filters
                sql, params = self._apply_resource_filter(sql, params, resource_type)
                sql, params = self._apply_category_filter(sql, params, category)
                
                sql += " ORDER BY distance FETCH FIRST :p_limit ROWS ONLY "
                cursor.execute(sql, params)
                cards = []
                for row in cursor.fetchall():
                    distance = row[5]
                    similarity = 1 - distance if distance else 0
                    if similarity >= 0.35:
                         content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
                         cards.append(FlowCard(
                            flow_id=str(uuid.uuid4()),
                            chunk_id=str(row[0]),
                            content=content,
                            title=row[2] or "Untitled",
                            page_number=row[4],
                            source_type="personal" if row[3] in ('HIGHLIGHT','INSIGHT','PERSONAL_NOTE') else "pdf_chunk",
                            zone=1,
                            epistemic_level="B", # Contextual
                            reason=f"🎯 Konu Odaklı ({similarity:.0%})"
                        ))
                    else:
                        logger.debug(f"[FLOW] Skipping candidate with low similarity: {similarity:.2f}")
                return cards
            return []
        
        book_title, anchor_page = anchor_row
        anchor_page = anchor_page or 1
        
        # Fetch nearby chunks (within 10 pages)
        params = {
            "p_uid": firebase_uid,
            "p_book_title": book_title,
            "p_page": anchor_page,
            "p_anchor_id": state.global_anchor_id,
            "p_limit": limit,
            "p_sid": state.session_id
        }
        sql = """
            SELECT id, content_chunk, title, content_type AS source_type, page_number
            FROM TOMEHUB_CONTENT_V2
            WHERE firebase_uid = :p_uid
            AND title = :p_book_title
            AND ABS(NVL(page_number, 1) - :p_page) <= 10
        """
        # Only filter by anchor ID if it's actually a numeric database ID
        if state.global_anchor_id and state.global_anchor_id.isdigit():
            sql += " AND id != :p_anchor_id "
        
        sql += """
            AND NOT EXISTS (
                SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
            )
        """
        sql, params = self._apply_resource_filter(sql, params, resource_type)
        sql, params = self._apply_category_filter(sql, params, category)
            
        sql += " ORDER BY ABS(NVL(page_number, 1) - :p_page) FETCH FIRST :p_limit ROWS ONLY "
        cursor.execute(sql, params)
        
        cards = []
        for row in cursor.fetchall():
            content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
            cards.append(FlowCard(
                flow_id=str(uuid.uuid4()),
                chunk_id=str(row[0]),
                content=content,
                title=row[2] or "Untitled",
                page_number=row[4],
                source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                zone=1,
                epistemic_level="B", # Contextual
                reason=f"[Book] Page {row[4]}"
            ))
        
        return cards
    
    def _fetch_zone2_authors_mind(
        self, cursor, state: FlowSessionState, firebase_uid: str, limit: int,
        resource_type: Optional[str] = None, category: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Zone 2: Fetch from the same author or graph 1-hop neighbors.
        """
        # Get author of the anchor (parsed from title since AUTHOR column is missing)
        author = None
        is_numeric_id = state.global_anchor_id and state.global_anchor_id.isdigit()
        
        if is_numeric_id:
            try:
                cursor.execute("""
                    SELECT title FROM TOMEHUB_CONTENT_V2
                    WHERE id = :p_id AND firebase_uid = :p_uid
                """, {"p_id": int(state.global_anchor_id), "p_uid": firebase_uid})
            except (ValueError, oracledb.DatabaseError) as e:
                logger.warning(f"Failed to fetch author for anchor ID {state.global_anchor_id}: {e}")
                author = None
            
            anchor_row = cursor.fetchone()
            if anchor_row and " - " in anchor_row[0]:
                author = anchor_row[0].split(" - ")[-1].strip()
        
        cards = []
        
        if author:
            # Same author, different books (Query via TITLE suffix)
            params = {
                "p_uid": firebase_uid,
                "p_author_pattern": f"% - {author}",
                "p_anchor_id": state.global_anchor_id,
                "p_limit": limit,
                "p_sid": state.session_id
            }
            sql = """
                SELECT id, content_chunk, title, content_type AS source_type, page_number
                FROM TOMEHUB_CONTENT_V2
                WHERE firebase_uid = :p_uid
                AND title LIKE :p_author_pattern
            """
            # Only filter by anchor ID if it's actually a numeric database ID
            if state.global_anchor_id and state.global_anchor_id.isdigit():
                sql += " AND id != :p_anchor_id "
            
            sql += """
                AND NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                    WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
                )
            """

            sql, params = self._apply_resource_filter(sql, params, resource_type)
            sql, params = self._apply_category_filter(sql, params, category)
                
            sql += " ORDER BY DBMS_RANDOM.VALUE FETCH FIRST :p_limit ROWS ONLY "
            cursor.execute(sql, params)
            
            for row in cursor.fetchall():
                content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
                cards.append(FlowCard(
                    flow_id=str(uuid.uuid4()),
                    chunk_id=str(row[0]),
                    content=content,
                    title=row[2] or "Untitled",
                    author=author,
                    page_number=row[4],
                    source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                    zone=2,
                    epistemic_level="B", # Contextual
                    reason=f"[Author] {author}"
                ))
        elif state.global_anchor_vector:
             # Fallback: If no author (Topic Anchor), use broader vector search
             # Use loose threshold (0.40)
            vec_array = array.array('f', state.global_anchor_vector)
            offset = min(10, state.cards_shown)
            params = {
                "p_uid": firebase_uid,
                "p_vec": vec_array,
                "p_limit": limit,
                "p_sid": state.session_id,
                "p_offset": offset
            }
            sql = """
                SELECT id, content_chunk, title, content_type AS source_type, page_number,
                       VECTOR_DISTANCE(VEC_EMBEDDING, :p_vec, COSINE) as distance
                FROM TOMEHUB_CONTENT_V2
                WHERE firebase_uid = :p_uid
                AND VEC_EMBEDDING IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                    WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
                )
            """
            sql, params = self._apply_resource_filter(sql, params, resource_type)
            sql, params = self._apply_category_filter(sql, params, category)
                
            sql += " ORDER BY distance OFFSET :p_offset ROWS FETCH NEXT :p_limit ROWS ONLY "
            cursor.execute(sql, params)
            
            for row in cursor.fetchall():
                distance = row[5]
                similarity = 1 - distance if distance else 0
                if similarity >= 0.40:
                    content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
                    cards.append(FlowCard(
                        flow_id=str(uuid.uuid4()),
                        chunk_id=str(row[0]),
                        content=content,
                        title=row[2] or "Untitled",
                        page_number=row[4],
                        source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                        zone=2,
                        epistemic_level="B", # Broad Context
                        reason=f"[Concept] Context ({similarity:.0%})"
                    ))
        
        return cards
    
    def _fetch_zone3_syntopic(
        self, cursor, target_vector: Optional[List[float]], firebase_uid: str, session_id: str, limit: int,
        resource_type: Optional[str] = None, category: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Zone 3: Vector similarity search (Syntopic Debate).
        """
        if not target_vector:
            return []
        
        # Convert to array for Oracle
        vec_array = array.array('f', target_vector)
        
        params = {
            "p_uid": firebase_uid,
            "p_vec": vec_array,
            "p_limit": limit,
            "p_sid": session_id
        }
        sql = """
            SELECT id, content_chunk, title, content_type AS source_type, page_number,
                   VECTOR_DISTANCE(VEC_EMBEDDING, :p_vec, COSINE) as distance
            FROM TOMEHUB_CONTENT_V2
            WHERE firebase_uid = :p_uid
            AND VEC_EMBEDDING IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
            )
        """
        sql, params = self._apply_resource_filter(sql, params, resource_type)
        sql, params = self._apply_category_filter(sql, params, category)
            
        sql += " ORDER BY distance FETCH FIRST :p_limit ROWS ONLY "
        cursor.execute(sql, params)
        
        cards = []
        for row in cursor.fetchall():
            distance = row[5]
            similarity = 1 - distance if distance else 0
            
            if similarity < SIMILARITY_THRESHOLDS["syntopic"]:
                continue
            
            content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
            cards.append(FlowCard(
                flow_id=str(uuid.uuid4()),
                chunk_id=str(row[0]),
                content=content,
                title=row[2] or "Untitled",
                page_number=row[4],
                source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                zone=3,
                epistemic_level="B", # Dialectical
                reason=f"🔗 Anlamsal Bağlantı ({similarity:.0%})"
            ))
        
        return cards
    
    def _fetch_zone4_discovery(
        self, cursor, target_vector: Optional[List[float]], firebase_uid: str, session_id: str, limit: int,
        cards_shown: int = 0,
        resource_type: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[FlowCard]:
        """
        Zone 4: Discovery Bridge (prioritize high-centrality bridge nodes).
        
        Uses precomputed centrality_score from TOMEHUB_CONCEPTS (via calculate_graph_stats.py).
        Falls back to looser vector similarity if graph data unavailable.
        """
        cards = []
        
        # Strategy 1: Try to find chunks linked to high-centrality concepts
        try:
            params = {"p_uid": firebase_uid, "p_limit": limit}
            
            sql = """
                SELECT DISTINCT
                    ct.id, ct.content_chunk, ct.title, ct.content_type AS source_type, ct.page_number,
                    c.name as concept_name, c.centrality_score
                FROM TOMEHUB_CONCEPTS c
                JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c.id = cc.concept_id
                JOIN TOMEHUB_CONTENT_V2 ct ON cc.content_id = ct.id
                WHERE ct.firebase_uid = :p_uid
                AND ct.ai_eligible = 1
                AND c.centrality_score > 0.01
            """
            
            if resource_type == 'PERSONAL_NOTE':
                sql += " AND ct.content_type = 'PERSONAL_NOTE' "
            elif resource_type == 'ALL_NOTES':
                sql += " AND ct.content_type IN ('HIGHLIGHT', 'INSIGHT') "
            elif resource_type == 'BOOK':
                sql += " AND ct.content_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT') "
            elif resource_type in ('ARTICLE', 'WEBSITE'):
                sql += " AND ct.content_type = :p_type "
                params["p_type"] = resource_type
            
            sql, params = self._apply_category_filter(sql, params, category)
                
            sql += " ORDER BY c.centrality_score DESC, DBMS_RANDOM.VALUE FETCH FIRST :p_limit ROWS ONLY "
            cursor.execute(sql, params)
            
            for row in cursor.fetchall():
                content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
                concept_name = row[5]
                centrality = row[6] or 0
                
                cards.append(FlowCard(
                    flow_id=str(uuid.uuid4()),
                    chunk_id=str(row[0]),
                    content=content,
                    title=row[2] or "Untitled",
                    page_number=row[4],
                    source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                    zone=4,
                    epistemic_level="A", # Foundational
                    reason=f"💎 Temel Kavram: {concept_name} (merkezilik: {centrality:.2f})"
                ))
                
        except Exception as e:
            logger.warning(f"Graph bridge query failed, falling back to vector: {e}")
        
        # Strategy 2: Fallback to loose vector similarity if graph didn't yield enough
        if len(cards) < limit and target_vector:
            remaining = limit - len(cards)
            vec_array = array.array('f', target_vector)
            
            offset = min(20, cards_shown)
            params = {
                "p_uid": firebase_uid,
                "p_vec": vec_array,
                "p_limit": remaining,
                "p_sid": session_id,
                "p_offset": offset
            }
            sql = """
                SELECT id, content_chunk, title, content_type AS source_type, page_number,
                       VECTOR_DISTANCE(VEC_EMBEDDING, :p_vec, COSINE) as distance
                FROM TOMEHUB_CONTENT_V2
                WHERE firebase_uid = :p_uid
                AND VEC_EMBEDDING IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_FLOW_SEEN fs 
                    WHERE fs.chunk_id = TOMEHUB_CONTENT_V2.id AND TO_CHAR(fs.session_id) = :p_sid
                )
            """
            sql, params = self._apply_resource_filter(sql, params, resource_type)
            sql, params = self._apply_category_filter(sql, params, category)
                
            sql += " ORDER BY distance OFFSET :p_offset ROWS FETCH NEXT :p_limit ROWS ONLY "
            cursor.execute(sql, params)
            
            for row in cursor.fetchall():
                distance = row[5]
                similarity = 1 - distance if distance else 0
                
                if similarity < SIMILARITY_THRESHOLDS["discovery"]:
                    continue
                
                content = _prepare_flow_card_content(safe_read_clob(row[1]), row[3])
                cards.append(FlowCard(
                    flow_id=str(uuid.uuid4()),
                    chunk_id=str(row[0]),
                    content=content,
                    title=row[2] or "Untitled",
                    page_number=row[4],
                    source_type="pdf_chunk" if row[3] in ["PDF", "PDF_CHUNK", "EPUB"] else "personal",
                    zone=4,
                    epistemic_level="B", # Discovery
                    reason=f"Expanding Horizon ({similarity:.0%})"
                ))
        
        return cards

    
    # -------------------------------------------------------------------------
    # FILTERING & RANKING
    # -------------------------------------------------------------------------
    
    def _filter_candidates(
        self, 
        candidates: List[FlowCard], 
        state: FlowSessionState,
        session_id: str,
        target_vector: Optional[List[float]] = None,
        allow_global_seen: bool = False,
        skip_ids: Optional[Set[str]] = None
    ) -> List[FlowCard]:
        """
        Filter candidates:
        1. Remove already seen chunks (ID-based)
        2. Apply semantic deduplication (Centroid + Buffer check)
        3. Apply negative feedback penalty
        """
        filtered = []
        
        # BATCH OPTIMIZATION:
        # Fetch metadata (Global Seen + Vectors) for ALL candidates in one go
        chunk_ids = [c.chunk_id for c in candidates]
        metadata = self._get_candidate_metadata_batch(state.firebase_uid, chunk_ids, days=30)
        
        skip_ids = skip_ids or set()
        for card in candidates:
            if card.chunk_id in skip_ids:
                continue
            # Check 1: Already shown in THIS session (Absolute exclusion)
            if self.session_manager.is_chunk_seen(session_id, card.chunk_id):
                continue
            
            # Check 1b: Globally seen recently (Batch Checked)
            # Use metadata cache
            meta = metadata.get(card.chunk_id)
            if not meta:
                # Should not happen given logic, but safe fallback
                continue
                
            if meta['is_seen'] and not allow_global_seen:
                # Applying logic for discovery jumps vs normal flow
                local_anchor_id = state.local_anchor_id or ""
                # If discovery jump, we might be strict, else soft?
                # For now, respecting the global seen flag
                logger.debug(f"Skipping globally seen chunk: {card.chunk_id}")
                continue
            
            # Check 2: Semantic deduplication
            card_vector = meta['vector']
            
            if card_vector:
                if target_vector:
                    card._similarity = self._cosine_similarity(card_vector, target_vector)
                
                # Check if semantically duplicate
                if self.session_manager.is_semantically_duplicate(
                    session_id, card_vector, threshold=0.85
                ):
                    logger.debug(f"Skipping semantically duplicate chunk: {card.chunk_id}")
                    continue
                
                # Check 3: Negative feedback penalty
                penalty = self.session_manager.calculate_negative_penalty(
                    session_id, card_vector, penalty_threshold=0.80
                )
                
                if penalty < 0.3:
                    # Too similar to disliked content - skip entirely
                    logger.debug(f"Skipping negatively penalized chunk: {card.chunk_id}")
                    continue
                
                # Store penalty for ranking
                card._penalty = penalty
            
            filtered.append(card)
        
        return filtered

    def _get_candidate_metadata_batch(self, firebase_uid: str, chunk_ids: list[str], days: int = 30) -> dict[str, dict]:
        """
        Fetch vector and seen status for a batch of chunk IDs in a SINGLE query.
        Returns: {chunk_id: {'vector': [...], 'is_seen': bool}}
        """
        if not chunk_ids:
            return {}
            
        result = {}
        # Initialize defaults
        for cid in chunk_ids:
            result[cid] = {'vector': None, 'is_seen': False}

        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    # Create bind variables for IN clause (safely)
                    # Oracle supports standard IN with list?
                    # Python DPAPI usually requires generating :1, :2...
                    
                    # Split into chunks of 1000 if needed, but for now assuming <1000 candidates
                    if len(chunk_ids) > 950:
                        chunk_ids = chunk_ids[:950]
                        
                    bind_names = [f":id{i}" for i in range(len(chunk_ids))]
                    bind_dict = {f"id{i}": cid for i, cid in enumerate(chunk_ids)}
                    bind_dict["p_uid"] = firebase_uid
                    bind_dict["p_days"] = days
                    
                    # Combined query: Get Vector + Check if Seen
                    # Using LEFT JOIN on SEEN table
                    sql = f"""
                        SELECT c.id, c.VEC_EMBEDDING,
                               CASE WHEN s.chunk_id IS NOT NULL THEN 1 ELSE 0 END as is_seen
                        FROM TOMEHUB_CONTENT_V2 c
                        LEFT JOIN TOMEHUB_FLOW_SEEN s 
                               ON c.id = s.chunk_id 
                               AND s.firebase_uid = :p_uid 
                               AND s.seen_at > SYSTIMESTAMP - :p_days
                        WHERE c.id IN ({','.join(bind_names)})
                    """
                    
                    cursor.execute(sql, bind_dict)
                    
                    for row in cursor.fetchall():
                        cid = str(row[0])
                        vec = self._to_list(row[1])
                        is_seen = bool(row[2])
                        result[cid] = {'vector': vec, 'is_seen': is_seen}
                        
        except Exception as e:
            logger.error(f"Batch metadata fetch failed: {e}")
            # Fallback: don't crash, return defaults (potentially allowing dupes/missing vectors but keeping system alive)
            
        return result

    def _coerce_chunk_id(self, chunk_id: str) -> Optional[int]:
        """Coerce chunk_id to int for DB operations; return None if invalid."""
        if chunk_id is None:
            return None
        if isinstance(chunk_id, (int, np.integer)):
            return int(chunk_id)
        chunk_str = str(chunk_id).strip()
        if not chunk_str.isdigit():
            return None
        return int(chunk_str)
    
    def _coerce_session_id(self, session_id: str) -> Optional[int]:
        """Coerce session_id to int for DB operations; return None if invalid."""
        if session_id is None:
            return None
        if isinstance(session_id, (int, np.integer)):
            return int(session_id)
        sid_str = str(session_id).strip()
        if not sid_str.isdigit():
            return None
        return int(sid_str)
    
    def _record_seen_chunk(self, firebase_uid: str, session_id: str, chunk_id: str,
                           reaction_type: Optional[str] = None, discovered_via: Optional[str] = None):
        """Persist seen chunk to Database for cross-session global history, decay, and engagement tracking."""
        try:
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    sid_int = self._coerce_session_id(session_id)
                    if sid_int is None:
                        logger.debug(f"Skipping seen record insert for non-numeric session_id: {session_id}")
                        return
                    coerced_id = self._coerce_chunk_id(chunk_id)
                    if coerced_id is None:
                        logger.debug(f"Skipping non-numeric chunk_id for seen record: {chunk_id}")
                        return
                    cursor.execute("""
                        INSERT INTO TOMEHUB_FLOW_SEEN (firebase_uid, session_id, chunk_id, seen_at, reaction_type, discovered_via)
                        VALUES (:p_uid, :p_sid, :p_cid, CURRENT_TIMESTAMP, :p_reaction, :p_via)
                    """, {
                        "p_uid": firebase_uid, "p_sid": sid_int, "p_cid": coerced_id,
                        "p_reaction": reaction_type, "p_via": discovered_via
                    })
                    conn.commit()
        except Exception as e:
            logger.debug(f"DB seen recording failed (likely missing columns/table): {e}")

    def _is_globally_seen(self, firebase_uid: str, chunk_id: str, days: int = 30) -> bool:
        """Check if chunk was seen by this user globally within X days (Decay)."""
        try:
            coerced_id = self._coerce_chunk_id(chunk_id)
            if coerced_id is None:
                return False
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    # Note: Oracle date subtraction 'TIMESTAMP - NUMBER' results in days
                    cursor.execute("""
                        SELECT count(*) FROM TOMEHUB_FLOW_SEEN
                        WHERE firebase_uid = :p_uid AND chunk_id = :p_cid
                        AND seen_at > CURRENT_TIMESTAMP - :p_days
                    """, {"p_uid": firebase_uid, "p_cid": coerced_id, "p_days": days})
                    return cursor.fetchone()[0] > 0
        except Exception:
            return False

    def _prune_old_seen_records(self, firebase_uid: str, days: int = 45):
        """
        Lightweight cleanup to prevent TOMEHUB_FLOW_SEEN from bloating.
        Deletes records older than given days. Defaults to 45 days.
        """
        try:
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    # Oracle TIMESTAMP math
                    cursor.execute("""
                        DELETE FROM TOMEHUB_FLOW_SEEN
                        WHERE firebase_uid = :p_uid
                        AND seen_at < CURRENT_TIMESTAMP - :p_days
                    """, {"p_uid": firebase_uid, "p_days": days})
                    deleted = cursor.rowcount
                    conn.commit()
                    if deleted > 0:
                        logger.info(f"[FLOW-PRUNE] Cleaned up {deleted} old seen records for UID: {firebase_uid}")
        except Exception as e:
            logger.warning(f"Failed to prune old seen records: {e}")

    def _get_chunk_vector(self, chunk_id: str) -> Optional[List[float]]:
        """
        Retrieve the embedding vector for a chunk from the database.
        """
        try:
            coerced_id = self._coerce_chunk_id(chunk_id)
            if coerced_id is None:
                return None
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT VEC_EMBEDDING FROM TOMEHUB_CONTENT_V2 WHERE id = :p_id
                    """, {"p_id": coerced_id})
                    
                    row = cursor.fetchone()
                    if row and row[0]:
                        return self._to_list(row[0])
        except Exception as e:
            logger.warning(f"Failed to get vector for chunk {chunk_id}: {e}")
        
        return None
    
    def handle_feedback(
        self,
        session_id: str,
        chunk_id: str,
        action: str,
        firebase_uid: str
    ) -> bool:
        """
        Handle user feedback on a card.
        
        Actions:
        - 'like': Add to positive signals (future use)
        - 'dislike': Add vector to negative buffer
        - 'skip': Mild negative signal
        - 'save': Strong positive signal (future use)
        """
        state = self.session_manager.get_session(session_id)
        if not state:
            return False
        
        if action in ('dislike', 'skip'):
            # Get the chunk's vector
            chunk_vector = self._get_chunk_vector(chunk_id)
            
            if chunk_vector:
                # Add to negative buffer
                self.session_manager.add_negative_vector(session_id, chunk_vector)
                logger.info(f"Added negative signal for chunk {chunk_id}")
                return True
        
        elif action == 'like':
            # Update the local anchor to this card (user engaged with it)
            chunk_vector = self._get_chunk_vector(chunk_id)
            if chunk_vector:
                state.local_anchor_id = chunk_id
                state.local_anchor_vector = chunk_vector
                self.session_manager.update_session(state)
                
                # Add to recent vectors for dedup tracking
                self.session_manager.add_recent_vector(session_id, chunk_vector)
                
                # Update session centroid
                self.session_manager.update_session_centroid(session_id, chunk_vector)
                logger.info(f"Updated session anchors from liked chunk {chunk_id}")
                return True
        
        return False
    
    def _rank_candidates(
        self,
        candidates: List[FlowCard],
        target_vector: Optional[List[float]]
    ) -> List[FlowCard]:
        """
        Rank candidates by zone priority and relevance.
        
        Lower zones have higher priority (Zone 1 > Zone 2 > Zone 3 > Zone 4).
        Within same zone, use similarity + penalty, then shuffle for variety.
        """
        import random
        
        import random
        
        zone_weight = {1: 0.45, 2: 0.35, 3: 0.20}
        # RANKING WEIGHTS CONFIG
        WEIGHT_ZONE = 1.0        # Base weight for zone priority
        WEIGHT_SIMILARITY = 0.8  # Importance of semantic match
        WEIGHT_PENALTY = 1.5     # Importance of negative feedback (Multiplier space)

        def score(card: FlowCard) -> float:
            similarity = getattr(card, "_similarity", None)
            if similarity is None:
                similarity = 0.0
                
            penalty = getattr(card, "_penalty", 1.0) # 1.0 = No penalty, 0.0 = Full penalty
            
            # Formula: (ZoneBase + (Sim * Weight)) * Penalty
            base = zone_weight.get(card.zone, 0.1) * WEIGHT_ZONE
            sim_score = similarity * WEIGHT_SIMILARITY
            
            return (base + sim_score) * penalty

        # Group by zone
        by_zone = {1: [], 2: [], 3: []}
        for card in candidates:
            by_zone.get(card.zone, []).append(card)

        # Sort by similarity/penalty within each zone, keep light shuffle for variety
        for zone in list(by_zone.keys()):
            random.shuffle(by_zone[zone])
            by_zone[zone].sort(key=score, reverse=True)

        # Interleave: Take from each zone in round-robin
        result = []
        max_len = max(len(cards) for cards in by_zone.values()) if by_zone else 0

        for i in range(max_len):
            for zone in sorted(by_zone.keys()):
                if i < len(by_zone[zone]):
                    result.append(by_zone[zone][i])

        return result


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_flow_service: Optional[FlowService] = None


def get_flow_service() -> FlowService:
    """Get or create the global FlowService instance."""
    global _flow_service
    if _flow_service is None:
        _flow_service = FlowService()
    return _flow_service
