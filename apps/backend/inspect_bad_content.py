
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def inspect_content():
    print("Initializing DB Pool...")
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                print("Fetching content samples...")
                cursor.execute("""
                    SELECT content_chunk 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE 'Hayatin Anlami - Terry Eagleton%' 
                    FETCH FIRST 5 ROWS ONLY
                """)
                
                rows = cursor.fetchall()
                print(f"Found {len(rows)} rows.")
                for i, row in enumerate(rows):
                    print(f"\n--- Chunk {i+1} ---")
                    print(row[0])
                    
    except Exception as e:
        print(f"Query failed: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    inspect_content()
