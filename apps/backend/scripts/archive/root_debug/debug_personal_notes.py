import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Search for the specific titles seen in the user's screenshot
            titles = ["ku8tlam 2", "dogum 2", "Dogum gunu", "ktlma2", "klutlama", "Kutlama"]
            
            print("=== Analyzing Specific Personal Notes ===")
            for t in titles:
                # Try exact match first, then like match
                cursor.execute("""
                    SELECT id, title, source_type, content_chunk 
                    FROM TOMEHUB_CONTENT 
                    WHERE LOWER(title) LIKE :p_pattern
                """, {"p_pattern": f"%{t.lower()}%"})
                
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        print(f"\nSearch Term: '{t}'")
                        print(f"  DB Title: '{row[1]}'")
                        print(f"  DB Source Type: '{row[2]}'")
                        print(f"  DB ID: {row[0]}")
                else:
                    print(f"\nSearch Term: '{t}' - NOT FOUND IN DB")

            print("\n=== Checking for ANY item with source_type='NOTE' or 'NOTES' or 'PERSONAL_NOTE' ===")
            cursor.execute("SELECT count(*), source_type FROM TOMEHUB_CONTENT GROUP BY source_type")
            for row in cursor.fetchall():
                print(f"  Type: {row[1]}, Count: {row[0]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
