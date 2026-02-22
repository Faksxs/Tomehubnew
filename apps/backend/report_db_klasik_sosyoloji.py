import os
import sys

# Add apps/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def report_klasik_sosyoloji():
    print("==================================================")
    print("VERİTABANI KİRLİLİK RAPORU: 'Klasik Sosyoloji'")
    print("==================================================")
    
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Check TOMEHUB_BOOKS
                print("\n1. TOMEHUB_BOOKS TABLOSU (Ana Kitap Kayıtları)")
                cursor.execute('''
                    SELECT id, title, firebase_uid, created_at 
                    FROM TOMEHUB_BOOKS 
                    WHERE title LIKE '%Klasik%Sosyoloji%' OR title LIKE '%Sosyoloji%Tarihi%'
                    ORDER BY created_at DESC
                ''')
                books = cursor.fetchall()
                if not books:
                    print("Hiç kayıt bulunamadı.")
                for b in books:
                    print(f"  - Kitap ID: {b[0]} | Başlık: {b[1]} | UID: {b[2]} | Tarih: {b[3]}")

                # 2. Check TOMEHUB_INGESTED_FILES
                print("\n2. TOMEHUB_INGESTED_FILES TABLOSU (PDF Yükleme İşlemleri)")
                cursor.execute('''
                    SELECT book_id, source_file_name, status, chunk_count, embedding_count, updated_at 
                    FROM TOMEHUB_INGESTED_FILES 
                    WHERE source_file_name LIKE '%Klasik%' OR source_file_name LIKE '%Sosyoloji%'
                    OR book_id IN (
                        SELECT id FROM TOMEHUB_BOOKS WHERE title LIKE '%Klasik%Sosyoloji%' OR title LIKE '%Sosyoloji%Tarihi%'
                    )
                    ORDER BY updated_at DESC
                ''')
                files = cursor.fetchall()
                if not files:
                    print("Hiç kayıt bulunamadı.")
                for f in files:
                    print(f"  - Kitap ID: {f[0]} | Dosya: {f[1]} | Durum: {f[2]} | Chunk: {f[3]} | Embed: {f[4]} | Tarih: {f[5]}")

                # 3. Check TOMEHUB_CONTENT
                print("\n3. TOMEHUB_CONTENT TABLOSU (İşlenmiş Parçalar/Chunks)")
                cursor.execute('''
                    SELECT book_id, title, source_type, count(*), sum(case when vec_embedding is not null then 1 else 0 end)
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE '%Klasik%Sosyoloji%' OR title LIKE '%Sosyoloji%Tarihi%'
                    GROUP BY book_id, title, source_type
                ''')
                chunks = cursor.fetchall()
                if not chunks:
                    print("Hiç kayıt bulunamadı.")
                for c in chunks:
                    print(f"  - Kitap ID: {c[0]} | Başlık: {c[1]} | Tip: {c[2]} | Toplam Parça: {c[3]} | İşlenmiş Parça (Embed): {c[4]}")
                    
                # 4. Inconsistency Analysis
                print("\n--- ANALİZ ÖZETİ ---")
                
                # Check for orphaned chunks (chunks without a book)
                book_ids_in_books = {b[0] for b in books}
                book_ids_in_content = {c[0] for c in chunks}
                orphaned_ids = book_ids_in_content - book_ids_in_books
                
                if orphaned_ids:
                    print(f"\n[UYARI] TOMEHUB_BOOKS'ta kaydı sildiği halde TOMEHUB_CONTENT'ta parçaları kalan yetim (orphan) kayıtlar var: {orphaned_ids}")
                else:
                    print("\n[BİLGİ] Yetim (orphan) içerik parçası YOK (Veritabanı tutarlı).")
                    
                if len(books) > 1:
                    print(f"\n[UYARI] TOMEHUB_BOOKS tablosunda bu kitaba ait {len(books)} farklı kayıt var. (Veritabanı kirliliği)")
                
                if len(files) > 1:
                    print(f"\n[UYARI] TOMEHUB_INGESTED_FILES tablosunda bu kitaba ait {len(files)} farklı yükleme denemesi var.")

    except Exception as e:
        print(f"HATA: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    report_klasik_sosyoloji()
