
import os
import sys
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def get_title():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, firebase_uid, COUNT(*) FROM TOMEHUB_CONTENT WHERE book_id = '1764982122036' GROUP BY title, firebase_uid")
                rows = cur.fetchall()
                print(f"--- Data for 1764982122036 ---")
                for title, uid, count in rows:
                    print(f"Title: {repr(title)} | UID: {uid} | Chunks: {count}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_title()
