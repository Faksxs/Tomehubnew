
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def diagnostic():
    print("--- Detailed MERGE Diagnostic ---")
    with DatabaseManager.get_write_connection() as conn:
        cursor = conn.cursor()
        
        # Test 1: Minimal MERGE
        print("Test 1: Minimal MERGE (ONLY ON clause)...")
        try:
            sql = """
                MERGE INTO TOMEHUB_FILE_REPORTS t
                USING (SELECT 'TEST' as BID, 'TEST' as UVAL FROM DUAL) s
                ON (t.BOOK_ID = s.BID AND t.FIREBASE_UID = s.UVAL)
                WHEN MATCHED THEN UPDATE SET SUMMARY_TEXT = 'TEST'
            """
            cursor.execute(sql)
            print("✓ Test 1 OK")
        except Exception as e:
            print(f"✗ Test 1 FAILED: {e}")

        # Test 2: Add KEY_TOPICS
        print("Test 2: Add KEY_TOPICS...")
        try:
            sql = """
                MERGE INTO TOMEHUB_FILE_REPORTS t
                USING (SELECT 'TEST' as BID, 'TEST' as UVAL FROM DUAL) s
                ON (t.BOOK_ID = s.BID AND t.FIREBASE_UID = s.UVAL)
                WHEN MATCHED THEN UPDATE SET KEY_TOPICS = '[]'
            """
            cursor.execute(sql)
            print("✓ Test 2 OK")
        except Exception as e:
            print(f"✗ Test 2 FAILED: {e}")

        # Test 3: Add ENTITIES
        print("Test 3: Add ENTITIES...")
        try:
            sql = """
                MERGE INTO TOMEHUB_FILE_REPORTS t
                USING (SELECT 'TEST' as BID, 'TEST' as UVAL FROM DUAL) s
                ON (t.BOOK_ID = s.BID AND t.FIREBASE_UID = s.UVAL)
                WHEN MATCHED THEN UPDATE SET ENTITIES = '[]'
            """
            cursor.execute(sql)
            print("✓ Test 3 OK")
        except Exception as e:
            print(f"✗ Test 3 FAILED: {e}")

        # Test 4: Add UPDATED_AT
        print("Test 4: Add UPDATED_AT...")
        try:
            sql = """
                MERGE INTO TOMEHUB_FILE_REPORTS t
                USING (SELECT 'TEST' as BID, 'TEST' as UVAL FROM DUAL) s
                ON (t.BOOK_ID = s.BID AND t.FIREBASE_UID = s.UVAL)
                WHEN MATCHED THEN UPDATE SET UPDATED_AT = CURRENT_TIMESTAMP
            """
            cursor.execute(sql)
            print("✓ Test 4 OK")
        except Exception as e:
            print(f"✗ Test 4 FAILED: {e}")

        conn.rollback()

if __name__ == "__main__":
    diagnostic()
