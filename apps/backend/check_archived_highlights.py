
import sys
import os
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def check_archived_highlights():
    DatabaseManager.init_pool()
    target_book_id = "1763947192884s1obi7m9k"
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Search for notes in archived content
                print(f"Checking for highlights in TOMEHUB_CONTENT_ARCHIVED for {target_book_id}...")
                cursor.execute("""
                    SELECT id, content_type, is_note, DBMS_LOB.SUBSTR(content_chunk, 500, 1) as snippet, created_at
                    FROM TOMEHUB_CONTENT_ARCHIVED 
                    WHERE BOOK_ID = :tid 
                    AND (IS_NOTE = '1' OR CONTENT_TYPE IN ('HIGHLIGHT', 'PERSONAL_NOTE'))
                """, tid=target_book_id)
                
                rows = cursor.fetchall()
                print(f"Found {len(rows)} matching highlights.")
                
                results = []
                for r in rows:
                    results.append({
                        "id": r[0],
                        "content_type": r[1],
                        "is_note": r[2],
                        "snippet": r[3],
                        "created_at": str(r[4])
                    })
                
                with open("archived_highlights_check.json", "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    check_archived_highlights()
