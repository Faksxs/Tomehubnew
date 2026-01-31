import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Query to understand Personal Notes storage
            cursor.execute("""
                SELECT DISTINCT title, source_type, firebase_uid
                FROM TOMEHUB_CONTENT 
                WHERE title LIKE '% - Self'
                FETCH FIRST 20 ROWS ONLY
            """)
            
            print("=== Items with '- Self' suffix (Personal Notes) ===")
            for row in cursor.fetchall():
                print(f"Title: {row[0]}, source_type: {row[1]}")
            
            print("\n=== Checking if there's a separate NOTES table ===")
            try:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_NOTES")
                count = cursor.fetchone()[0]
                print(f"TOMEHUB_NOTES table exists with {count} rows")
                
                cursor.execute("SELECT NOTE_ID, TITLE, firebase_uid FROM TOMEHUB_NOTES FETCH FIRST 10 ROWS ONLY")
                print("\n=== Sample Personal Notes from TOMEHUB_NOTES ===")
                for row in cursor.fetchall():
                    print(f"Note ID: {row[0]}, Title: {row[1]}")
            except Exception as e:
                print(f"TOMEHUB_NOTES table doesn't exist or error: {e}")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
