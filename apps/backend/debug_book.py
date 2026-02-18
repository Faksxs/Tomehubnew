import sqlite3
import os
from services.analytics_service import resolve_multiple_book_ids_from_question

uid = "58Hn5Zxxxx" # Placeholder, I need to know the UID. 
# Wait, I don't have the UID easily. I'll use the one from the logs if I can find it, or just query all books.
# I'll just query the DB directly first.

def check_book():
    from infrastructure.db_manager import DatabaseManager
    with DatabaseManager.get_read_connection() as conn:
        cursor = conn.cursor()
        # Try finding the book in TOMEHUB_BOOKS (assuming column is id)
        try:
            cursor.execute("SELECT id, title, firebase_uid FROM TOMEHUB_BOOKS WHERE title LIKE '%Mahur%'")
            rows = cursor.fetchall()
            print("Books found (TOMEHUB_BOOKS):", rows)
        except Exception as e:
            print("Error querying TOMEHUB_BOOKS:", e)
        
        # Try finding content in TOMEHUB_CONTENT (using book_id)
        try:
            cursor.execute("SELECT book_id, title, firebase_uid, source_type FROM TOMEHUB_CONTENT WHERE title LIKE '%Mahur%' GROUP BY book_id, title, firebase_uid, source_type")
            rows_content = cursor.fetchall()
            print("Books found (TOMEHUB_CONTENT):", rows_content)
        except Exception as e:
            print("Error querying TOMEHUB_CONTENT:", e)

if __name__ == "__main__":
    try:
        check_book()
    except Exception as e:
        print("Error:", e)
