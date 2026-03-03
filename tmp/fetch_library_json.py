import os
import json
import sys
from dotenv import load_dotenv

# Add backend dir to path for imports
backend_dir = r"c:\Users\aksoy\Desktop\yeni tomehub\apps\backend"
sys.path.append(backend_dir)
from infrastructure.db_manager import DatabaseManager

# Load env from backend dir
load_dotenv(os.path.join(backend_dir, '.env'))

def get_titles():
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Find the correct library table
                cursor.execute("SELECT table_name FROM user_tables WHERE table_name IN ('TOMEHUB_LIBRARY_ITEMS', 'TOME_LIBRARY_ITEMS')")
                row = cursor.fetchone()
                if not row:
                    # Fallback to TOMEHUB_BOOKS if primary library table is missing
                    cursor.execute("SELECT table_name FROM user_tables WHERE table_name = 'TOMEHUB_BOOKS'")
                    row = cursor.fetchone()
                    if not row:
                        print(json.dumps({"error": "No book/library tables found"}))
                        return
                
                table_name = row[0]
                
                # Check columns to build query
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table_name}'")
                cols = [c[0] for c in cursor.fetchall()]
                
                select_cols = []
                if "TITLE" in cols: select_cols.append("TITLE")
                if "AUTHOR" in cols: select_cols.append("AUTHOR")
                if "TYPE" in cols: select_cols.append("TYPE")
                if "ADDED_AT" in cols: select_cols.append("ADDED_AT")
                if "ID" in cols: select_cols.append("ID")
                
                query = f"SELECT {', '.join(select_cols)} FROM {table_name}"
                if "IS_DELETED" in cols:
                    query += " WHERE IS_DELETED = 0"
                query += " ORDER BY TITLE"
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                book_list = []
                for r in rows:
                    item = {}
                    for i, col_name in enumerate(select_cols):
                        val = r[i]
                        if hasattr(val, 'isoformat'):
                            val = val.isoformat()
                        item[col_name.lower()] = val
                    book_list.append(item)
                
                output_path = r"c:\Users\aksoy\Desktop\yeni tomehub\tmp\library_list.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(book_list, f, indent=2, ensure_ascii=False)
                print(f"Success: Written to {output_path}")
                
    except Exception as e:
        import traceback
        print(json.dumps({"error": str(e), "trace": traceback.format_exc()}))
    finally:
        try:
            DatabaseManager.close_pool()
        except:
            pass

if __name__ == "__main__":
    get_titles()
