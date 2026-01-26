# -*- coding: utf-8 -*-
"""
Multi-layer caching service for TomeHub.
Implements L1 (in-memory) and L2 (Redis) cache layers with query normalization.
"""

from typing import Optional, Any
import hashlib
import json
import time
import unicodedata
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Try to import Redis, but make it optional
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available. L2 cache will be disabled.")


def normalize_query(query: str) -> str:
    """
    Normalize query for cache key generation.
    
    Steps:
    1. Normalize whitespace (collapse multiple spaces)
    2. Convert to lowercase (preserving Turkish characters)
    3. Unicode normalization (NFD → NFC)
    4. Strip leading/trailing whitespace
    
    Args:
        query: Raw query string
        
    Returns:
        Normalized query string
    """
    if not query:
        return ""
    
    # Normalize whitespace
    normalized = ' '.join(query.split())
    
    # Lowercase (preserving Turkish chars: ç, ğ, ı, ö, ş, ü)
    normalized = normalized.lower()
    
    # Unicode normalization (NFD → NFC)
    normalized = unicodedata.normalize('NFC', normalized)
    
    return normalized.strip()


class L1Cache:
    """In-memory L1 cache using TTLCache."""
    
    def __init__(self, maxsize: int = 1000, ttl: int = 600):
        """
        Initialize L1 cache.
        
        Args:
            maxsize: Maximum number of entries (default: 1000)
            ttl: Time-to-live in seconds (default: 600 = 10 minutes)
        """
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        logger.info(f"L1 Cache initialized: maxsize={maxsize}, ttl={ttl}s")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        return self.cache.get(key)
    
    def set(self, key: str, value: Any):
        """Set value in cache."""
        self.cache[key] = value
    
    def delete(self, key: str):
        """Delete key from cache."""
        self.cache.pop(key, None)
    
    def clear(self):
        """Clear all entries from cache."""
        self.cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)


class L2Cache:
    """Distributed L2 cache using Redis."""
    
    def __init__(self, redis_client=None, redis_url: str = None):
        """
        Initialize L2 cache.
        
        Args:
            redis_client: Existing Redis client (optional)
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        """
        if redis_client:
            self.redis = redis_client
        elif REDIS_AVAILABLE and redis_url:
            self.redis = redis.from_url(redis_url)
        elif REDIS_AVAILABLE:
            # Try default connection
            try:
                self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=False)
                # Test connection
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. L2 cache disabled.")
                self.redis = None
        else:
            self.redis = None
        
        if self.redis:
            logger.info("L2 Cache (Redis) initialized")
        else:
            logger.warning("L2 Cache (Redis) not available")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if not self.redis:
            return None
        
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"L2 cache get error for key {key}: {e}")
        return None
    
    def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL."""
        if not self.redis:
            return
        
        try:
            self.redis.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error(f"L2 cache set error for key {key}: {e}")
    
    def delete(self, key: str):
        """Delete key from cache."""
        if not self.redis:
            return
        
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"L2 cache delete error for key {key}: {e}")
    
    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern (use with caution)."""
        if not self.redis:
            return
        
        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.info(f"Deleted {len(keys)} keys matching pattern: {pattern}")
        except Exception as e:
            logger.error(f"L2 cache delete_pattern error for pattern {pattern}: {e}")
    
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self.redis is not None


class MultiLayerCache:
    """Multi-layer cache with L1 (in-memory) and L2 (Redis)."""
    
    def __init__(self, l1: L1Cache = None, l2: L2Cache = None):
        """
        Initialize multi-layer cache.
        
        Args:
            l1: L1 cache instance (optional, will create default if None)
            l2: L2 cache instance (optional, will try to create if None)
        """
        self.l1 = l1 or L1Cache()
        self.l2 = l2 or L2Cache()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache (checks L1 first, then L2).
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        # Check L1 first
        value = self.l1.get(key)
        if value is not None:
            return value
        
        # Check L2
        value = self.l2.get(key)
        if value is not None:
            # Populate L1 for next time
            self.l1.set(key, value)
            return value
        
        return None
    
    def set(self, key: str, value: Any, ttl: int):
        """
        Set value in both cache layers.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (for L2)
        """
        # Store in both layers
        self.l2.set(key, value, ttl)
        self.l1.set(key, value)  # L1 TTL is fixed in constructor
    
    def delete(self, key: str):
        """Delete key from both cache layers."""
        self.l1.delete(key)
        self.l2.delete(key)
    
    def delete_pattern(self, pattern: str):
        """Delete pattern from L2 (L1 doesn't support patterns)."""
        self.l2.delete_pattern(pattern)
    
    def clear(self):
        """Clear all entries from both cache layers."""
        self.l1.clear()
        # Note: L2 clear would require redis.flushdb() which is dangerous
    
    def is_available(self) -> bool:
        """Check if at least one cache layer is available."""
        return self.l2.is_available() or True  # L1 is always available


def generate_cache_key(
    service: str,
    query: str,
    firebase_uid: str,
    book_id: str = None,
    limit: int = 50,
    version: str = "v2"
) -> str:
    """
    Generate cache key with all context components.
    
    Format: {service}:{normalized_query_hash}:{firebase_uid}:{book_id}:{limit}:{version}
    
    Args:
        service: Service identifier (e.g., "search", "expansion", "embedding")
        query: User query string (will be normalized)
        firebase_uid: User identifier
        book_id: Optional book identifier
        limit: Result count limit
        version: Model/embedding version
        
    Returns:
        Cache key string
    """
    normalized = normalize_query(query)
    query_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]
    
    components = [service, query_hash, firebase_uid]
    if book_id:
        components.append(book_id)
    components.extend([str(limit), version])
    
    return ":".join(components)


# Global cache instance (will be initialized in app startup)
_cache_instance: Optional[MultiLayerCache] = None


def get_cache() -> Optional[MultiLayerCache]:
    """Get global cache instance."""
    return _cache_instance


def init_cache(l1_maxsize: int = 1000, l1_ttl: int = 600, redis_url: str = None) -> MultiLayerCache:
    """
    Initialize global cache instance.
    
    Args:
        l1_maxsize: L1 cache max size
        l1_ttl: L1 cache TTL in seconds
        redis_url: Redis connection URL (optional)
        
    Returns:
        Initialized MultiLayerCache instance
    """
    global _cache_instance
    
    l1 = L1Cache(maxsize=l1_maxsize, ttl=l1_ttl)
    l2 = L2Cache(redis_url=redis_url)
    
    _cache_instance = MultiLayerCache(l1=l1, l2=l2)
    logger.info("Global cache initialized")
    
    return _cache_instance
