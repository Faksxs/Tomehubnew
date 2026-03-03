
import os
import sys
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def check_status():
    bid = '1771795251587'
    uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    print(f"Checking DB for Book: {bid}, User: {uid}")
    
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            params = {'p_bid': bid, 'p_uid': uid}
            
            # Check Ingestion Status
            try:
                cursor.execute("SELECT STATUS, SOURCE_FILE_NAME, UPDATED_AT, CHUNK_COUNT FROM TOMEHUB_INGESTED_FILES WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid", params)
                row = cursor.fetchone()
                if row:
                    print("--- TOMEHUB_INGESTED_FILES ---")
                    print(f"Status: {row[0]}")
                    print(f"File: {row[1]}")
                    print(f"Updated At: {row[2]}")
                    print(f"Chunk Count (expected): {row[3]}")
                else:
                    print("No record found in TOMEHUB_INGESTED_FILES.")
            except Exception as e:
                print(f"Error checking status: {e}")
            
            # Check Content Chunks
            try:
                cursor.execute("SELECT CONTENT_TYPE, COUNT(*) FROM TOMEHUB_CONTENT_V2 WHERE ITEM_ID = :p_bid AND FIREBASE_UID = :p_uid GROUP BY CONTENT_TYPE", params)
                rows = cursor.fetchall()
                if rows:
                    print("\n--- TOMEHUB_CONTENT_V2 (Current Counts) ---")
                    for r in rows:
                        print(f"{r[0]}: {r[1]} chunks")
                else:
                    print("\nNo content found in TOMEHUB_CONTENT_V2.")
            except Exception as e:
                print(f"Error checking content: {e}")

if __name__ == '__main__':
    check_status()
