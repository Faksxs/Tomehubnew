
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager
from services.data_cleaner_service import DataCleanerService

def demo():
    DatabaseManager.init_pool()
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, content_chunk, title FROM TOMEHUB_CONTENT WHERE title LIKE '%Ahlak Felsefesinin Sorunları%' AND page_number = 203")
            row = cursor.fetchone()
            if not row: return
            
            chunk_id, lob, title = row
            text = lob.read() if hasattr(lob, 'read') else str(lob)
            cleaned = DataCleanerService.clean_with_ai(text, title=title)
            
            with open("demo_result.txt", "w", encoding="utf-8") as f:
                f.write("BEFORE:\n" + text[:500] + "\n\nAFTER:\n" + cleaned[:500])

if __name__ == "__main__":
    demo()
