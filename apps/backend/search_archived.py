
from infrastructure.db_manager import DatabaseManager
import json

def search_archived():
    results = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                table = "TOMEHUB_BOOKS_ARCHIVED"
                # Get columns
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                
                # Search
                query = f"SELECT * FROM {table} WHERE UPPER(TITLE) LIKE '%AHMET%ARSLAN%' OR UPPER(AUTHOR) LIKE '%AHMET%ARSLAN%' OR UPPER(TITLE) LIKE '%ISLAM%FELSEFESI%'"
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    row_dict = {}
                    for idx, val in enumerate(row):
                        col_name = cols[idx]
                        row_dict[col_name] = str(val)
                    results.append(row_dict)
                    
        with open("archived_search_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"Done. Found {len(results)} matches in archived table.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_archived()
