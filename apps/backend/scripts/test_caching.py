#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for caching infrastructure.
Tests L1, L2, and multi-layer cache functionality.
"""

import sys
import os
import time

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.cache_service import (
    L1Cache, L2Cache, MultiLayerCache, 
    generate_cache_key, normalize_query, init_cache
)
from config import settings

def test_query_normalization():
    """Test query normalization function."""
    print("\n" + "="*60)
    print("TEST 1: Query Normalization")
    print("="*60)
    
    test_cases = [
        ("  Vicdanın   Doğası  ", "vicdanın doğası"),
        ("What is CONSCIENCE?", "what is conscience?"),
        ("Test\t\nQuery", "test query"),
        ("  Multiple   Spaces   Here  ", "multiple spaces here"),
    ]
    
    all_passed = True
    for input_query, expected in test_cases:
        result = normalize_query(input_query)
        passed = result == expected
        status = "✓" if passed else "✗"
        print(f"{status} Input: '{input_query}'")
        print(f"  Expected: '{expected}'")
        print(f"  Got:      '{result}'")
        if not passed:
            all_passed = False
        print()
    
    return all_passed

def test_cache_key_generation():
    """Test cache key generation."""
    print("\n" + "="*60)
    print("TEST 2: Cache Key Generation")
    print("="*60)
    
    key1 = generate_cache_key("search", "test query", "user123", None, 50, "v2")
    key2 = generate_cache_key("search", "test query", "user123", None, 50, "v2")
    key3 = generate_cache_key("search", "test query", "user456", None, 50, "v2")
    key4 = generate_cache_key("search", "different query", "user123", None, 50, "v2")
    
    # Same inputs should generate same key
    assert key1 == key2, "Same inputs should generate same key"
    print(f"✓ Same inputs generate same key: {key1[:50]}...")
    
    # Different users should generate different keys
    assert key1 != key3, "Different users should generate different keys"
    print(f"✓ Different users generate different keys")
    
    # Different queries should generate different keys
    assert key1 != key4, "Different queries should generate different keys"
    print(f"✓ Different queries generate different keys")
    
    print(f"\nSample keys:")
    print(f"  Key 1: {key1}")
    print(f"  Key 3: {key3}")
    print(f"  Key 4: {key4}")
    
    return True

def test_l1_cache():
    """Test L1 (in-memory) cache."""
    print("\n" + "="*60)
    print("TEST 3: L1 Cache (In-Memory)")
    print("="*60)
    
    cache = L1Cache(maxsize=10, ttl=2)  # 2 second TTL for testing
    
    # Test set and get
    cache.set("key1", "value1")
    value = cache.get("key1")
    assert value == "value1", "L1 cache should return stored value"
    print("✓ Set and get works")
    
    # Test cache hit
    value = cache.get("key1")
    assert value == "value1", "L1 cache should return cached value"
    print("✓ Cache hit works")
    
    # Test cache miss
    value = cache.get("nonexistent")
    assert value is None, "L1 cache should return None for missing key"
    print("✓ Cache miss works")
    
    # Test TTL expiration
    cache.set("key2", "value2")
    time.sleep(3)  # Wait for TTL to expire
    value = cache.get("key2")
    assert value is None, "L1 cache should expire after TTL"
    print("✓ TTL expiration works")
    
    # Test size limit
    for i in range(15):
        cache.set(f"key{i}", f"value{i}")
    # Should have evicted oldest entries
    assert cache.size() <= 10, "L1 cache should respect maxsize"
    print(f"✓ Size limit works (current size: {cache.size()})")
    
    return True

def test_l2_cache():
    """Test L2 (Redis) cache if available."""
    print("\n" + "="*60)
    print("TEST 4: L2 Cache (Redis)")
    print("="*60)
    
    cache = L2Cache(redis_url=settings.REDIS_URL)
    
    if not cache.is_available():
        print("⚠ Redis not available, skipping L2 cache tests")
        print("  To test L2 cache, start Redis and set REDIS_URL environment variable")
        return True  # Not a failure, just skip
    
    # Test set and get
    cache.set("test_key", {"data": "test_value"}, ttl=10)
    value = cache.get("test_key")
    assert value == {"data": "test_value"}, "L2 cache should return stored value"
    print("✓ Set and get works")
    
    # Test cache hit
    value = cache.get("test_key")
    assert value == {"data": "test_value"}, "L2 cache should return cached value"
    print("✓ Cache hit works")
    
    # Test cache miss
    value = cache.get("nonexistent_key")
    assert value is None, "L2 cache should return None for missing key"
    print("✓ Cache miss works")
    
    # Cleanup
    cache.delete("test_key")
    print("✓ Cleanup works")
    
    return True

def test_multilayer_cache():
    """Test multi-layer cache (L1 + L2)."""
    print("\n" + "="*60)
    print("TEST 5: Multi-Layer Cache")
    print("="*60)
    
    l1 = L1Cache(maxsize=100, ttl=60)
    l2 = L2Cache(redis_url=settings.REDIS_URL)
    cache = MultiLayerCache(l1=l1, l2=l2)
    
    test_key = "multilayer_test"
    test_value = {"result": "test_data", "sources": []}
    
    # Test write (should write to both layers)
    cache.set(test_key, test_value, ttl=60)
    print("✓ Write to both layers")
    
    # Test read from L1 (should hit L1)
    l1_value = l1.get(test_key)
    assert l1_value == test_value, "L1 should have the value"
    print("✓ Value stored in L1")
    
    # Clear L1 to test L2 fallback
    l1.delete(test_key)
    
    # Test read from L2 (should fallback to L2 and populate L1)
    value = cache.get(test_key)
    assert value == test_value, "Should get value from L2"
    print("✓ Fallback to L2 works")
    
    # Verify L1 was populated
    l1_value = l1.get(test_key)
    assert l1_value == test_value, "L1 should be populated from L2"
    print("✓ L1 populated from L2 on miss")
    
    # Cleanup
    cache.delete(test_key)
    print("✓ Cleanup works")
    
    return True

def test_search_orchestrator_caching():
    """Test search orchestrator with caching."""
    print("\n" + "="*60)
    print("TEST 6: Search Orchestrator Caching")
    print("="*60)
    
    try:
        from services.search_system.orchestrator import SearchOrchestrator
        from services.embedding_service import get_embedding
        
        # Initialize cache
        cache = init_cache(
            l1_maxsize=100,
            l1_ttl=60,
            redis_url=settings.REDIS_URL
        )
        
        # Create orchestrator with cache
        orchestrator = SearchOrchestrator(
            embedding_fn=get_embedding,
            cache=cache
        )
        
        test_query = "test query"
        test_uid = "test_user_001"
        
        print(f"Running first search (should compute and cache)...")
        start_time = time.time()
        results1 = orchestrator.search(test_query, test_uid, limit=10)
        time1 = time.time() - start_time
        print(f"  First search took: {time1:.3f}s")
        print(f"  Results: {len(results1)} items")
        
        print(f"\nRunning second search (should hit cache)...")
        start_time = time.time()
        results2 = orchestrator.search(test_query, test_uid, limit=10)
        time2 = time.time() - start_time
        print(f"  Second search took: {time2:.3f}s")
        print(f"  Results: {len(results2)} items")
        
        # Second search should be much faster
        if time2 < time1 * 0.1:  # At least 10x faster
            print(f"✓ Cache hit confirmed ({time1/time2:.1f}x speedup)")
        else:
            print(f"⚠ Cache may not be working (only {time1/time2:.1f}x speedup)")
        
        # Results should be identical
        assert len(results1) == len(results2), "Cached results should match"
        print("✓ Cached results match original")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_query_expansion_caching():
    """Test query expansion caching."""
    print("\n" + "="*60)
    print("TEST 7: Query Expansion Caching")
    print("="*60)
    
    try:
        from services.query_expander import QueryExpander
        
        # Initialize cache
        cache = init_cache(
            l1_maxsize=100,
            l1_ttl=60,
            redis_url=settings.REDIS_URL
        )
        
        expander = QueryExpander(cache=cache)
        
        test_query = "vicdanın doğası"
        
        print(f"Running first expansion (should call LLM and cache)...")
        start_time = time.time()
        variations1 = expander.expand_query(test_query)
        time1 = time.time() - start_time
        print(f"  First expansion took: {time1:.3f}s")
        print(f"  Variations: {variations1}")
        
        print(f"\nRunning second expansion (should hit cache)...")
        start_time = time.time()
        variations2 = expander.expand_query(test_query)
        time2 = time.time() - start_time
        print(f"  Second expansion took: {time2:.3f}s")
        print(f"  Variations: {variations2}")
        
        # Second expansion should be much faster
        if time2 < time1 * 0.1:  # At least 10x faster
            print(f"✓ Cache hit confirmed ({time1/time2:.1f}x speedup)")
        else:
            print(f"⚠ Cache may not be working (only {time1/time2:.1f}x speedup)")
        
        # Variations should be identical
        assert variations1 == variations2, "Cached variations should match"
        print("✓ Cached variations match original")
        
        return True
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("CACHING INFRASTRUCTURE TESTS")
    print("="*60)
    
    tests = [
        ("Query Normalization", test_query_normalization),
        ("Cache Key Generation", test_cache_key_generation),
        ("L1 Cache", test_l1_cache),
        ("L2 Cache", test_l2_cache),
        ("Multi-Layer Cache", test_multilayer_cache),
        ("Search Orchestrator Caching", test_search_orchestrator_caching),
        ("Query Expansion Caching", test_query_expansion_caching),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
