from infrastructure.db_manager import DatabaseManager

try:
    # Database Pool'ı başlat
    DatabaseManager.init_pool()
    
    # Read pool'dan bağlantı al
    conn = DatabaseManager._read_pool.acquire()
    cursor = conn.cursor()
    
    print('=' * 80)
    print('TOMEHUB VERİTABANI İSTATİSTİKLERİ')
    print('=' * 80)
    print()
    
    # 1. Toplam Content Sayısı
    cursor.execute('SELECT COUNT(*) FROM TOMEHUB_CONTENT')
    total = cursor.fetchone()[0]
    print(f'📊 TOPLAM İÇERİK: {total:,}')
    print()
    
    # 2. Kaynak Türüne Göre Dağılım
    print('📋 KAYNAK TÜRÜNE GÖRE DAĞILIM:')
    cursor.execute('''
        SELECT SOURCE_TYPE, COUNT(*) as cnt 
        FROM TOMEHUB_CONTENT 
        GROUP BY SOURCE_TYPE 
        ORDER BY cnt DESC
    ''')
    for source_type, cnt in cursor.fetchall():
        print(f'   {source_type:15} : {cnt:8,}')
    print()
    
    # 3. Toplam Kullanıcı (Firebase UID)
    cursor.execute('SELECT COUNT(DISTINCT FIREBASE_UID) FROM TOMEHUB_CONTENT')
    users = cursor.fetchone()[0]
    print(f'👥 TOPLAM KULLANICI (UID): {users}')
    print()
    
    # 4. Concept Sayısı
    cursor.execute('SELECT COUNT(*) FROM TOMEHUB_CONCEPTS')
    concepts = cursor.fetchone()[0]
    print(f'💡 TOPLAM CONCEPT: {concepts:,}')
    print()
    
    # 5. Relations (İlişkiler)
    cursor.execute('SELECT COUNT(*) FROM TOMEHUB_RELATIONS')
    relations = cursor.fetchone()[0]
    print(f'🔗 TOPLAM İLİŞKİ: {relations:,}')
    print()
    
    # 6. Flow Seen (Görülmüş Kaynaklar)
    cursor.execute('SELECT COUNT(*) FROM TOMEHUB_FLOW_SEEN')
    flow_seen = cursor.fetchone()[0]
    print(f'👁️  GÖRÜLMÜŞ KAYNAKLAR: {flow_seen:,}')
    print()
    
    # 7. Search Logs
    cursor.execute('SELECT COUNT(*) FROM TOMEHUB_SEARCH_LOGS')
    logs = cursor.fetchone()[0]
    print(f'🔍 ARAMA KAYITLARI: {logs:,}')
    print()
    
    # 8. En Çok Kullanılan Kaynaklar (Kitaplar)
    print('📚 EN ÇOK KULLANILAN KİTAPLAR/KAYNAKLAR (Top 5):')
    cursor.execute('''
        SELECT TITLE, COUNT(*) as chunk_count
        FROM TOMEHUB_CONTENT
        WHERE TITLE IS NOT NULL
        GROUP BY TITLE
        ORDER BY chunk_count DESC
        FETCH FIRST 5 ROWS ONLY
    ''')
    for title, cnt in cursor.fetchall():
        print(f'   {title[:50]:50} : {cnt:5,} chunk')
    print()
    
    # 9. BOOK tablosundaki kitap sayısı
    try:
        cursor.execute('SELECT COUNT(*) FROM TOMEHUB_BOOKS')
        books = cursor.fetchone()[0]
        print(f'📖 TOPLAM KİTAP: {books:,}')
        print()
    except:
        pass
    
    print('=' * 80)
    
    conn.close()
    
except Exception as e:
    print(f'❌ HATA: {str(e)}')
    import traceback
    traceback.print_exc()
