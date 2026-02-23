
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def test_columns(table_name, columns):
    print(f"--- Column Test for {table_name} ---")
    with DatabaseManager.get_read_connection() as conn:
        cursor = conn.cursor()
        for col in columns:
            try:
                cursor.execute(f"SELECT {col} FROM {table_name} FETCH FIRST 1 ROWS ONLY")
                print(f"✓ Column {col}: OK")
            except Exception as e:
                print(f"✗ Column {col}: FAILED ({e})")

if __name__ == "__main__":
    cols = ["BOOK_ID", "FIREBASE_UID", "SUMMARY_TEXT", "KEY_TOPICS", "ENTITIES", "CREATED_AT", "UPDATED_AT", "LAST_UPDATED"]
    test_columns("TOMEHUB_FILE_REPORTS", cols)
