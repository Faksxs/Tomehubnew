#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick script to test database content for Layer 3 diagnosis
"""

from infrastructure.db_manager import DatabaseManager
from services.embedding_service import get_embedding

def main():
    # Initialize database pool
    DatabaseManager.init_pool()
    
    conn = DatabaseManager.get_connection()
    cursor = conn.cursor()
    
    # Test 1: Count total chunks
    cursor.execute(
        "SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid",
        {"uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"}
    )
    total_chunks = cursor.fetchone()[0]
    print(f"✓ Total chunks for user: {total_chunks}")
    
    # Test 2: Count books
    cursor.execute(
        "SELECT COUNT(DISTINCT title) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid",
        {"uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"}
    )
    total_books = cursor.fetchone()[0]
    print(f"✓ Total books: {total_books}")
    
    # Test 3: Top 5 books
    cursor.execute("""
        SELECT title, COUNT(*) as chunk_count 
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :uid 
        GROUP BY title 
        ORDER BY chunk_count DESC 
        FETCH FIRST 5 ROWS ONLY
    """, {"uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"})
    
    print("\n✓ Top 5 books by chunk count:")
    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} chunks")
    
    # Test 4: Vector search
    print("\n✓ Testing vector search for 'vicdan'...")
    emb = get_embedding("vicdan")
    print(f"  - Embedding generated: {emb is not None}")
    print(f"  - Embedding length: {len(emb) if emb else 0}")
    
    if emb:
        cursor.execute("""
            SELECT content_chunk, title, page_number,
                   VECTOR_DISTANCE(vec_embedding, :p_vec, COSINE) as dist
            FROM TOMEHUB_CONTENT 
            WHERE firebase_uid = :p_uid
            ORDER BY dist 
            FETCH FIRST 3 ROWS ONLY
        """, {"p_vec": emb, "p_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"})
        
        print("\n  Top 3 vector search results:")
        for row in cursor.fetchall():
            content = row[0].read() if row[0] else ""
            print(f"    - Distance: {row[3]:.4f}, Title: {row[1]}, Page: {row[2]}")
            print(f"      Content: {content[:100]}...")
    
    # Test 5: Check if embeddings exist
    cursor.execute("""
        SELECT COUNT(*) 
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :uid AND vec_embedding IS NOT NULL
    """, {"uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"})
    
    chunks_with_embeddings = cursor.fetchone()[0]
    print(f"\n✓ Chunks with embeddings: {chunks_with_embeddings} / {total_chunks}")
    
    if chunks_with_embeddings == 0:
        print("\n⚠️  WARNING: No embeddings found! This is why search is failing.")
    
    cursor.close()
    conn.close()
    print("\n✓ Database test complete")

if __name__ == "__main__":
    main()
