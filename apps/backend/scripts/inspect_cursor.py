
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def inspect_cursor():
    print("--- Cursor Description for TOMEHUB_FILE_REPORTS ---")
    try:
        with DatabaseManager.get_read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM TOMEHUB_FILE_REPORTS FETCH FIRST 1 ROWS ONLY")
            cols = [d[0] for d in cursor.description]
            print(f"Columns: {cols}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_cursor()
