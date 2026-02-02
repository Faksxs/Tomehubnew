"""
Simple script to clear the backend cache.
Run this if you experience stale search results.
"""
import requests

try:
    # This would require adding a /api/cache/clear endpoint
    # For now, just restart the backend to clear L1 cache
    print("To clear the cache, restart the backend server.")
    print("The L1 cache (in-memory) will be cleared automatically.")
    print("TTL is 600 seconds (10 minutes), so stale entries expire naturally.")
except Exception as e:
    print(f"Error: {e}")
