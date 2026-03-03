
import sys
import os
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
from config import settings

def search_highlights_and_events():
    DatabaseManager.init_pool()
    
    target_book_id = "1763947192884s1obi7m9k"
    results = {
        "highlights_v2": [],
        "highlights_archived": [],
        "change_events": [],
        "library_item": []
    }
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Search Library Items
                print(f"Checking library items for {target_book_id}...")
                cursor.execute("SELECT * FROM TOMEHUB_LIBRARY_ITEMS WHERE ID = :tid", tid=target_book_id)
                cols = [d[0] for d in cursor.description]
                for r in cursor.fetchall():
                    results["library_item"].append(dict(zip(cols, [str(v) for v in r])))

                # 2. Search Content V2
                print(f"Checking TOMEHUB_CONTENT_V2 for {target_book_id}...")
                cursor.execute("SELECT * FROM TOMEHUB_CONTENT_V2 WHERE ITEM_ID = :tid", tid=target_book_id)
                cols = [d[0] for d in cursor.description]
                for r in cursor.fetchall():
                    data = dict(zip(cols, r))
                    # Handle LOBs and large fields
                    summary = {}
                    for k, v in data.items():
                        if k == 'VEC_EMBEDDING': continue
                        if hasattr(v, 'read'):
                            summary[k] = v.read()[:1000]
                        else:
                            summary[k] = str(v)
                    results["highlights_v2"].append(summary)

                # 3. Search Content Archived
                print(f"Checking TOMEHUB_CONTENT_ARCHIVED for {target_book_id}...")
                cursor.execute("SELECT * FROM TOMEHUB_CONTENT_ARCHIVED WHERE BOOK_ID = :tid", tid=target_book_id)
                cols = [d[0] for d in cursor.description]
                for r in cursor.fetchall():
                    data = dict(zip(cols, r))
                    summary = {}
                    for k, v in data.items():
                        if k == 'VEC_EMBEDDING': continue
                        if hasattr(v, 'read'):
                            summary[k] = v.read()[:1000]
                        else:
                            summary[k] = str(v)
                    results["highlights_archived"].append(summary)

                # 4. Search Change Events
                print(f"Checking TOMEHUB_CHANGE_EVENTS for {target_book_id} or related keywords...")
                # Search by item_id or search in the event_data (CLOB)
                cursor.execute("""
                    SELECT * FROM TOMEHUB_CHANGE_EVENTS 
                    WHERE ITEM_ID = :tid 
                    OR DBMS_LOB.INSTR(EVENT_DATA, :tid) > 0
                    OR DBMS_LOB.INSTR(LOWER(EVENT_DATA), 'islam felsefesi') > 0
                """, tid=target_book_id)
                cols = [d[0] for d in cursor.description]
                for r in cursor.fetchall():
                    data = dict(zip(cols, r))
                    summary = {}
                    for k, v in data.items():
                        if hasattr(v, 'read'):
                            summary[k] = v.read()
                        else:
                            summary[k] = str(v)
                    results["change_events"].append(summary)

        with open("highlight_investigation_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print("Investigation complete. Results in highlight_investigation_results.json")

    except Exception as e:
        print(f"Error during investigation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    search_highlights_and_events()
