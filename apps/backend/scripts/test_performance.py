#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Performance test to measure cache impact on search latency.
"""

import sys
import os
import time
import statistics

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding
from services.cache_service import init_cache, get_cache
from config import settings

def benchmark_search(query: str, firebase_uid: str, iterations: int = 5, use_cache: bool = True):
    """Benchmark search performance with and without cache."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: Search Performance ({'WITH' if use_cache else 'WITHOUT'} cache)")
    print(f"{'='*60}")
    
    cache = init_cache(
        l1_maxsize=1000,
        l1_ttl=3600,
        redis_url=settings.REDIS_URL
    ) if use_cache else None
    
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
        
        print(f"  Iteration {i+1}: {latency:.3f}s ({len(results)} results)")
        
        # Small delay between iterations
        if i < iterations - 1:
            time.sleep(0.5)
    
    avg_latency = statistics.mean(latencies)
    min_latency = min(latencies)
    max_latency = max(latencies)
    median_latency = statistics.median(latencies)
    
    print(f"\n  Statistics:")
    print(f"    Average: {avg_latency:.3f}s")
    print(f"    Median:  {median_latency:.3f}s")
    print(f"    Min:     {min_latency:.3f}s")
    print(f"    Max:     {max_latency:.3f}s")
    
    return {
        'avg': avg_latency,
        'median': median_latency,
        'min': min_latency,
        'max': max_latency,
        'latencies': latencies
    }

def main():
    """Run performance benchmarks."""
    print("\n" + "="*60)
    print("SEARCH PERFORMANCE BENCHMARK")
    print("="*60)
    
    test_query = "vicdanın doğası"
    if len(sys.argv) < 2:
        print("Usage: python test_performance.py <uid>")
        sys.exit(1)
    test_uid = sys.argv[1]
    
    # First run: without cache (warm-up)
    print("\n⚠ Warming up (first search may be slower)...")
    orchestrator = SearchOrchestrator(embedding_fn=get_embedding, cache=None)
    orchestrator.search(test_query, test_uid, limit=10)
    time.sleep(1)
    
    # Benchmark without cache
    no_cache_stats = benchmark_search(test_query, test_uid, iterations=3, use_cache=False)
    
    # Clear any existing cache
    cache = init_cache()
    cache.clear()
    time.sleep(1)
    
    # Benchmark with cache (first will compute, rest will hit cache)
    with_cache_stats = benchmark_search(test_query, test_uid, iterations=5, use_cache=True)
    
    # Compare results
    print(f"\n{'='*60}")
    print("PERFORMANCE COMPARISON")
    print(f"{'='*60}")
    
    print(f"\nWithout Cache:")
    print(f"  Average: {no_cache_stats['avg']:.3f}s")
    print(f"  Median:  {no_cache_stats['median']:.3f}s")
    
    print(f"\nWith Cache (first iteration computes, rest hit cache):")
    print(f"  First iteration: {with_cache_stats['latencies'][0]:.3f}s (compute)")
    print(f"  Cached avg:      {statistics.mean(with_cache_stats['latencies'][1:]):.3f}s")
    print(f"  Overall avg:     {with_cache_stats['avg']:.3f}s")
    
    speedup = no_cache_stats['avg'] / statistics.mean(with_cache_stats['latencies'][1:])
    print(f"\n📊 Cache Speedup: {speedup:.1f}x faster for cached queries")
    
    if speedup > 5:
        print("✓ Excellent cache performance!")
    elif speedup > 2:
        print("✓ Good cache performance")
    else:
        print("⚠ Cache performance could be better")

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
