
import sys
import os
import json

# Add current directory and apps/backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def verify_restoration():
    DatabaseManager.init_pool()
    target_id = "1763947192884s1obi7m9k"
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                print("--- Verification Report ---")
                
                # Check Library
                cursor.execute("SELECT TITLE, AUTHOR FROM TOMEHUB_LIBRARY_ITEMS WHERE ITEM_ID = :tid", tid=target_id)
                lib = cursor.fetchone()
                if lib:
                    print(f"Library Item Found: {lib[0]} by {lib[1]}")
                else:
                    print("Error: Library Item NOT found in active table!")

                # Check Content Count
                cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT_V2 WHERE ITEM_ID = :tid", tid=target_id)
                count = cursor.fetchone()[0]
                print(f"Total Content Records in V2: {count}")

                # Check Highlights Specifically
                cursor.execute("""
                    SELECT count(*) FROM TOMEHUB_CONTENT_V2 
                    WHERE ITEM_ID = :tid 
                    AND (CONTENT_TYPE IN ('HIGHLIGHT', 'PERSONAL_NOTE'))
                """, tid=target_id)
                highlight_count = cursor.fetchone()[0]
                print(f"Total Highlights in V2: {highlight_count}")

                # Sample Snippet
                cursor.execute("""
                    SELECT CONTENT_CHUNK FROM TOMEHUB_CONTENT_V2 
                    WHERE ITEM_ID = :tid AND CONTENT_TYPE = 'HIGHLIGHT'
                    FETCH FIRST 1 ROWS ONLY
                """)
                snippet = cursor.fetchone()
                if snippet:
                    print(f"Sample Highlight: {str(snippet[0])[:150]}...")

    except Exception as e:
        print(f"Verification Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    verify_restoration()
