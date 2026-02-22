
from infrastructure.db_manager import DatabaseManager
import os

def find_islam_books():
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        # Search in TOMEHUB_BOOKS
        print("Searching TOMEHUB_BOOKS...")
        cursor.execute("SELECT title, firebase_uid FROM TOMEHUB_BOOKS WHERE LOWER(title) LIKE '%islam felsefesi%'")
        books = cursor.fetchall()
        for b in books:
            print(f"BOOK: {b[0]} | UID: {b[1]}")
            
        # Search in TOMEHUB_CONTENT titles
        print("\nSearching TOMEHUB_CONTENT titles...")
        cursor.execute("SELECT DISTINCT title, firebase_uid FROM TOMEHUB_CONTENT WHERE LOWER(title) LIKE '%islam felsefesi%'")
        contents = cursor.fetchall()
        for c in contents:
            print(f"CONTENT TITLE: {c[0]} | UID: {c[1]}")
            
        # Search in TOMEHUB_CONTENT content
        print("\nSearching TOMEHUB_CONTENT snippets...")
        cursor.execute("SELECT title, firebase_uid, DBMS_LOB.SUBSTR(content_chunk, 100, 1) FROM TOMEHUB_CONTENT WHERE LOWER(content_chunk) LIKE '%islam felsefesi%' AND ROWNUM <= 5")
        snippets = cursor.fetchall()
        for s in snippets:
            print(f"SNIPPET FROM: {s[0]} | UID: {s[1]} | TEXT: {s[2]}...")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_islam_books()
