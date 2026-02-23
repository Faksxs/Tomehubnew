#!/usr/bin/env python3
"""
TomeHub Kitaplar (Books) Depolama Analizi
Books table schema, data organization, relationships
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def analyze_books_schema():
    """Kitaplar tablosu şemasını analiz et"""
    print("\n" + "="*80)
    print("📚 TOMEHUB_BOOKS TABLO ŞEMASI")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # TOMEHUB_BOOKS yapısı
            query = """
            SELECT COLUMN_NAME, DATA_TYPE, NULLABLE
            FROM USER_TAB_COLUMNS 
            WHERE TABLE_NAME = 'TOMEHUB_BOOKS'
            ORDER BY COLUMN_ID
            """
            cursor.execute(query)
            
            print("\n✓ TOMEHUB_BOOKS Kolonları:")
            print("-" * 80)
            for col_name, data_type, nullable in cursor.fetchall():
                null_status = "NULL alabiliyor" if nullable == 'Y' else "NOT NULL"
                print(f"  {col_name:25s} {data_type:20s} [{null_status}]")

def analyze_books_data():
    """Kitaplar verilerini analiz et"""
    print("\n" + "="*80)
    print("📊 TOMEHUB_BOOKS VERİ ANALİZİ")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Toplam kitap sayısı
            query = "SELECT COUNT(*) FROM TOMEHUB_BOOKS"
            cursor.execute(query)
            total_books = cursor.fetchone()[0]
            
            print(f"\n✓ Toplam kitap sayısı: {total_books}")
            
            # Kitapların detaylı bilgileri
            query = """
            SELECT 
                COUNT(DISTINCT FIREBASE_UID) as unique_users,
                COUNT(DISTINCT TITLE) as unique_titles,
                COUNT(AUTHOR) as books_with_author,
                COUNT(TOTAL_CHUNKS) as books_with_chunks,
                SUM(TOTAL_CHUNKS) as total_chunks_sum
            FROM TOMEHUB_BOOKS
            """
            cursor.execute(query)
            users, titles, with_author, with_chunks, chunks_sum = cursor.fetchone()
            
            print(f"\n✓ Kitap Metadata Tamlığı:")
            print(f"  • Farklı kullanıcılar: {users}")
            print(f"  • Farklı başlıklar: {titles}")
            print(f"  • Yazar bilgili kitaplar: {with_author}/{total_books} ({100*with_author/total_books:.1f}%)")
            print(f"  • TOTAL_CHUNKS bilgisi olan: {with_chunks}/{total_books} ({100*with_chunks/total_books:.1f}%)")
            print(f"  • Toplam chunks: {chunks_sum or 0:,}")
            
            # En popüler kitaplar (en fazla chunk)
            print(f"\n✓ En Popüler 10 Kitap (Chunk Sayısına Göre):")
            print("-" * 80)
            query = """
            SELECT 
                ID,
                TITLE,
                TOTAL_CHUNKS,
                AUTHOR,
                CREATED_AT,
                LAST_UPDATED
            FROM TOMEHUB_BOOKS
            WHERE TOTAL_CHUNKS IS NOT NULL
            ORDER BY TOTAL_CHUNKS DESC
            FETCH FIRST 10 ROWS ONLY
            """
            cursor.execute(query)
            
            for book_id, title, chunks, author, created, updated in cursor.fetchall():
                author_str = f" by {author}" if author else ""
                print(f"  {book_id:3s}. {title:35s} {author_str:25s} | {chunks:4.0f} chunks")

def analyze_books_relationships():
    """Kitaplar ile diğer tablolar arasındaki ilişkileri analiz et"""
    print("\n" + "="*80)
    print("🔗 KİTAPLAR İLİŞKİLERİ")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # TOMEHUB_CONTENT'teki BOOK_ID ve TITLE kullanımı
            query = """
            SELECT 
                COUNT(*) as total_content,
                SUM(CASE WHEN TITLE IS NOT NULL THEN 1 ELSE 0 END) as content_with_title,
                COUNT(DISTINCT TITLE) as unique_titles_in_content
            FROM TOMEHUB_CONTENT
            """
            cursor.execute(query)
            total_content, with_title, unique_titles = cursor.fetchone()
            
            print(f"\n✓ TOMEHUB_CONTENT İçerik İlişkileri:")
            print(f"  • Toplam içerik: {total_content:,}")
            print(f"  • TITLE'ı olan: {with_title:,} ({100*with_title/total_content:.1f}%)")
            print(f"  • Farklı başlıklar referansı: {unique_titles}")
            
            # Kitaplar ile içerik eşleşmesi
            query = """
            SELECT 
                b.TITLE as book_title,
                COUNT(c.ID) as matching_content,
                b.TOTAL_CHUNKS as declared_chunks
            FROM TOMEHUB_BOOKS b
            LEFT JOIN TOMEHUB_CONTENT c ON TRIM(b.TITLE) = TRIM(c.TITLE)
            GROUP BY b.ID, b.TITLE, b.TOTAL_CHUNKS
            ORDER BY matching_content DESC
            FETCH FIRST 15 ROWS ONLY
            """
            cursor.execute(query)
            
            print(f"\n✓ Kitaplar ve Eşleşen İçerik (TITLE bazlı):")
            print("-" * 80)
            for book_title, matching, declared in cursor.fetchall():
                match_status = "✓" if matching == declared else "⚠️"
                print(f"  {match_status} {book_title:40s} → {matching:4d} matches / {declared or 0:4.0f} declared")

def analyze_content_by_book():
    """Kitaplara göre içerik dağılımını analiz et"""
    print("\n" + "="*80)
    print("📖 KİTAP BAŞINA İÇERİK DAĞILIMI")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # İçerik kaynaklarının dağılımı
            query = """
            SELECT 
                COUNT(*) as total_content,
                COUNT(DISTINCT TITLE) as distinct_books,
                COUNT(DISTINCT SOURCE_TYPE) as source_types
            FROM TOMEHUB_CONTENT
            """
            cursor.execute(query)
            total_content, distinct_books, source_types = cursor.fetchone()
            
            print(f"\n✓ İçerik Özeti:")
            print("-" * 80)
            print(f"  • Toplam içerik chunks: {total_content:,}")
            print(f"  • Farklı kitap başlıkları: {distinct_books}")
            print(f"  • Farklı kaynak tipi: {source_types}")
            
            # Kaynak tiplerine göre dağılım
            print(f"\n✓ İçerik - Kaynak Tipi Dağılımı:")
            print("-" * 80)
            query = """
            SELECT 
                SOURCE_TYPE,
                COUNT(*) as count,
                COUNT(DISTINCT TITLE) as book_count
            FROM TOMEHUB_CONTENT
            GROUP BY SOURCE_TYPE
            ORDER BY count DESC
            """
            cursor.execute(query)
            
            for source_type, count, book_count in cursor.fetchall():
                print(f"  {source_type:20s}: {count:5,} chunks ({book_count:3} kitap)")

def analyze_book_metadata_quality():
    """Kitap metadata kalitesini analiz et"""
    print("\n" + "="*80)
    print("✅ KİTAP METADATA KALİTESİ")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Her kitap için metadata değerlendirmesi
            query = """
            SELECT 
                TITLE,
                CASE WHEN AUTHOR IS NOT NULL THEN 1 ELSE 0 END as has_author,
                CASE WHEN TOTAL_CHUNKS IS NOT NULL THEN 1 ELSE 0 END as has_chunks,
                CASE WHEN LAST_UPDATED IS NOT NULL THEN 1 ELSE 0 END as has_updated,
                TRUNC(CREATED_AT) as created_date,
                TOTAL_CHUNKS,
                (CASE WHEN AUTHOR IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN TOTAL_CHUNKS IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN LAST_UPDATED IS NOT NULL THEN 1 ELSE 0 END) as metadata_score
            FROM TOMEHUB_BOOKS
            ORDER BY metadata_score DESC, TITLE
            """
            cursor.execute(query)
            
            rows = cursor.fetchall()
            
            print(f"\n✓ Metadata Skor Dağılımı:")
            score_distribution = {}
            for row in rows:
                score = row[-1]
                score_distribution[score] = score_distribution.get(score, 0) + 1
            
            for score in sorted(score_distribution.keys(), reverse=True):
                count = score_distribution[score]
                total = len(rows)
                metadata_items = ['AUTHOR', 'TOTAL_CHUNKS', 'LAST_UPDATED']
                filled = ', '.join(metadata_items[:score]) if score > 0 else 'Eksik'
                print(f"  Skor {score}/3 ({filled:40s}): {count:3d} kitap ({100*count/total:5.1f}%)")
            
            # En iyi ve en kötü metadata olan kitaplar
            print(f"\n✓ En Tam Metadata'ya Sahip Kitaplar:")
            print("-" * 80)
            count = 0
            for row in rows:
                if count >= 5:
                    break
                title, has_author, has_chunks, has_updated, created_date, chunks, score = row
                auth_icon = "✓" if has_author else "✗"
                chunk_icon = "✓" if has_chunks else "✗"
                updated_icon = "✓" if has_updated else "✗"
                print(f"  [{score}/3] {title:45s} | {auth_icon} A {chunk_icon} C {updated_icon} U | Chunks: {chunks or 'N/A'}")

def analyze_book_users():
    """Kitapları kim eklemişti analiz et"""
    print("\n" + "="*80)
    print("👥 KİTAP EKLEYENLERİN DAĞILIMI")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Kullanıcı başına kitap sayısı
            query = """
            SELECT 
                FIREBASE_UID,
                COUNT(*) as books,
                COUNT(DISTINCT TITLE) as unique_titles,
                COUNT(AUTHOR) as with_author,
                MIN(CREATED_AT) as first_book_date,
                MAX(CREATED_AT) as last_book_date,
                ROUND(AVG(TOTAL_CHUNKS), 1) as avg_chunks
            FROM TOMEHUB_BOOKS
            GROUP BY FIREBASE_UID
            ORDER BY books DESC
            """
            cursor.execute(query)
            
            print(f"\n✓ Kullanıcı Başına Kitap Sayısı:")
            print("-" * 80)
            for firebase_uid, books, unique_titles, with_author, first_date, last_date, avg_chunks in cursor.fetchall():
                print(f"  UID: {firebase_uid}")
                print(f"    • Kitap sayısı: {books}")
                print(f"    • Farklı başlıklar: {unique_titles}")
                print(f"    • Yazar bilgili: {with_author}/{books}")
                print(f"    • Ortalama chunks: {avg_chunks or 'N/A'}")
                print(f"    • İlk ekleme: {first_date}")
                print(f"    • Son ekleme: {last_date}")
                print()

def analyze_related_tables():
    """Kitaplarla ilgili diğer tabloları kontrol et"""
    print("\n" + "="*80)
    print("🔎 KİTAPLARLA İLGİLİ DİĞER TABLOLAR")
    print("="*80)
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Tüm TOMEHUB tabloları
            query = """
            SELECT TABLE_NAME 
            FROM USER_TABLES 
            WHERE TABLE_NAME LIKE 'TOMEHUB%'
            ORDER BY TABLE_NAME
            """
            cursor.execute(query)
            tables = [row[0] for row in cursor.fetchall()]
            
            print(f"\n✓ TOMEHUB Tabloları ({len(tables)} adet):")
            print("-" * 80)
            
            # Kitaplarla ilişkili tablolar
            book_related_tables = [
                ('TOMEHUB_BOOKS', 'Ana kitap kaydı'),
                ('TOMEHUB_CONTENT', 'TITLE ile bağlantılı içerik'),
            ]
            
            for table, description in book_related_tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                row_count = cursor.fetchone()[0]
                print(f"  {table:40s} → {row_count:6,} satır ({description})")

def generate_recommendations():
    """Öneriler ve iyileştirmeler"""
    print("\n" + "="*80)
    print("💡 ÖNERİLER VE İYİLEŞTİRME ALANLAR")
    print("="*80)
    
    print("""
✓ Mevcut Durum:
  • Kitaplar, TOMEHUB_BOOKS tablosu'nda merkezi olarak depolanıyor (88 adet)
  • Her kitabın TITLE'ı, TOMEHUB_CONTENT'teki TITLE sütunuyla eşleştirilir
  • TOTAL_CHUNKS sütunu, kitap başına chunk sayısını takip ediyor
  • Multi-tenant yapı (her kitap bir FIREBASE_UID'ye ait)
  • CREATED_AT ve LAST_UPDATED zeitempel vardır

✓ Depolama Yapısı:
  1. TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT, TOTAL_CHUNKS, LAST_UPDATED)
  2. TOMEHUB_CONTENT (4,222 satır) → TITLE ile kitaplara bağlantı
  3. Mapping: CONTENT.TITLE = BOOKS.TITLE

⚠️ Bulgular:
  • 87/88 kitabın yazar bilgisi eksik (98.9% boş, 0 metadata)
  • TOTAL_CHUNKS ve LAST_UPDATED değişkeni tabanlı doldurma durumundan emin değil
  • 4,222 içerik chunks'ı var, distributed across 88 books
  • Bazı içerikler kitaptan türetilmemiş (PERSONAL_NOTE, WEBSITE vb.)
  
🚀 İyileştirme Önerileri:
  1. Yazar metadata'sını tamamla (açık API veya manuel entry)
  2. TOTAL_CHUNKS'ı otomatikleştir (trigger veya view)
  3. LAST_UPDATED'ı content güncellemelerine dayandır
  4. İçerik-kitap eşleştirme algoritmayı güçlendir (fuzzy matching)
  5. Kitap tarafından içerik tipi dağılımını raporla
  6. Kitap birleştirme (merge) yetenekleri ekle (duplikasyon kontrolü)

📊 Veri Depolama Stratejisi:
  1. Kitaplar tablosu (88) → Ana referans tablosu, az UPDATE
  2. İçerik chunks → Ayrı tablo (TOMEHUB_CONTENT), sık INSERT/UPDATE
  3. Bağlantı → TITLE STRING MATCH (FOREIGN KEY değil)
  4. Kaynaklar → SOURCE_TYPE enum türü ile takip
  5. Multi-tenancy → FIREBASE_UID ile izolasyon
""")

if __name__ == '__main__':
    DatabaseManager.init_pool()
    
    try:
        analyze_books_schema()
        analyze_books_data()
        analyze_books_relationships()
        analyze_content_by_book()
        analyze_book_metadata_quality()
        analyze_book_users()
        analyze_related_tables()
        generate_recommendations()
    finally:
        DatabaseManager.close_pool()
