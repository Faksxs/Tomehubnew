
import os
import sys
# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oracledb
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'

print(f"Checking data for UID: {UID}")
try:
    DatabaseManager.init_pool()
    with DatabaseManager.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check Total
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid", {"uid": UID})
        total = cursor.fetchone()[0]
        
        # Check Embeddings
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid AND vec_embedding IS NOT NULL", {"uid": UID})
        embeddings = cursor.fetchone()[0]
        
        # Check Lemmas
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid AND lemma_tokens IS NOT NULL", {"uid": UID})
        lemmas = cursor.fetchone()[0]
        
        print(f"Total Rows: {total}")
        print(f"Rows with Embeddings: {embeddings}")
        print(f"Rows with Lemmas: {lemmas}")

except Exception as e:
    print(f"Error: {e}")
