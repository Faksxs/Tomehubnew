import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings

def find_ghost_in_firestore(uid):
    if not settings.FIREBASE_READY:
        print("Firebase Admin SDK is not ready.")
        return

    from firebase_admin import firestore
    db = firestore.client()
    
    docs = db.collection("users").document(uid).collection("items").stream()
    
    found = False
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title", "").lower()
        author = data.get("author", "").lower()
        
        # Broad search
        if "klasik" in title or "sosyoloji" in title or "klasik" in author or "sosyoloji" in author:
            print(f"!!! FOUND GHOST IN FIRESTORE !!!")
            print(f"ID: {doc.id}")
            print(f"Title: {data.get('title')}")
            print(f"Author: {data.get('author')}")
            found = True
            
            # Now check Oracle for this specific ID
            from infrastructure.db_manager import DatabaseManager
            DatabaseManager.init_pool()
            try:
                with DatabaseManager.get_read_connection() as conn:
                    with conn.cursor() as cursor:
                        # Check TOMEHUB_BOOKS
                        cursor.execute("SELECT count(*) FROM TOMEHUB_BOOKS WHERE id = :p_id", {"p_id": doc.id})
                        if cursor.fetchone()[0] == 0:
                            print(f"-> This book ({doc.id}) is MISSING from Oracle TOMEHUB_BOOKS.")
                            print(f"-> Fixing: Inserting into TOMEHUB_BOOKS to restore sync...")
                            cursor.execute("""
                                INSERT INTO TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
                                VALUES (:p_id, :p_title, :p_author, :p_uid, CURRENT_TIMESTAMP)
                            """, {
                                "p_id": doc.id,
                                "p_title": data.get('title', 'Unknown Title'),
                                "p_author": data.get('author', 'Unknown Author'),
                                "p_uid": uid
                            })
                            
                        # Check TOMEHUB_CONTENT for chunks linked to this ID
                        cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT WHERE book_id = :p_id", {"p_id": doc.id})
                        print(f"-> Oracle TOMEHUB_CONTENT contains {cursor.fetchone()[0]} chunks for this ID.")
            finally:
                DatabaseManager.close_pool()
            
    if not found:
        print("No matching books found in Firestore under any ID.")

if __name__ == "__main__":
    find_ghost_in_firestore("vpq1p0UzcCSLAh1d18WgZZeTebh1")
