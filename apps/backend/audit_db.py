
import sys
import os
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def efficiency_audit():
    print("→ Auditing Database Efficiency and Legacy Structures...")
    results = {
        "orphaned_content_count": 0,
        "legacy_tables": [],
        "backup_tables": [],
        "null_vectors_count": 0,
        "index_stats": []
    }
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Yetim İçerik Kontrolü (Orphaned Chunks)
                # LIBRARY_ITEMS'da olmayan ITEM_ID'ler CONTENT_V2'yi yoruyor mu?
                cursor.execute("""
                    SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2 c
                    WHERE NOT EXISTS (
                        SELECT 1 FROM TOMEHUB_LIBRARY_ITEMS l 
                        WHERE l.item_id = c.item_id
                    ) AND c.content_type NOT IN ('PERSONAL_NOTE', 'NOTES')
                """)
                results["orphaned_content_count"] = cursor.fetchone()[0]
                
                # 2. Boş Vektör Kontrolü (Null Vectors)
                # Aramada hesaba katılan ama vektörü olmayan satırlar latency yaratır
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2 WHERE vec_embedding IS NULL AND AI_ELIGIBLE = 1")
                results["null_vectors_count"] = cursor.fetchone()[0]
                
                # 3. Hiç Kullanılmayan (0 Satırlı) Tablolar
                cursor.execute("SELECT table_name FROM user_tables WHERE num_rows = 0 OR num_rows IS NULL")
                results["legacy_tables"] = [r[0] for r in cursor.fetchall() if not r[0].startswith(('DR$', 'VECTOR$'))]
                
                # 4. Yedekleme Tabloları
                cursor.execute("SELECT table_name, num_rows FROM user_tables WHERE table_name LIKE 'TH_BKP_%'")
                results["backup_tables"] = [{"name": r[0], "rows": r[1]} for r in cursor.fetchall()]
                
                # 5. İndeks Kontrolü (Gürültü Yaratan İndeksler)
                cursor.execute("SELECT index_name, index_type, status FROM user_indexes WHERE status != 'VALID'")
                results["invalid_indexes"] = [{"name": r[0], "type": r[1]} for r in cursor.fetchall()]

        # Analizi yazdır
        print_audit_report(results)

    except Exception as e:
        print(f"\n❌ Efficiency Audit Failed: {e}")

def print_audit_report(res):
    print("\n=== VERİTABANI VERİMLİLİK DENETİMİ ===")
    print(f"❌ Yetim İçerik (Silinmiş Kaynak Kalıntısı): {res['orphaned_content_count']} satır")
    print(f"⚠️ Vektörü Olmayan AI İçeriği: {res['null_vectors_count']} satır")
    print(f"🧹 Temizlenebilir Yedek Tablo Sayısı: {len(res['backup_tables'])}")
    print(f"📉 Hiç Kullanılmayan (Legacy) Tablo Sayısı: {len(res['legacy_tables'])}")
    
    # Detaylı Rapor Dosyası
    with open("apps/backend/audit_report_db.md", "w", encoding="utf-8") as f:
        f.write("# Veritabanı Temizlik ve Optimizasyon Raporu\n\n")
        f.write(f"## 1. Kritik Sorunlar\n")
        f.write(f"*   **Yetim Kayıtlar:** {res['orphaned_content_count']} adet içerik parçası kütüphanede karşılığı olmadığı halde veritabanında yer kaplıyor. Bu, arama sırasında sistemin boş yere bu satırları taramasına neden olur.\n")
        f.write(f"*   **Eksik Vektörler:** {res['null_vectors_count']} satır 'AI_ELIGIBLE' olarak işaretlenmiş ama anlamsal karşılığı (embedding) yok. Bu, arama kalitesini düşürür.\n\n")
        f.write(f"## 2. Gereksiz Tablolar (Silinebilir)\n")
        for t in res['legacy_tables']:
            f.write(f"*   `{t}` (0 satır)\n")
        f.write("\n## 3. Yedekleme Yükü\n")
        for b in res['backup_tables']:
            f.write(f"*   `{b['name']}` ({b['rows']} satır)\n")

if __name__ == "__main__":
    efficiency_audit()
