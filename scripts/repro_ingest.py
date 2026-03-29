
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def check_ingestion_failures():
    print("→ Investigating ingestion and embedding lifecycle...")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Hürriyet Üstüne kitabının eklenme zamanını bulalım
                cursor.execute("""
                    SELECT item_id, created_at 
                    FROM TOMEHUB_LIBRARY_ITEMS 
                    WHERE title LIKE '%Hürriyet Üstüne%'
                """)
                item_data = cursor.fetchone()
                if not item_data:
                    print("Kitap bulunamadı.")
                    return
                
                item_id, created_at = item_data
                print(f"Kitap ID: {item_id}, Eklenme Zamanı: {created_at}")

                # 2. Bu ITEM_ID ile ilgili hata loglarını (INGESTION_EVENTS) sorgulayalım
                # Not: Tablo ismini ve kolonları tahmin ediyoruz, önce bir hata olursa düzelteceğiz
                print("\n→ Checking Ingestion Events for errors...")
                cursor.execute("""
                    SELECT event_type, status, error_message, created_at 
                    FROM TOMEHUB_INGESTION_EVENTS 
                    WHERE item_id = :iid
                    ORDER BY created_at DESC
                """, {"iid": item_id})
                logs = cursor.fetchall()
                if logs:
                    for l in logs:
                        print(f"[{l[3]}] Tip: {l[0]}, Statü: {l[1]}, Hata: {l[2]}")
                else:
                    print("Bu kitap için özel bir hata kaydı bulunamadı.")

                # 3. Genel olarak son 24 saatteki EMBEDDING hatalarını tarayalım
                print("\n→ Checking overall EMBEDDING failures in the last 48 hours...")
                cursor.execute("""
                    SELECT error_message, COUNT(*) 
                    FROM TOMEHUB_INGESTION_EVENTS 
                    WHERE (event_type LIKE '%EMBEDDING%' OR event_type LIKE '%VECTOR%')
                      AND status = 'FAILED'
                    GROUP BY error_message
                """)
                fail_stats = cursor.fetchall()
                for f in fail_stats:
                    print(f"Hata: {f[0]} | Adet: {f[1]}")

    except Exception as e:
        print(f"\n❌ Fail Investigation Failed: {e}")

if __name__ == "__main__":
    check_ingestion_failures()
