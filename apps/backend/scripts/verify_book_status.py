
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def  verify_books():
    target_books = [
        "Mahur Beste",
        "Akıl Çağı",
        "1984",
        "Ahlak Felsefesinin Sorunları",
        "Hayatın Anlamı"
    ]
    
    print("🔍 Verifying status for requested books...\n")
    
    try:
        DatabaseManager.init_pool()
        
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                print(f"{'BOOK TITLE':<35} | {'PDF CHUNKS':<12} | {'OTHER (Notes/Meta)':<15}")
                print("-" * 70)
                
                for title in target_books:
                    # Check PDF content (should be 0)
                    cursor.execute("""
                        SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                        WHERE LOWER(title) LIKE LOWER(:p_title)
                        AND source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    """, {"p_title": f"%{title}%"})
                    pdf_count = cursor.fetchone()[0]
                    
                    # Check other content (should remain if exists)
                    cursor.execute("""
                        SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                        WHERE LOWER(title) LIKE LOWER(:p_title)
                        AND source_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    """, {"p_title": f"%{title}%"})
                    other_count = cursor.fetchone()[0]
                    
                    status = "✅ CLEAN" if pdf_count == 0 else "❌ HAS DATA"
                    print(f"{title:<35} | {pdf_count:<12} | {other_count:<15} -> {status}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_books()
