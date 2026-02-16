#!/usr/bin/env python3
"""
Layer 3 Diagnostic Test Script
================================
Tests the complete Layer 3 pipeline to identify failure points.
"""

import sys
import os

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oracledb
from dotenv import load_dotenv
from services.search_service import generate_answer
from services.smart_search_service import perform_search
from services.embedding_service import get_embedding
from infrastructure.db_manager import DatabaseManager

# Load environment
load_dotenv()

print("=" * 80)
print("LAYER 3 DIAGNOSTIC TEST")
print("=" * 80)

# Test Configuration (non-interactive for automation)
# You can modify these values directly in the script
TEST_FIREBASE_UID = os.getenv("TEST_FIREBASE_UID", "test_user")
TEST_QUESTION = os.getenv("TEST_QUESTION", "vicdan nedir")

print(f"\n[CONFIG] Testing with:")
print(f"  - UID: {TEST_FIREBASE_UID}")
print(f"  - Question: {TEST_QUESTION}")
print()

# =============================================================================
# TEST 1: Environment Check
# =============================================================================
print("\n" + "=" * 80)
print("TEST 1: ENVIRONMENT CHECK")
print("=" * 80)

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    print(f"✓ GEMINI_API_KEY is set (first 10 chars: {api_key[:10]}...)")
else:
    print("✗ GEMINI_API_KEY is NOT set")
    
# =============================================================================
# TEST 2: Database Connection
# =============================================================================
print("\n" + "=" * 80)
print("TEST 2: DATABASE CONNECTION")
print("=" * 80)

try:
    DatabaseManager.init_pool()
    conn = DatabaseManager.get_connection()
    cursor = conn.cursor()
    print("✓ Database connection successful")
    
    # Count total chunks
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT book_id) as books,
               SUM(CASE WHEN vec_embedding IS NOT NULL THEN 1 ELSE 0 END) as with_emb
        FROM TOMEHUB_CONTENT
        WHERE firebase_uid = :uid
    """, {"uid": TEST_FIREBASE_UID})
    
    row = cursor.fetchone()
    total_chunks, total_books, chunks_with_emb = row
    
    print(f"\n[DATABASE STATS]")
    print(f"  - Total chunks: {total_chunks}")
    print(f"  - Total books: {total_books}")
    print(f"  - Chunks with embeddings: {chunks_with_emb}")
    
    if total_chunks == 0:
        print("\n⚠️  WARNING: No content found for this user!")
        print("   Layer 3 cannot work without indexed content.")
    elif chunks_with_emb == 0:
        print("\n⚠️  WARNING: No embeddings found!")
        print("   Semantic search will fail.")
    else:
        print(f"\n✓ Database has {chunks_with_emb} searchable chunks")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Database connection failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# TEST 3: Embedding Service
# =============================================================================
print("\n" + "=" * 80)
print("TEST 3: EMBEDDING SERVICE")
print("=" * 80)

try:
    test_embedding = get_embedding(TEST_QUESTION)
    if test_embedding:
        print(f"✓ Embedding generated successfully")
        print(f"  - Dimension: {len(test_embedding)}")
        print(f"  - First 5 values: {test_embedding[:5]}")
    else:
        print("✗ Embedding service returned None")
except Exception as e:
    print(f"✗ Embedding service failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# TEST 4: Layer 2 (Smart Search)
# =============================================================================
print("\n" + "=" * 80)
print("TEST 4: LAYER 2 (SMART SEARCH)")
print("=" * 80)

try:
    layer2_results, _ = perform_search(TEST_QUESTION, TEST_FIREBASE_UID)
    
    if layer2_results:
        print(f"✓ Layer 2 returned {len(layer2_results)} results")
        print(f"\nTop 3 results:")
        for i, res in enumerate(layer2_results[:3], 1):
            title = res.get('title', 'Unknown')
            score = res.get('score', 0)
            snippet = str(res.get('content_chunk', ''))[:80]
            print(f"  {i}. [{score:.1f}] {title}")
            print(f"     {snippet}...")
    else:
        print("✗ Layer 2 returned empty results")
        print("   This means no relevant content was found.")
        
except Exception as e:
    print(f"✗ Layer 2 failed: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# TEST 5: Layer 3 (Full Pipeline)
# =============================================================================
print("\n" + "=" * 80)
print("TEST 5: LAYER 3 (FULL PIPELINE)")
print("=" * 80)

try:
    print(f"\n[INFO] Calling generate_answer()...")
    print(f"       This may take 10-30 seconds...\n")
    
    answer, sources, meta = generate_answer(TEST_QUESTION, TEST_FIREBASE_UID)
    
    if answer:
        print("✓ Layer 3 generated an answer\n")
        print("=" * 80)
        print("ANSWER:")
        print("=" * 80)
        print(answer)
        print("\n" + "=" * 80)
        print(f"SOURCES: {len(sources) if sources else 0} found")
        print("=" * 80)
        if sources:
            for i, src in enumerate(sources[:5], 1):
                print(f"  {i}. {src.get('title', 'Unknown')} (page {src.get('page_number', 'N/A')})")
    else:
        print("✗ Layer 3 returned None")
        print("   Possible causes:")
        print("   - No data retrieved from Layer 2")
        print("   - Gemini API failed")
        print("   - Logic error in generate_answer()")
        
except Exception as e:
    print(f"✗ Layer 3 failed with exception: {e}")
    import traceback
    traceback.print_exc()

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "=" * 80)
print("DIAGNOSTIC SUMMARY")
print("=" * 80)
print("\nPlease review the test results above.")
print("If Layer 2 works but Layer 3 doesn't, check the Gemini API logs.")
print("If Layer 2 doesn't work, the database likely has no indexed content.\n")
