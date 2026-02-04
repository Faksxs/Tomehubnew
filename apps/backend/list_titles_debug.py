
import os
import sys
import io

# Handle Turkish encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def list_titles():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Search for multiple variations
                cursor.execute("""
                    SELECT DISTINCT title, firebase_uid, source_type 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE '%Hayat%' 
                       OR title LIKE '%Anlam%' 
                       OR title LIKE '%Terry%' 
                       OR title LIKE '%Eagleton%'
                """)
                rows = cursor.fetchall()
                print(f"--- Found {len(rows)} matching titles ---")
                for row in rows:
                    print(f"Title: {row[0]} | UID: {row[1]} | Type: {row[2]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    list_titles()
