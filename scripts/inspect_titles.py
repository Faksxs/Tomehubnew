
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def inspect_missing_vectors():
    print("→ Inspecting 181 items with missing vectors...")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Kaynak Tipi ve Kategori Dağılımı
                # Not: PERSONAL_NOTE olanların kategorisini de kontrol ediyoruz
                cursor.execute("""
                    SELECT c.content_type, l.item_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT_V2 c
                    LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                    WHERE c.vec_embedding IS NULL AND c.AI_ELIGIBLE = 1
                    GROUP BY c.content_type, l.item_type
                """)
                distribution = cursor.fetchall()
                print("\n--- DAĞILIM (Eksik Vektörler) ---")
                for row in distribution:
                    print(f"İçerik: {row[0]}, Kütüphane Tipi: {row[1]}, Adet: {row[2]}")

                # 2. Rastgele Örnekler (Başlık ve İçerik Özeti)
                cursor.execute("""
                    SELECT c.title, c.content_chunk, c.content_type, l.item_type
                    FROM TOMEHUB_CONTENT_V2 c
                    LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                    WHERE c.vec_embedding IS NULL AND c.AI_ELIGIBLE = 1
                    FETCH FIRST 5 ROWS ONLY
                """)
                samples = cursor.fetchall()
                print("\n--- RASTGELE ÖRNEKLER ---")
                for s in samples:
                    content_preview = s[1][:80].replace('\n', ' ') if s[1] else "BOŞ"
                    print(f"📌 [{s[2]}/{s[3]}] Başlık: {s[0]} \n   Özet: {content_preview}...\n")

    except Exception as e:
        print(f"\n❌ Inspection Failed: {e}")

if __name__ == "__main__":
    inspect_missing_vectors()
