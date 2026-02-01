
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager
from services.data_cleaner_service import DataCleanerService
from services.embedding_service import get_embedding
import concurrent.futures

def scrub_book(target_title):
    print(f"\n🚀 Scrubbing book: {target_title}")
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Fetch chunks that need scrubbing (limiting for safety, can be expanded)
            cursor.execute("""
                SELECT id, content_chunk, title 
                FROM TOMEHUB_CONTENT 
                WHERE title LIKE :p_title 
                AND source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
            """, {"p_title": f"%{target_title}%"})
            
            rows = cursor.fetchall()
            print(f"📄 Found {len(rows)} chunks to process.")
            
            def process_chunk(row):
                cid, lob, title = row
                original_text = lob.read() if hasattr(lob, 'read') else str(lob)
                
                # Perform AI Clean
                cleaned_text = DataCleanerService.clean_with_ai(original_text, title=title)
                
                if cleaned_text and cleaned_text != original_text:
                    # Update DB (and also update embedding since text changed)
                    new_vec = get_embedding(cleaned_text)
                    return (cid, cleaned_text, new_vec)
                return None

            updates = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(process_chunk, rows))
                updates = [r for r in results if r]

            print(f"✨ Cleaned {len(updates)} chunks. Committing...")
            
            for cid, text, vec in updates:
                cursor.execute("""
                    UPDATE TOMEHUB_CONTENT 
                    SET content_chunk = :p_content, 
                        vec_embedding = :p_vec
                    WHERE id = :p_id
                """, {"p_content": text, "p_vec": vec, "p_id": cid})
            
            conn.commit()
            print("✅ Done!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        scrub_book(sys.argv[1])
    else:
        print("Usage: python scrub_existing_books.py <book_title_keyword>")
