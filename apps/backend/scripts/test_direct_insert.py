
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def test_direct_insert():
    print("--- Direct INSERT Test ---")
    try:
        with DatabaseManager.get_write_connection() as conn:
            cursor = conn.cursor()
            # Try to insert a row with minimal columns
            # Assuming ID is auto-generated or some sequence exists
            # If not, it will fail, but we want to see the error
            sql = """
                INSERT INTO TOMEHUB_FILE_REPORTS (BOOK_ID, FIREBASE_UID, SUMMARY_TEXT)
                VALUES ('TEST_BID', 'TEST_UID', 'TEST_SUMMARY')
            """
            cursor.execute(sql)
            print("✓ INSERT successful (transaction not committed yet)")
            conn.rollback() # Don't actually save test data
    except Exception as e:
        print(f"✗ INSERT failed: {e}")

if __name__ == "__main__":
    test_direct_insert()
