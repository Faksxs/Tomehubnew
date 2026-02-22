import os
import sys
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings

async def force_sync_or_clean(uid, book_id):
    if not settings.FIREBASE_READY:
        print("Firebase Admin SDK is not ready.")
        return

    from firebase_admin import firestore
    from infrastructure.db_manager import DatabaseManager
    
    db = firestore.client()
    doc_ref = db.collection("users").document(uid).collection("items").document(book_id)
    
    doc = doc_ref.get()
    if doc.exists:
        print(f"Book exists in Firestore: {doc.to_dict().get('title')}")
        
        # Check if it exists in Oracle TOMEHUB_BOOKS
        DatabaseManager.init_pool()
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id FROM TOMEHUB_BOOKS WHERE id = :p_id", {"p_id": book_id})
                    if not cursor.fetchone():
                        print(f"WARNING: Book {book_id} is in Firestore but MISSING from Oracle TOMEHUB_BOOKS!")
                        print("This is a GHOST record. Since user requested NO DELETION, we will just copy it back to Oracle to fix the desync.")
                        
                        # Fix the desync by re-inserting into Oracle from Firestore data
                        cursor.execute("""
                            INSERT INTO TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
                            VALUES (:p_id, :p_title, :p_author, :p_uid, CURRENT_TIMESTAMP)
                        """, {
                            "p_id": book_id,
                            "p_title": doc.to_dict().get('title', 'Klasik Sosyoloji'),
                            "p_author": doc.to_dict().get('author', 'Unknown'),
                            "p_uid": uid
                        })
                        conn.commit()
                        print("Restored ghost book from Firestore back to Oracle TOMEHUB_BOOKS.")
                    else:
                        print("Book also exists in Oracle. Sync is fine.")
        finally:
            DatabaseManager.close_pool()
    else:
        print("Book does not exist in Firestore. No front-end ghost data found for this specific ID.")

if __name__ == "__main__":
    asyncio.run(force_sync_or_clean("vpq1p0UzcCSLAh1d18WgZZeTebh1", "1771631518661"))
