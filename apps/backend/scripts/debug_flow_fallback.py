# Test Zone 1 Fallback for Topic Anchor

import sys
sys.path.insert(0, '.')

from infrastructure.db_manager import DatabaseManager
from services.embedding_service import get_query_embedding
import array

DatabaseManager.init_pool()

uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
anchor_text = "General Discovery"

conn = DatabaseManager.get_connection()
cur = conn.cursor()

print(f"Testing Zone 1 Fallback for Topic: '{anchor_text}'")

# 1. Generate Vector
vec = get_query_embedding(anchor_text)
if not vec:
    print("Failed to generate embedding")
    sys.exit(1)

vec_array = array.array('f', list(vec))

# 2. Run the Zone 1 Fallback Query
print("Running Zone 1 Fallback Query (Threshold 0.80)...")
cur.execute("""
    SELECT id, title, VECTOR_DISTANCE(VEC_EMBEDDING, :vec, COSINE) as distance
    FROM TOMEHUB_CONTENT
    WHERE firebase_uid = :uid
    AND VEC_EMBEDDING IS NOT NULL
    ORDER BY distance
    FETCH FIRST 5 ROWS ONLY
""", {
    "uid": uid,
    "vec": vec_array
})

results = cur.fetchall()
if not results:
    print("No results found! Check threshold or data.")
else:
    print(f"Found {len(results)} results:")
    for row in results:
        distance = row[2]
        similarity = 1 - distance if distance else 0
        print(f"  ID: {row[0]}, Title: {row[1][:40]}, Sim: {similarity:.2%}")

conn.close()
