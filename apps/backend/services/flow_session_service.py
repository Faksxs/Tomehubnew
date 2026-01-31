# -*- coding: utf-8 -*-
"""
Layer 4: Flow Session Service (Redis State Manager)
====================================================
Manages the ephemeral state for Knowledge Stream sessions.
Uses the existing L2Cache (Redis) infrastructure from cache_service.py.
Fallbacks to in-memory dictionary if Redis is unavailable.
"""

import json
import hashlib
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Set, Dict, Any
import numpy as np

from services.cache_service import L2Cache
from models.flow_models import FlowSessionState, FlowMode
from config import settings

logger = logging.getLogger(__name__)

# Constants
SESSION_TTL = 3600 * 2  # 2 hours
RECENT_BUFFER_SIZE = 50
NEGATIVE_BUFFER_SIZE = 20


class FlowSessionManager:
    """
    Manages Flow session state in Redis or In-Memory (Fallback).
    
    Keys (Redis):
    - flow:session:{sid}:state     -> JSON of FlowSessionState
    - flow:session:{sid}:seen      -> Set of seen chunk_ids
    - flow:session:{sid}:recent    -> List of recent vectors (JSON encoded)
    - flow:session:{sid}:negative  -> List of negative vectors (JSON encoded)
    - flow:session:{sid}:queue     -> List of prefetched chunk_ids
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize with Redis connection or fallback to memory."""
        self.l2 = L2Cache(redis_url=redis_url or settings.REDIS_URL)
        self.use_redis = self.l2.is_available()
        
        # In-memory storage (fallback)
        self._local_storage: Dict[str, Any] = {}
        
        if not self.use_redis:
            logger.warning("Redis not available. Flow sessions will use in-memory storage (non-persistent across restarts).")
        else:
            logger.info("FlowSessionManager using Redis.")
    
    def _key(self, session_id: str, suffix: str) -> str:
        """Generate Redis key."""
        return f"flow:session:{session_id}:{suffix}"
    
    # --- Session Lifecycle ---
    
    def create_session(
        self,
        firebase_uid: str,
        anchor_id: str,
        anchor_vector: Optional[List[float]] = None,
        horizon_value: float = 0.25,
        mode: FlowMode = FlowMode.FOCUS,
        resource_type: Optional[str] = None
    ) -> FlowSessionState:
        """Create a new Flow session."""
        session_id = str(uuid.uuid4())
        
        state = FlowSessionState(
            session_id=session_id,
            firebase_uid=firebase_uid,
            global_anchor_id=anchor_id,
            global_anchor_vector=anchor_vector,
            local_anchor_id=anchor_id,
            local_anchor_vector=anchor_vector,
            session_centroid=anchor_vector,  # Initialize centroid with anchor
            horizon_value=horizon_value,
            mode=mode,
            resource_type=resource_type,
            cards_shown=0,
            created_at=datetime.utcnow().isoformat()
        )
        
        if self.use_redis:
            self.l2.set(self._key(session_id, "state"), state.model_dump(), SESSION_TTL)
        else:
            # Local fallback
            self._local_storage[self._key(session_id, "state")] = state.model_dump()
            # Initialize other collections
            self._local_storage[self._key(session_id, "seen")] = set()
            self._local_storage[self._key(session_id, "recent")] = []
            self._local_storage[self._key(session_id, "negative")] = []
            self._local_storage[self._key(session_id, "queue")] = []
            
        logger.info(f"Created Flow session: {session_id} (Redis: {self.use_redis})")
        return state
    
    def get_session(self, session_id: str) -> Optional[FlowSessionState]:
        """Retrieve session state."""
        key = self._key(session_id, "state")
        
        data = None
        if self.use_redis:
            data = self.l2.get(key)
        
        # Fallback check (or primary if redis disabled)
        if data is None and key in self._local_storage:
             data = self._local_storage[key]
             
        if data:
            return FlowSessionState(**data)
        return None
    
    def update_session(self, state: FlowSessionState):
        """Update session state."""
        key = self._key(state.session_id, "state")
        data = state.model_dump()
        
        if self.use_redis:
            self.l2.set(key, data, SESSION_TTL)
        
        # Always update local if it exists there (consistency)
        if not self.use_redis or key in self._local_storage:
            self._local_storage[key] = data
    
    def update_session_anchor(self, session_id: str, anchor_id: str, anchor_vector: Optional[List[float]]):
        """Update the anchor point of a session."""
        state = self.get_session(session_id)
        if not state:
            return
        
        state.global_anchor_id = anchor_id
        state.global_anchor_vector = anchor_vector
        state.local_anchor_id = anchor_id
        state.local_anchor_vector = anchor_vector
        
        # For a responsible pivot, reset the centroid to the new anchor
        if anchor_vector:
            state.session_centroid = anchor_vector
            
        self.update_session(state)

    def delete_session(self, session_id: str):
        """Delete a session and all its data."""
        if self.use_redis:
            self.l2.delete_pattern(f"flow:session:{session_id}:*")
        
        # Clear local
        prefix = f"flow:session:{session_id}:"
        keys_to_remove = [k for k in self._local_storage.keys() if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._local_storage[k]
            
        logger.info(f"Deleted Flow session: {session_id}")
    
    # --- Seen Chunks (Deduplication) ---
    
    def add_seen_chunk(self, session_id: str, chunk_id: str):
        """Mark a chunk as seen in this session."""
        key = self._key(session_id, "seen")
        
        if self.use_redis and self.l2.redis:
            try:
                self.l2.redis.sadd(key, chunk_id)
                self.l2.redis.expire(key, SESSION_TTL)
            except Exception as e:
                logger.error(f"Redis error (seen): {e}")
        else:
            if key not in self._local_storage:
                self._local_storage[key] = set()
            self._local_storage[key].add(chunk_id)
    
    def is_chunk_seen(self, session_id: str, chunk_id: str) -> bool:
        """Check if a chunk was already shown."""
        key = self._key(session_id, "seen")
        
        if self.use_redis and self.l2.redis:
            try:
                return self.l2.redis.sismember(key, chunk_id)
            except Exception as e:
                logger.error(f"Redis error (is_seen): {e}")
                return False
        else:
            return chunk_id in self._local_storage.get(key, set())
    
    def get_seen_count(self, session_id: str) -> int:
        """Get count of seen chunks."""
        key = self._key(session_id, "seen")
        if self.use_redis and self.l2.redis:
            try:
                return self.l2.redis.scard(key)
            except Exception:
                return 0
        else:
            return len(self._local_storage.get(key, set()))
    
    # --- Semantic Deduplication (Vector Buffer) ---
    
    def add_recent_vector(self, session_id: str, vector: List[float]):
        """Add a vector to the recent buffer (FIFO, max RECENT_BUFFER_SIZE)."""
        key = self._key(session_id, "recent")
        
        if self.use_redis and self.l2.redis:
            try:
                vec_json = json.dumps(vector)
                self.l2.redis.lpush(key, vec_json)
                self.l2.redis.ltrim(key, 0, RECENT_BUFFER_SIZE - 1)
                self.l2.redis.expire(key, SESSION_TTL)
            except Exception as e:
                logger.error(f"Redis error (recent): {e}")
        else:
            if key not in self._local_storage:
                self._local_storage[key] = []
            self._local_storage[key].insert(0, vector)
            if len(self._local_storage[key]) > RECENT_BUFFER_SIZE:
                 self._local_storage[key].pop()
    
    def get_recent_vectors(self, session_id: str) -> List[List[float]]:
        """Get all recent vectors."""
        key = self._key(session_id, "recent")
        if self.use_redis and self.l2.redis:
            try:
                raw_list = self.l2.redis.lrange(key, 0, -1)
                return [json.loads(v) for v in raw_list]
            except Exception as e:
                return []
        else:
            return self._local_storage.get(key, [])
    
    def is_semantically_duplicate(
        self,
        session_id: str,
        candidate_vector: List[float],
        threshold: float = 0.85
    ) -> bool:
        """Check for semantic duplicates."""
        if not candidate_vector:
            return False
        
        state = self.get_session(session_id)
        if not state or not state.session_centroid:
            return False
            
        # Step 1: Quick check against session centroid
        # If available (Redis or Local)
        centroid_sim = self._cosine_similarity(candidate_vector, state.session_centroid)
        if centroid_sim < 0.80:
            return False
        
        # Step 2: Granular check
        recent_vectors = self.get_recent_vectors(session_id)
        for rv in recent_vectors:
            sim = self._cosine_similarity(candidate_vector, rv)
            if sim > threshold:
                return True
        return False
    
    def update_session_centroid(self, session_id: str, new_vector: List[float]):
        """Update session centroid."""
        state = self.get_session(session_id)
        if not state:
            return
        
        if state.session_centroid is None:
            state.session_centroid = new_vector
        else:
            n = state.cards_shown + 1
            old_centroid = np.array(state.session_centroid)
            new_vec = np.array(new_vector)
            updated = old_centroid + (new_vec - old_centroid) / n
            state.session_centroid = updated.tolist()
        
        self.update_session(state)
    
    # --- Negative Feedback ---
    
    def add_negative_vector(self, session_id: str, vector: List[float]):
        """Add a disliked vector to the negative buffer."""
        key = self._key(session_id, "negative")
        
        if self.use_redis and self.l2.redis:
            try:
                vec_json = json.dumps(vector)
                self.l2.redis.lpush(key, vec_json)
                self.l2.redis.ltrim(key, 0, NEGATIVE_BUFFER_SIZE - 1)
                self.l2.redis.expire(key, SESSION_TTL)
            except Exception:
                pass
        else:
            if key not in self._local_storage:
                 self._local_storage[key] = []
            self._local_storage[key].insert(0, vector)
            if len(self._local_storage[key]) > NEGATIVE_BUFFER_SIZE:
                self._local_storage[key].pop()
    
    def calculate_negative_penalty(
        self,
        session_id: str,
        candidate_vector: List[float],
        penalty_threshold: float = 0.80
    ) -> float:
        """Calculate negative penalty."""
        if not candidate_vector:
            return 1.0
        
        negative_vectors = []
        key = self._key(session_id, "negative")
        
        if self.use_redis and self.l2.redis:
            try:
                raw_list = self.l2.redis.lrange(key, 0, -1)
                negative_vectors = [json.loads(v) for v in raw_list]
            except Exception:
                negative_vectors = []
        else:
             negative_vectors = self._local_storage.get(key, [])
             
        if not negative_vectors:
            return 1.0
            
        max_sim = 0.0
        for nv in negative_vectors:
            sim = self._cosine_similarity(candidate_vector, nv)
            if sim > max_sim:
                max_sim = sim
                
        if max_sim > penalty_threshold:
            penalty = 1.0 - (max_sim - penalty_threshold) / (1.0 - penalty_threshold)
            return max(0.0, penalty)
            
        return 1.0
    
    # --- Prefetch Queue ---
    
    def enqueue_prefetch(self, session_id: str, chunk_ids: List[str]):
        """Add to prefetch queue."""
        key = self._key(session_id, "queue")
        if self.use_redis and self.l2.redis:
            try:
                for cid in chunk_ids:
                    self.l2.redis.rpush(key, cid)
                self.l2.redis.expire(key, SESSION_TTL)
            except Exception:
                pass
        else:
            if key not in self._local_storage:
                self._local_storage[key] = []
            self._local_storage[key].extend(chunk_ids)

    def dequeue_prefetch(self, session_id: str, count: int) -> List[str]:
        """Get from prefetch queue."""
        key = self._key(session_id, "queue")
        if self.use_redis and self.l2.redis:
            try:
                result = []
                for _ in range(count):
                    cid = self.l2.redis.lpop(key)
                    if cid:
                        result.append(cid.decode() if isinstance(cid, bytes) else cid)
                    else:
                        break
                return result
            except Exception:
                return []
        else:
             queue = self._local_storage.get(key, [])
             result = queue[:count]
             self._local_storage[key] = queue[count:]
             return result

    def get_prefetch_count(self, session_id: str) -> int:
         """Get size of prefetch queue."""
         key = self._key(session_id, "queue")
         if self.use_redis and self.l2.redis:
             try:
                 return self.l2.redis.llen(key)
             except Exception:
                 return 0
         else:
             return len(self._local_storage.get(key, []))
             
    # --- Utilities ---
    
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


# Global instance
_flow_session_manager: Optional[FlowSessionManager] = None

def get_flow_session_manager() -> FlowSessionManager:
    """Get singleton instance."""
    global _flow_session_manager
    if _flow_session_manager is None:
        _flow_session_manager = FlowSessionManager()
    return _flow_session_manager

def init_flow_session_manager(redis_url: Optional[str] = None) -> FlowSessionManager:
    global _flow_session_manager
    _flow_session_manager = FlowSessionManager(redis_url=redis_url)
    return _flow_session_manager
