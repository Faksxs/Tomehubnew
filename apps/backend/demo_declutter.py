
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager
from services.data_cleaner_service import DataCleanerService

def demo():
    DatabaseManager.init_pool()
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Get a cluttered chunk
            cursor.execute("""
                SELECT id, content_chunk, title 
                FROM TOMEHUB_CONTENT 
                WHERE title LIKE '%Ahlak Felsefesinin Sorunları%' 
                AND page_number = 203
            """)
            row = cursor.fetchone()
            if not row:
                print("No cluttered chunk found for demo.")
                return
                
            chunk_id, lob, title = row
            text = lob.read() if hasattr(lob, 'read') else str(lob)
            
            print("\n" + "="*50)
            print("BEFORE CLEANING (Original):")
            print("="*50)
            print(text[:400] + "...")
            
            print("\n" + "="*50)
            print("AFTER CLEANING (AI):")
            print("="*50)
            cleaned = DataCleanerService.clean_with_ai(text, title=title)
            print(cleaned[:400] + "...")

if __name__ == "__main__":
    demo()
