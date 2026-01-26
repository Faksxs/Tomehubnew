
import os
import sys
import oracledb
import time

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager
from services.embedding_service import get_embedding

load_dotenv()

TARGET_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
EMAIL_UID = 'aksoyfeth@gmail.com'

def fix_data():
    print("="*60)
    print("DATA REPAIR TOOL")
    print("="*60)
    
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Analyze Data
        print(f"\n[ANALYSIS] Checking UID: {TARGET_UID}")
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": TARGET_UID})
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid AND vec_embedding IS NOT NULL", {"p_uid": TARGET_UID})
        with_emb = cursor.fetchone()[0]
        
        print(f"  Total Chunks: {total}")
        print(f"  With Embeddings: {with_emb}")
        print(f"  Missing Embeddings: {total - with_emb}")
        
        # Check target UID (Email)
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": EMAIL_UID})
        email_total = cursor.fetchone()[0]
        print(f"  Existing count for {EMAIL_UID}: {email_total}")

        # 2. Fix Embeddings
        missing = total - with_emb
        if missing > 0:
            print(f"\n[FIX] Found {missing} chunks without embeddings. Repairing...")
            
            # Fetch actual NULLs
            cursor.execute("""
                SELECT rowid, content_chunk, title
                FROM TOMEHUB_CONTENT 
                WHERE firebase_uid = :p_uid AND vec_embedding IS NULL
            """, {"p_uid": TARGET_UID})
            
            rows = cursor.fetchall()
            print(f"  Fetched {len(rows)} rows to repair.")
            
            repaired = 0
            for row in rows:
                rid, text, title = row
                try:
                    if not text: 
                        continue
                        
                    emb = get_embedding(text)
                    if emb:
                        cursor.execute("UPDATE TOMEHUB_CONTENT SET vec_embedding = :p_vec WHERE rowid = :p_rid", {"p_vec": emb, "p_rid": rid})
                        repaired += 1
                        if repaired % 10 == 0:
                            conn.commit()
                            print(f"    Repaired {repaired}...")
                            time.sleep(0.5) 
                except Exception as e:
                    print(f"    Failed to repair {title}: {e}")
            
            conn.commit()
            print(f"  [SUCCESS] Repaired {repaired} chunks.")
        else:
            print("\n[OK] All chunks have embeddings.")

        # 3. Migration (If needed)
        # Assuming frontend passes Email, and we have data on UID, let's copy/move.
        # But let's verify if user has NO data on Email first.
        if total > 0 and email_total == 0:
            print("\n[MIGRATION REQUIRED]")
            print(f"Moving {total} items from {TARGET_UID} to {EMAIL_UID}")
            
            # Perform update
            cursor.execute("""
                UPDATE TOMEHUB_CONTENT 
                SET firebase_uid = :p_new_uid 
                WHERE firebase_uid = :p_old_uid
            """, {"p_new_uid": EMAIL_UID, "p_old_uid": TARGET_UID})
            count = cursor.rowcount
            conn.commit()
            print(f"  [SUCCESS] Migrated {count} rows.")
            
        elif email_total > 0:
            print("\n[INFO] Data already exists for email address. Migration skipped.")

if __name__ == "__main__":
    try:
        fix_data()
    except Exception as e:
        print(f"FATAL: {e}")
