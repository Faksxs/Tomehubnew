
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def verify_single_book():
    title = "Ahlak Felsefesinin Sorunları"
    print(f"🔍 Verifying upload status for: {title}...\n")
    
    try:
        DatabaseManager.init_pool()
        
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Check PDF content (Should be > 0 now if upload succeeded)
                cursor.execute("""
                    SELECT COUNT(*) FROM TOMEHUB_CONTENT 
                    WHERE LOWER(title) LIKE LOWER(:p_title)
                    AND source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                """, {"p_title": f"%{title}%"})
                
                pdf_count = cursor.fetchone()[0]
                
                print(f"📊 PDF Chunk Count: {pdf_count}")
                
                if pdf_count > 0:
                    print("✅ SUCCESS: usage verified. PDF content exists in database.")
                else:
                    print("⚠️  WARNING: No PDF content found. Upload might have failed or processing is lagging.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    verify_single_book()
