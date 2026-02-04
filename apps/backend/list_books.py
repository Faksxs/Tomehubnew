
import os
import sys
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def list_books():
    DatabaseManager.init_pool()
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT title, book_id FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": uid})
                rows = cur.fetchall()
                print(f"--- Books for {uid} ---")
                for title, bid in rows:
                    print(f"Title: {title} | ID: {bid}")
                
                cur.execute("SELECT DISTINCT book_id, status FROM TOMEHUB_INGESTED_FILES WHERE firebase_uid = :p_uid", {"p_uid": uid})
                rows = cur.fetchall()
                print(f"\n--- Ingested Files Status ---")
                for bid, status in rows:
                    print(f"ID: {bid} | Status: {status}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_books()
