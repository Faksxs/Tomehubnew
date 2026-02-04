
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

def list_all_pdfs():
    print("🔍 Listing ALL PDF source types in DB...")
    
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT title, source_type 
                    FROM TOMEHUB_CONTENT 
                    WHERE source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    FETCH FIRST 20 ROWS ONLY
                """)
                rows = cursor.fetchall()
                
                if not rows:
                    print("❌ NO PDF CONTENT FOUND IN DB.")
                else:
                    print(f"✅ Found {len(rows)} distinct PDF titles:")
                    for r in rows:
                        print(f"   - [{r[1]}] {r[0]}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_all_pdfs()
