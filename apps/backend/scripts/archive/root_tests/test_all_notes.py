import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Test query: what happens when resource_type is None?
            sql = """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN title LIKE '% - Self' THEN 1 ELSE 0 END) as personal_notes,
                       SUM(CASE WHEN title NOT LIKE '% - Self' THEN 1 ELSE 0 END) as other_content
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = 'ver63'
            """
            cursor.execute(sql)
            row = cursor.fetchone()
            print(f"Total content: {row[0]}")
            print(f"Personal Notes (title LIKE '% - Self'): {row[1]}")
            print(f"Other content: {row[2]}")
            
            print("\n=== Testing 'All Notes' behavior (should exclude Personal Notes) ===")
            # This is what "All Notes" should do: get everything EXCEPT Personal Notes
            sql2 = """
                SELECT COUNT(*) 
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = 'ver63'
                AND title NOT LIKE '% - Self'
            """
            cursor.execute(sql2)
            count = cursor.fetchone()[0]
            print(f"Content excluding Personal Notes: {count}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
