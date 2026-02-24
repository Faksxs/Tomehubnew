import os
from infrastructure.db_manager import DatabaseManager

def get_columns():
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        print("--- TOMEHUB_BOOKS ---")
        try:
            cursor.execute("SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH FROM user_tab_columns WHERE table_name = 'TOMEHUB_BOOKS' ORDER BY COLUMN_ID")
            for row in cursor.fetchall():
                print(row)
        except Exception as e: print(e)

        print("\n--- TOMEHUB_LIBRARY_ITEMS ---")
        try:
            cursor.execute("SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH FROM user_tab_columns WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS' ORDER BY COLUMN_ID")
            for row in cursor.fetchall():
                print(row)
        except Exception as e: print(e)

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_columns()
