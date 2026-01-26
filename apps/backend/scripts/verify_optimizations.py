#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple verification script to check if optimizations are in place.
Doesn't require full system setup - just checks code changes.
"""

import sys
import os
import re

def check_file_contains(file_path: str, patterns: list, description: str) -> bool:
    """Check if file contains any of the patterns."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            for pattern in patterns:
                if pattern in content:
                    print(f"  [OK] {description}")
                    return True
        print(f"  [FAIL] {description} - NOT FOUND")
        return False
    except FileNotFoundError:
        print(f"  [FAIL] File not found: {file_path}")
        return False
    except Exception as e:
        print(f"  [ERROR] Error checking {file_path}: {e}")
        return False

def main():
    """Verify optimizations are in place."""
    print("\n" + "="*70)
    print("  OPTIMIZATION VERIFICATION")
    print("  Checking if Priority 1 & 2 changes are implemented")
    print("="*70)
    
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)
    
    checks = []
    
    # Priority 1 Checks
    print("\n" + "-"*70)
    print("PRIORITY 1: Caching & Database Pool")
    print("-"*70)
    
    # 1. Database pool size
    checks.append(check_file_contains(
        "infrastructure/db_manager.py",
        ["max=20", "max = 20"],
        "Database pool increased to 20"
    ))
    
    # 2. Cache service exists
    checks.append(check_file_contains(
        "services/cache_service.py",
        ["class MultiLayerCache", "class L1Cache", "class L2Cache"],
        "Cache service infrastructure created"
    ))
    
    # 3. Cache integration in orchestrator
    checks.append(check_file_contains(
        "services/search_system/orchestrator.py",
        ["self.cache", "cache.get", "cache.set", "generate_cache_key"],
        "Caching integrated in SearchOrchestrator"
    ))
    
    # 4. Query expansion caching
    checks.append(check_file_contains(
        "services/query_expander.py",
        ["cache.get", "cache.set", "generate_cache_key"],
        "Query expansion caching implemented"
    ))
    
    # 5. Cache invalidation on ingestion
    checks.append(check_file_contains(
        "services/ingestion_service.py",
        ["cache.delete_pattern", "Cache invalidated"],
        "Cache invalidation on ingestion"
    ))
    
    # 6. Config has cache settings
    checks.append(check_file_contains(
        "config.py",
        ["REDIS_URL", "CACHE_ENABLED", "CACHE_L1"],
        "Cache configuration added"
    ))
    
    # Priority 2 Checks
    print("\n" + "-"*70)
    print("PRIORITY 2: Performance Optimizations")
    print("-"*70)
    
    # 7. Parallel query expansion
    checks.append(check_file_contains(
        "services/search_system/orchestrator.py",
        ["expansion_future", "executor.submit(self.expander.expand_query", "max_workers=6"],
        "Parallel query expansion implemented"
    ))
    
    # 8. Smart reranking skip
    checks.append(check_file_contains(
        "services/search_service.py",
        ["skip_reranking", "Skipping reranking", "High RRF confidence"],
        "Smart reranking skip implemented"
    ))
    
    # 9. Intent classification caching
    checks.append(check_file_contains(
        "services/dual_ai_orchestrator.py",
        ["Cache hit for intent classification", "generate_cache_key", "service=\"intent\""],
        "Intent classification caching implemented"
    ))
    
    # 10. Requirements updated
    checks.append(check_file_contains(
        "requirements.txt",
        ["cachetools", "redis"],
        "Cache dependencies added to requirements.txt"
    ))
    
    # Summary
    print("\n" + "="*70)
    print("  VERIFICATION SUMMARY")
    print("="*70)
    
    passed = sum(checks)
    total = len(checks)
    
    print(f"\nTotal checks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    
    if passed == total:
        print("\n[SUCCESS] All optimizations are in place!")
        print("\nNext Steps:")
        print("  1. Install dependencies: pip install -r requirements.txt")
        print("  2. Set up Redis (optional): docker run -d -p 6379:6379 redis")
        print("  3. Configure .env file with cache settings")
        print("  4. Run full tests: python scripts/test_caching.py")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} optimization(s) not found")
        print("  Review the failed checks above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
