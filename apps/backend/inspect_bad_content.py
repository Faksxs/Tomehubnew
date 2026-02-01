
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

def inspect():
    DatabaseManager.init_pool()
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Query the specific page from the screenshot
            cursor.execute("""
                SELECT content_chunk 
                FROM TOMEHUB_CONTENT 
                WHERE title LIKE '%Ahlak Felsefesinin Sorunları%' 
                AND page_number = 203
            """)
            row = cursor.fetchone()
            if row:
                content = row[0].read() if hasattr(row[0], 'read') else str(row[0])
                print(f"--- PAGE 203 CONTENT ---\n{content[:500]}...\n...{content[-300:]}")
            else:
                print("Page 203 not found. Trying another page.")
                cursor.execute("SELECT content_chunk, page_number FROM TOMEHUB_CONTENT WHERE title LIKE '%Ahlak Felsefesinin Sorunları%' FETCH FIRST 3 ROWS ONLY")
                for r in cursor.fetchall():
                    c = r[0].read() if hasattr(r[0], 'read') else str(r[0])
                    print(f"--- PAGE {r[1]} CONTENT ---\n{c[:300]}...\n")

if __name__ == "__main__":
    inspect()
