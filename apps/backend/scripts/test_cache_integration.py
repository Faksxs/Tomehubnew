#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration test for cache invalidation on ingestion.
"""

import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cache_service import init_cache, generate_cache_key, get_cache
from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding
from config import settings

def test_cache_invalidation():
    """Test that cache is invalidated after ingestion."""
    print("\n" + "="*60)
    print("CACHE INVALIDATION TEST")
    print("="*60)
    
    # Initialize cache
    cache = init_cache(
        l1_maxsize=100,
        l1_ttl=3600,
        redis_url=settings.REDIS_URL
    )
    
    test_uid = "test_user_001"
    test_query = "test query for invalidation"
    
    # Create orchestrator
    orchestrator = SearchOrchestrator(
        embedding_fn=get_embedding,
        cache=cache
    )
    
    # Perform search (will cache results)
    print(f"\n1. Performing search (will cache results)...")
    results1 = orchestrator.search(test_query, test_uid, limit=10)
    print(f"   Results: {len(results1)} items")
    
    # Verify cache key exists
    cache_key = generate_cache_key(
        service="search",
        query=test_query,
        firebase_uid=test_uid,
        book_id=None,
        limit=10,
        version=settings.EMBEDDING_MODEL_VERSION
    )
    
    cached_value = cache.get(cache_key)
    assert cached_value is not None, "Cache should contain the search results"
    print(f"   ✓ Cache key exists: {cache_key[:50]}...")
    
    # Simulate cache invalidation (as would happen after ingestion)
    print(f"\n2. Simulating cache invalidation (as after ingestion)...")
    pattern = f"search:*:{test_uid}:*"
    cache.delete_pattern(pattern)
    print(f"   Pattern deleted: {pattern}")
    
    # Verify cache is cleared
    cached_value = cache.get(cache_key)
    assert cached_value is None, "Cache should be cleared after invalidation"
    print(f"   ✓ Cache cleared successfully")
    
    # Perform search again (should compute fresh, not use cache)
    print(f"\n3. Performing search again (should compute fresh)...")
    results2 = orchestrator.search(test_query, test_uid, limit=10)
    print(f"   Results: {len(results2)} items")
    
    # Verify cache is repopulated
    cached_value = cache.get(cache_key)
    assert cached_value is not None, "Cache should be repopulated after new search"
    print(f"   ✓ Cache repopulated after new search")
    
    print("\n✓ All cache invalidation tests passed!")
    return True

if __name__ == "__main__":
    try:
        test_cache_invalidation()
        print("\n🎉 Integration test passed!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
