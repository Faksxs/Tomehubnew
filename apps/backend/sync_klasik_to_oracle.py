import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

CORRECT_UID = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
BOOK_ID = "1771631518661"
TITLE = "Klasik Sosyoloji"
AUTHOR = "Bryan S. Turner"

def sync_book():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Check if already exists
                cursor.execute(
                    "SELECT count(*) FROM TOMEHUB_BOOKS WHERE id = :p_id",
                    {"p_id": BOOK_ID}
                )
                exists = cursor.fetchone()[0] > 0

                if exists:
                    print(f"Book already exists in TOMEHUB_BOOKS: {BOOK_ID}")
                    return

                cursor.execute("""
                    INSERT INTO TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
                    VALUES (:p_id, :p_title, :p_author, :p_uid, CURRENT_TIMESTAMP)
                """, {
                    "p_id": BOOK_ID,
                    "p_title": TITLE,
                    "p_author": AUTHOR,
                    "p_uid": CORRECT_UID
                })
                conn.commit()
                print(f"OK: Inserted '{TITLE}' by {AUTHOR} (ID: {BOOK_ID}) into TOMEHUB_BOOKS.")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    sync_book()
