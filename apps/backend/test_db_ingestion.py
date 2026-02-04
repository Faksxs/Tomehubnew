
import os
import sys

# Current dir is apps/backend
sys.path.append(os.getcwd())

try:
    from infrastructure.db_manager import DatabaseManager
    from config import settings
except ImportError:
    # try one level up
    sys.path.append(os.path.dirname(os.getcwd()))
    from infrastructure.db_manager import DatabaseManager
    from config import settings

def test_db():
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Get a sample UID first to be sure
                cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT WHERE ROWNUM <= 5")
                sample_uids = [row[0] for row in cursor.fetchall()]
                print(f"Sample UIDs in DB: {sample_uids}")
                
                # Use the suspected one or first one
                target_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
                if target_uid not in sample_uids and sample_uids:
                    target_uid = sample_uids[0]

                print(f"\nChecking for UID: {target_uid}")
                
                # Check table existence first
                print("\n--- TABLE STATUS ---")
                tables = ['TOMEHUB_INGESTED_FILES', 'TOMEHUB_CONTENT', 'TOMEHUB_BOOKS']
                for table in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        count = cursor.fetchone()[0]
                        print(f"Table {table}: {count} records total")
                    except Exception as e:
                        print(f"Table {table} check failed: {e}")

                # 1. Check TOMEHUB_INGESTED_FILES for target_uid
                print("\n--- TOMEHUB_INGESTED_FILES for target_uid ---")
                try:
                    cursor.execute("""
                        SELECT book_id, source_file_name, status 
                        FROM TOMEHUB_INGESTED_FILES 
                        WHERE firebase_uid = :p_fuid
                    """, {"p_fuid": target_uid})
                    rows = cursor.fetchall()
                    if not rows:
                        print("No records found in TOMEHUB_INGESTED_FILES for this UID")
                    for row in rows:
                        print(f"BookID: {row[0]}, File: {row[1]}, Status: {row[2]}")
                except Exception as e:
                    print(f"Error querying TOMEHUB_INGESTED_FILES: {e}")

                # 2. Check TOMEHUB_CONTENT for PDF for target_uid
                print("\n--- TOMEHUB_CONTENT (PDF counts) for target_uid ---")
                try:
                    cursor.execute("""
                        SELECT book_id, source_type, COUNT(*) 
                        FROM TOMEHUB_CONTENT 
                        WHERE firebase_uid = :p_fuid 
                          AND (source_type = 'PDF' OR source_type = 'PDF_CHUNK')
                        GROUP BY book_id, source_type
                    """, {"p_fuid": target_uid})
                    rows = cursor.fetchall()
                    if not rows:
                        print("No records found in TOMEHUB_CONTENT for PDF for this UID")
                    for row in rows:
                        print(f"BookID: {row[0]}, Type: {row[1]}, Count: {row[2]}")
                except Exception as e:
                    print(f"Error querying TOMEHUB_CONTENT: {e}")

    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    test_db()
