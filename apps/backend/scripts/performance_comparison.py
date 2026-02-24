#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance comparison script: Before vs After optimizations.
Shows measurable improvements from Priority 1 & 2 changes.
"""

import sys
import os
import time
import statistics
from typing import List, Dict

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding
from services.cache_service import init_cache
from config import settings

def measure_search_performance(query: str, firebase_uid: str, use_cache: bool = True, iterations: int = 3):
    """Measure search performance with or without cache."""
    cache = init_cache() if use_cache else None
    if cache:
        cache.clear()  # Start fresh
    
    orchestrator = SearchOrchestrator(
        embedding_fn=get_embedding,
        cache=cache
    )
    
    latencies = []
    
    for i in range(iterations):
        start_time = time.time()
        results = orchestrator.search(query, firebase_uid, limit=10)
        latency = time.time() - start_time
        latencies.append(latency)
        
        if i == 0:
            print(f"    Iteration {i+1}: {latency:.3f}s ({len(results)} results) - {'Compute' if i == 0 else 'Cached'}")
        else:
            print(f"    Iteration {i+1}: {latency:.3f}s ({len(results)} results) - Cached")
        
        if i < iterations - 1:
            time.sleep(0.5)
    
    return {
        'first': latencies[0],
        'cached_avg': statistics.mean(latencies[1:]) if len(latencies) > 1 else latencies[0],
        'overall_avg': statistics.mean(latencies),
        'min': min(latencies),
        'max': max(latencies),
        'latencies': latencies
    }

def main():
    """Run performance comparison."""
    print("\n" + "="*70)
    print("  PERFORMANCE COMPARISON: Before vs After Optimizations")
    print("="*70)
    
    test_queries = [
        "vicdanın doğası",
        "ahlak nedir",
        "etik kavramı nedir"
    ]
    if len(sys.argv) < 2:
        print("Usage: python performance_comparison.py <uid>")
        sys.exit(1)
    test_uid = sys.argv[1]
    
    print("\n" + "-"*70)
    print("SCENARIO 1: Without Cache (Baseline)")
    print("-"*70)
    
    no_cache_stats = []
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        stats = measure_search_performance(query, test_uid, use_cache=False, iterations=2)
        no_cache_stats.append(stats)
        print(f"  Average: {stats['overall_avg']:.3f}s")
    
    avg_no_cache = statistics.mean([s['overall_avg'] for s in no_cache_stats])
    print(f"\n📊 Average (no cache): {avg_no_cache:.3f}s")
    
    print("\n" + "-"*70)
    print("SCENARIO 2: With Cache (Optimized)")
    print("-"*70)
    
    with_cache_stats = []
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        stats = measure_search_performance(query, test_uid, use_cache=True, iterations=3)
        with_cache_stats.append(stats)
        print(f"  First (compute): {stats['first']:.3f}s")
        print(f"  Cached avg: {stats['cached_avg']:.3f}s")
        print(f"  Overall avg: {stats['overall_avg']:.3f}s")
    
    avg_with_cache_first = statistics.mean([s['first'] for s in with_cache_stats])
    avg_with_cache_cached = statistics.mean([s['cached_avg'] for s in with_cache_stats])
    
    print(f"\n📊 Average (with cache):")
    print(f"  First run (compute): {avg_with_cache_first:.3f}s")
    print(f"  Cached runs: {avg_with_cache_cached:.3f}s")
    
    # Calculate improvements
    print("\n" + "="*70)
    print("  PERFORMANCE IMPROVEMENTS")
    print("="*70)
    
    speedup_first = avg_no_cache / avg_with_cache_first if avg_with_cache_first > 0 else 0
    speedup_cached = avg_no_cache / avg_with_cache_cached if avg_with_cache_cached > 0 else 0
    
    reduction_first = ((avg_no_cache - avg_with_cache_first) / avg_no_cache * 100) if avg_no_cache > 0 else 0
    reduction_cached = ((avg_no_cache - avg_with_cache_cached) / avg_no_cache * 100) if avg_no_cache > 0 else 0
    
    print(f"\n📈 Cache Impact:")
    print(f"  First run improvement: {reduction_first:.1f}% faster ({speedup_first:.1f}x)")
    print(f"  Cached run improvement: {reduction_cached:.1f}% faster ({speedup_cached:.1f}x)")
    
    print(f"\n💰 Cost Savings:")
    print(f"  Query expansion calls saved: ~{len(test_queries) * 2} per {len(test_queries)} queries")
    print(f"  (Expansions cached for 7 days)")
    
    print(f"\n⚡ Latency Improvements:")
    if speedup_cached > 10:
        print(f"  ✓ Excellent: {speedup_cached:.1f}x faster for cached queries")
    elif speedup_cached > 5:
        print(f"  ✓ Very Good: {speedup_cached:.1f}x faster for cached queries")
    elif speedup_cached > 2:
        print(f"  ✓ Good: {speedup_cached:.1f}x faster for cached queries")
    else:
        print(f"  ⚠ Moderate: {speedup_cached:.1f}x faster for cached queries")
    
    # Database pool check
    print("\n" + "-"*70)
    print("DATABASE POOL STATUS")
    print("-"*70)
    
    try:
        from infrastructure.db_manager import DatabaseManager
        if DatabaseManager._pool:
            max_conn = DatabaseManager._pool.max
            print(f"✓ Pool size: {max_conn} connections")
            if max_conn >= 20:
                print(f"  ✓ Increased from 10 to {max_conn} (2x capacity)")
            else:
                print(f"  ⚠ Current: {max_conn} (expected >= 20)")
        else:
            print("⚠ Pool not initialized")
    except Exception as e:
        print(f"⚠ Could not check pool: {e}")
    
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)
    print(f"\n✅ Optimizations implemented:")
    print(f"  1. Multi-layer caching (L1 + L2)")
    print(f"  2. Parallel query expansion")
    print(f"  3. Smart reranking skip")
    print(f"  4. Intent classification caching")
    print(f"  5. Database pool increase (10 → 20)")
    
    print(f"\n📊 Expected improvements:")
    print(f"  - Cached queries: {reduction_cached:.0f}% faster")
    print(f"  - High-confidence queries: 30-50% faster (reranking skip)")
    print(f"  - Intent classification: 200-500ms faster (cached)")
    print(f"  - Database capacity: 2x more concurrent requests")

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Performance comparison failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
