import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Find personal notes by title pattern
            cursor.execute("""
                SELECT title, source_type, content_chunk
                FROM TOMEHUB_CONTENT 
                WHERE LOWER(title) LIKE '%kutlama%' 
                   OR LOWER(title) LIKE '%dogum%'
                   OR LOWER(title) LIKE '%ku8tlam%'
                FETCH FIRST 10 ROWS ONLY
            """)
            
            print("=== Personal Notes Found in Database ===")
            for row in cursor.fetchall():
                title = row[0]
                source_type = row[1]
                content = row[2].read() if hasattr(row[2], 'read') else str(row[2])[:100]
                print(f"\nTitle: {title}")
                print(f"Source Type: {source_type}")
                print(f"Content preview: {content[:100]}...")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
