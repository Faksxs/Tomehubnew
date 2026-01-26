#!/bin/bash
# Quick test script for optimizations

echo "=========================================="
echo "Quick Optimization Tests"
echo "=========================================="

cd "$(dirname "$0")/.."

echo ""
echo "1. Testing cache functionality..."
python scripts/test_caching.py

echo ""
echo "2. Testing cache integration..."
python scripts/test_cache_integration.py

echo ""
echo "3. Running performance comparison..."
python scripts/performance_comparison.py

echo ""
echo "=========================================="
echo "Tests Complete!"
echo "=========================================="
