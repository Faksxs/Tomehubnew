
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def investigate():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Identify Personal Notes (Expected: ~6 items)
            print("\n--- POTENTIAL PERSONAL NOTES (Ending in '- Self') ---")
            cursor.execute("SELECT id, title, source_type FROM TOMEHUB_CONTENT WHERE title LIKE '% - Self' OR title LIKE '%Dogum gunu%'")
            p_notes = cursor.fetchall()
            for row in p_notes:
                print(f"ID: {row[0]}, Title: {row[1]}, Current Type: {row[2]}")
                
            # 2. Identify Potential Articles (Current type PDF/NOTES but not Personal/Book?)
            # Listing all PDF/NOTES to see if we can spot the 9 articles
            print("\n--- ALL CONTENT TITLES (To spot Articles) ---")
            cursor.execute("SELECT title, source_type FROM TOMEHUB_CONTENT ORDER BY source_type, title")
            for row in cursor.fetchall():
                # Filter out obvious books if possible, or just print all to let me analyze output
                print(f"[{row[1]}] {row[0]}")

if __name__ == "__main__":
    investigate()
