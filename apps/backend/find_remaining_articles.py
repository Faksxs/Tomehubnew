
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

def fix_remaining():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Check Michele Murgia article
            print("\n--- CHECKING 'Michele Murgia' ---")
            cursor.execute("SELECT id, title, source_type FROM TOMEHUB_CONTENT WHERE title LIKE '%Michele Murgia%' OR title LIKE '%Overcoming AI%'")
            for row in cursor.fetchall():
                print(f"ID: {row[0]}, Title: {row[1]}, Type: {row[2]}")
            
            # List ALL unique titles with their source_type
            print("\n--- ALL UNIQUE TITLES BY TYPE ---")
            cursor.execute("SELECT DISTINCT title, source_type FROM TOMEHUB_CONTENT ORDER BY source_type, title")
            for row in cursor.fetchall():
                print(f"[{row[1]}] {row[0]}")

if __name__ == "__main__":
    fix_remaining()
