# Test Zone 3 vector search after fix

import sys
sys.path.insert(0, '.')

from infrastructure.db_manager import DatabaseManager
from services.embedding_service import get_query_embedding
import array

DatabaseManager.init_pool()

uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'

conn = DatabaseManager.get_connection()
cur = conn.cursor()

# Check embeddings count
cur.execute(f"SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = '{uid}' AND VEC_EMBEDDING IS NOT NULL")
emb_count = cur.fetchone()[0]
print(f"Content with VEC_EMBEDDING for user: {emb_count}")

# Test vector search (Zone 3 simulation)
print("\nTesting vector search (Zone 3):")
vec = get_query_embedding("General Discovery")
if vec:
    vec_array = array.array('f', list(vec))
    cur.execute(f"""
        SELECT id, title, VECTOR_DISTANCE(VEC_EMBEDDING, :vec, COSINE) as distance
        FROM TOMEHUB_CONTENT
        WHERE firebase_uid = '{uid}'
        AND VEC_EMBEDDING IS NOT NULL
        ORDER BY distance
        FETCH FIRST 5 ROWS ONLY
    """, {"vec": vec_array})
    
    print("Top 5 results:")
    for row in cur.fetchall():
        distance = row[2]
        similarity = 1 - distance if distance else 0
        title = row[1][:50] if row[1] else 'N/A'
        print(f"  ID: {row[0]}, Title: {title}, Similarity: {similarity:.2%}")
else:
    print("Failed to generate embedding")

conn.close()
