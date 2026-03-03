
from infrastructure.db_manager import DatabaseManager
import json

def search_highlights():
    book_id = "1763947192884s1obi7m9k"
    results = {}
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Search TOMEHUB_CONTENT_V2
                table = "TOMEHUB_CONTENT_V2"
                print(f"Searching {table} for ITEM_ID={book_id}...")
                results[table] = []
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {table} WHERE ITEM_ID = :bid", {"bid": book_id})
                rows = cursor.fetchall()
                for row in rows:
                    results[table].append(dict(zip(cols, [str(v.read())[:1000] if hasattr(v, 'read') else str(v) for v in row])))

                # 2. Search TOMEHUB_CONTENT_ARCHIVED
                table = "TOMEHUB_CONTENT_ARCHIVED"
                print(f"Searching {table} for BOOK_ID={book_id}...")
                results[table] = []
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {table} WHERE BOOK_ID = :bid", {"bid": book_id})
                rows = cursor.fetchall()
                for row in rows:
                    results[table].append(dict(zip(cols, [str(v.read())[:1000] if hasattr(v, 'read') else str(v) for v in row])))
                
                # 3. Search TOMEHUB_CHANGE_EVENTS
                table = "TOMEHUB_CHANGE_EVENTS"
                print(f"Searching {table} for ITEM_ID={book_id}...")
                results[table] = []
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {table} WHERE ITEM_ID = :bid", {"bid": book_id})
                rows = cursor.fetchall()
                for row in rows:
                    results[table].append(dict(zip(cols, [str(v.read())[:1000] if hasattr(v, 'read') else str(v) for v in row])))

        with open("highlight_search_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print("Done searching.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_highlights()
