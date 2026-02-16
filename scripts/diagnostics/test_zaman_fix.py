#!/usr/bin/env python3
"""
Test script to verify the 'zaman' search fix in Layer 2
"""

import sys
import os
from pathlib import Path

# Resolve repository root from scripts/diagnostics/test_zaman_fix.py
repo_root = Path(__file__).resolve().parents[2]
backend_dir = repo_root / 'apps' / 'backend'
sys.path.insert(0, str(backend_dir))

import asyncio
from dotenv import load_dotenv

# Import after path setup
from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding
from services.cache_service import MultiLayerCache
from infrastructure.db_manager import DatabaseManager

# Load environment
load_dotenv(str(backend_dir / '.env'))

async def test_zaman_search():
    print("=" * 80)
    print("TESTING LAYER 2 SEARCH FIX FOR 'zaman' QUERY")
    print("=" * 80)
    
    # Initialize database
    try:
        DatabaseManager.init_pool()
        print("✓ Database connection pool initialized")
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}")
        return
    
    # Get a test UID from the database
    test_uid = None
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT FETCH FIRST 1 ROW ONLY")
                row = cursor.fetchone()
                if row:
                    test_uid = row[0]
                    print(f"✓ Using test UID: {test_uid}")
                else:
                    print("✗ No users found in database")
                    return
    except Exception as e:
        print(f"✗ Failed to get test UID: {e}")
        return
    
    # Initialize search orchestrator
    try:
        cache = MultiLayerCache()
        orchestrator = SearchOrchestrator(embedding_fn=get_embedding, cache=cache)
        print("✓ SearchOrchestrator initialized")
    except Exception as e:
        print(f"✗ Failed to initialize orchestrator: {e}")
        return
    
    # Test search for 'zaman'
    print("\n" + "-" * 80)
    print("Searching for: 'zaman'")
    print("-" * 80)
    
    try:
        results, metadata = orchestrator.search(
            query="zaman",
            firebase_uid=test_uid,
            limit=10,
            intent="SYNTHESIS"
        )
        
        print(f"\n✓ Search completed successfully")
        print(f"✓ Found {len(results)} results")
        
        if results:
            print("\nTop Results:")
            for i, result in enumerate(results[:5], 1):
                print(f"\n  {i}. Title: {result.get('title', 'N/A')}")
                print(f"     Source Type: {result.get('source_type', 'N/A')}")
                print(f"     Match Type: {result.get('match_type', 'N/A')}")
                print(f"     Score: {result.get('score', 0):.2f}")
                content_preview = result.get('content_chunk', '')[:100].replace('\n', ' ')
                print(f"     Preview: {content_preview}...")
        else:
            print("\n✗ No results found - FIX FAILED")
            
    except Exception as e:
        print(f"✗ Search failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(test_zaman_search())
