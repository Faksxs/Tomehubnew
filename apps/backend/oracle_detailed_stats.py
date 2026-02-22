from infrastructure.db_manager import DatabaseManager
import oracledb

try:
    # Database Pool'ı başlat
    DatabaseManager.init_pool()
    
    # Read pool'dan bağlantı al
    conn = DatabaseManager._read_pool.acquire()
    cursor = conn.cursor()
    
    print('=' * 100)
    print('ORACLE 23AI VERİTABANI - DETAYLI ANALİZ')
    print('=' * 100)
    print()
    
    # 1. Oracle Sürümü ve Bilgileri
    print('🗄️  ORACLE VERİTABANI BİLGİLERİ:')
    cursor.execute("SELECT * FROM V$VERSION WHERE BANNER LIKE 'Oracle%'")
    version = cursor.fetchone()
    if version:
        print(f'   {version[0]}')
    print()
    
    # 2. Database Name ve Properties
    cursor.execute("SELECT NAME, CREATED FROM V$DATABASE")
    db_info = cursor.fetchone()
    if db_info:
        print(f'   Database Name: {db_info[0]}')
        print(f'   Created: {db_info[1]}')
    print()
    
    # 3. Tablo Boyutları (TOMEHUB tablolar)
    print('📏 TOMEHUB TABLOLARININ BOYUTU:')
    cursor.execute("""
        SELECT 
            SEGMENT_NAME,
            ROUND(SUM(BYTES)/1024/1024, 2) as SIZE_MB
        FROM USER_SEGMENTS
        WHERE SEGMENT_TYPE='TABLE' AND SEGMENT_NAME LIKE 'TOMEHUB%'
        GROUP BY SEGMENT_NAME
        ORDER BY SUM(BYTES) DESC
    """)
    for table_name, size_mb in cursor.fetchall():
        print(f'   {table_name:25} : {size_mb:10.2f} MB')
    print()
    
    # 4. Index Bilgileri
    print('📑 INDEX BİLGİLERİ (TOMEHUB):')
    cursor.execute("""
        SELECT 
            INDEX_NAME,
            TABLE_NAME,
            UNIQUENESS
        FROM USER_INDEXES
        WHERE TABLE_NAME LIKE 'TOMEHUB%'
        ORDER BY TABLE_NAME, INDEX_NAME
    """)
    indexes = cursor.fetchall()
    if indexes:
        for idx_name, tbl_name, uniqueness in indexes:
            print(f'   {idx_name:30} on {tbl_name:20} [{uniqueness}]')
    else:
        print('   Hiçbir index bulunamadı')
    print()
    
    # 5. Tablespace Bilgileri
    print('💾 TABLESPACE BİLGİLERİ:')
    cursor.execute("""
        SELECT 
            TABLESPACE_NAME,
            ROUND(SUM(BYTES)/1024/1024, 2) as USED_MB,
            ROUND(SUM(BYTES)/1024/1024/1024, 2) as USED_GB
        FROM USER_SEGMENTS
        GROUP BY TABLESPACE_NAME
        ORDER BY SUM(BYTES) DESC
    """)
    for ts_name, used_mb, used_gb in cursor.fetchall():
        print(f'   {ts_name:20} : {used_gb:8.2f} GB ({used_mb:10.2f} MB)')
    print()
    
    # 6. Vector Embedding Bilgileri (768-dimensional)
    print('🔢 VECTORİZATİON BİLGİLERİ:')
    cursor.execute("""
        SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE VEC_EMBEDDING IS NOT NULL
    """)
    vectorized = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
    total_content = cursor.fetchone()[0]
    
    vector_coverage = (vectorized / total_content * 100) if total_content > 0 else 0
    print(f'   Vektörize edilmiş içerik: {vectorized:,} / {total_content:,} ({vector_coverage:.1f}%)')
    print(f'   Embedding Dimension: 768-D (FLOAT32)')
    print(f'   Model: Google Gemini text-embedding-004')
    print()
    
    # 7. Session/Connection Bilgileri
    print('🔌 AKTIF SESSION BİLGİLERİ:')
    cursor.execute("SELECT COUNT(*) FROM V$SESSION WHERE TYPE='USER'")
    active_sessions = cursor.fetchone()[0]
    print(f'   Aktif User Sessions: {active_sessions}')
    print()
    
    # 8. Performance Stats
    print('⚡ ORACLE PERFORMANCE INDICATORS:')
    cursor.execute("SELECT VALUE FROM V$PARAMETER WHERE NAME='db_recovery_file_dest_size'")
    result = cursor.fetchone()
    if result and result[0]:
        print(f'   Recovery Dest Size: {result[0]}')
    
    cursor.execute("SELECT VALUE FROM V$PARAMETER WHERE NAME='processes'")
    result = cursor.fetchone()
    if result and result[0]:
        print(f'   Max Processes: {result[0]}')
    print()
    
    # 9. Character Set
    print('🔤 CHARACTER SET:')
    cursor.execute("SELECT VALUE FROM NLS_DATABASE_PARAMETERS WHERE PARAMETER='NLS_CHARACTERSET'")
    charset = cursor.fetchone()
    if charset:
        print(f'   {charset[0]}')
    print()
    
    print('=' * 100)
    print('✅ Oracle 23ai Veritabanı Başarıyla Analiz Edildi')
    print('=' * 100)
    
    conn.close()
    
except Exception as e:
    print(f'❌ HATA: {str(e)}')
    import traceback
    traceback.print_exc()
