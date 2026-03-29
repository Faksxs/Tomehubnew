
import sys
import os
import array
from typing import List, Dict

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager
from services.embedding_service import batch_get_embeddings

def backfill_missing_embeddings():
    print("→ Starting Re-embedding process for 181 items...")
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Eksik olanları çek
                cursor.execute("""
                    SELECT id, content_chunk 
                    FROM TOMEHUB_CONTENT_V2 
                    WHERE vec_embedding IS NULL AND AI_ELIGIBLE = 1
                    ORDER BY id
                """)
                rows = cursor.fetchall()
                if not rows:
                    print("✅ No missing embeddings found.")
                    return

                total = len(rows)
                print(f"→ Found {total} items to process.")

                # 2. Embedding'leri oluştur (Yeni batch motoruyla)
                ids = [r[0] for r in rows]
                texts = [r[1] for r in rows]
                
                print("→ Calling Gemini API (via new chunked batch engine)...")
                embeddings = batch_get_embeddings(texts)
                
                # 3. Veritabanını güncelle
                print("→ Updating database with new vectors...")
                success_count = 0
                for i, emb in enumerate(embeddings):
                    if emb is not None:
                        # Oracle VECTOR tipine yazmak için array formatı gerekebilir
                        # oracledb kütüphanesi list veya array.array kabul eder
                        cursor.execute("""
                            UPDATE TOMEHUB_CONTENT_V2 
                            SET vec_embedding = :p_vec 
                            WHERE id = :p_id
                        """, {"p_vec": list(emb), "p_id": ids[i]})
                        success_count += 1
                
                conn.commit()
                print(f"\n✅ SUCCESS: {success_count}/{total} items re-embedded and updated.")

    except Exception as e:
        print(f"\n❌ Backfill Failed: {e}")

if __name__ == "__main__":
    backfill_missing_embeddings()
