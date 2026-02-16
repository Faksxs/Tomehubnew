
import os
import sys
import logging
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)

# Add apps/backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager
from utils.text_utils import deaccent_text

def check_db_content():
    query = "zaman"
    firebase_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    
    print(f"--- Checking DB Content for '{query}' (UID: {firebase_uid}) ---")
    
    q_deaccented = deaccent_text(query)
    print(f"Deaccented term: '{q_deaccented}'")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 0. Check GLOBAL count
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
                global_docs = cursor.fetchone()[0]
                print(f"Global total documents: {global_docs}")

                # 1. Check TOTAL count for this user
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid", {"uid": firebase_uid})
                total_docs = cursor.fetchone()[0]
                print(f"Total documents for user: {total_docs}")
                
                # 2. Check Valid Source Types
                cursor.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT 
                    WHERE firebase_uid = :uid
                    GROUP BY source_type
                """, {"uid": firebase_uid})
                print("Source Types breakdown:")
                for row in cursor.fetchall():
                    print(f" - {row[0]}: {row[1]}")

                # 3. Check HIGHLIGHTS specifically
                print("Checking HIGHLIGHT counts...")
                cursor.execute("""
                    SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                    WHERE firebase_uid = :uid AND source_type = 'HIGHLIGHT'
                """, {"uid": firebase_uid})
                print(f"Highlights found: {cursor.fetchone()[0]}")

                # 4. Check PDF Exclusion impact
                print("Checking Non-PDF counts...")
                cursor.execute("""
                    SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                    WHERE firebase_uid = :uid 
                    AND source_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK')
                """, {"uid": firebase_uid})
                print(f"Non-PDF items found: {cursor.fetchone()[0]}")

                # 5. Run Search SQL with SAFE BINDING
                # 5. Minimal LIKE Check
                print("Running Minimal LIKE SQL...")
                sql = "SELECT id, source_type FROM TOMEHUB_CONTENT WHERE text_deaccented LIKE :p1 FETCH FIRST 5 ROWS ONLY"
                params = {"p1": f"%{q_deaccented}%"}
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                print(f"Minimal SQL Returned {len(rows)} rows.")
                
                print(f"Running Search SQL with params: {params}")
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                print(f"SQL Returned {len(rows)} rows.")
                for r in rows:
                    print(f"MATCH: {r[0]} | {r[1]} | {r[2]}")

    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    check_db_content()
