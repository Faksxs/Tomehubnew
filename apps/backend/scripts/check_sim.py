# Check "General Discovery" similarity scores

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

# 1. Generate Vector
vec = get_query_embedding(anchor_text)
if not vec:
    print("Failed to generate embedding")
    sys.exit(1)

vec_list = list(vec)
vec_array = array.array('f', vec_list)

# 2. Run Query (using f-string for uid to avoid ORA-01745 ambiguity)
# Note: we still bind vec because it's a vector
print(f"Checking top 5 for '{anchor_text}'...")

try:
    cur.execute(f"""
        SELECT id, title, VECTOR_DISTANCE(VEC_EMBEDDING, :vec, COSINE) as distance
        FROM TOMEHUB_CONTENT
        WHERE firebase_uid = '{uid}'
        AND VEC_EMBEDDING IS NOT NULL
        ORDER BY distance
        FETCH FIRST 5 ROWS ONLY
    """, {"vec": vec_array})

    results = cur.fetchall()
    for row in results:
        distance = row[2]
        similarity = 1 - distance if distance else 0
        print(f"  Sim: {similarity:.4f} | Title: {row[1][:40]}")

except Exception as e:
    print(f"Query failed: {e}")

conn.close()
