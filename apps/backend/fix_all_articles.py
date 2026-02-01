
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

def fix_all_articles():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Fix by ID for certainty
            print("\n--- FIXING ARTICLES BY ID/TITLE ---")
            
            # 1. Overcoming AI ethics
            cursor.execute("UPDATE TOMEHUB_CONTENT SET source_type = 'ARTICLE' WHERE id = 2182")
            print(f"Fixed 'Overcoming AI ethics': {cursor.rowcount} row(s)")
            
            # 2. rent a car (use LIKE for variations)
            cursor.execute("UPDATE TOMEHUB_CONTENT SET source_type = 'ARTICLE' WHERE title LIKE '%rent a car%'")
            print(f"Fixed 'rent a car': {cursor.rowcount} row(s)")
            
            conn.commit()
            
            # Verify
            print("\n--- VERIFICATION: REMAINING PDFs ---")
            cursor.execute("SELECT DISTINCT title FROM TOMEHUB_CONTENT WHERE source_type = 'PDF'")
            for row in cursor.fetchall():
                print(f"[PDF] {row[0]}")

if __name__ == "__main__":
    fix_all_articles()
