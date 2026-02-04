
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
                cur.execute("SELECT DISTINCT title, book_id FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid AND title LIKE '%Mahur Beste%'", {"p_uid": uid})
                rows = cur.fetchall()
                print(f"--- Mahur Beste Search Results ---")
                for title, bid in rows:
                    print(f"Found: {title} | ID: {bid}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_books()
