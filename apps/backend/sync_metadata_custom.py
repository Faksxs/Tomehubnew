import os
import sys
import json
import firebase_admin
from firebase_admin import credentials, firestore

CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)

from infrastructure.db_manager import DatabaseManager
from models.firestore_sync_models import normalize_and_validate_item

def sync_all():
    # Initialize Firebase if not already
    try:
        if not firebase_admin._apps:
            cred_path = os.getenv('FIREBASE_CREDENTIALS') 
            if cred_path:
                 cred = credentials.Certificate(cred_path)
                 firebase_admin.initialize_app(cred)
            else:
                 # Default ADC
                 firebase_admin.initialize_app()
    except Exception as e:
        print(f"Failed to initialize Firebase: {e}")
        return

    db = firestore.client()
    
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT FIREBASE_UID FROM TOMEHUB_LIBRARY_ITEMS")
                uids = [row[0] for row in cur.fetchall()]
        
        print(f"Found {len(uids)} users in TOMEHUB_LIBRARY_ITEMS.")
        
        with DatabaseManager.get_write_connection() as w_conn:
            with w_conn.cursor() as cur:
                for uid in uids:
                    print(f"Syncing user {uid} from Firestore...")
                    docs = db.collection("users").document(uid).collection("items").stream()
                    for doc in docs:
                        item_id = doc.id
                        raw = doc.to_dict() or {}
                        try:
                            item = normalize_and_validate_item(item_id, raw)
                        except Exception as e:
                            print(f"Validation failed for {item_id}: {e}")
                            continue
                        
                        tags_json = json.dumps(item.tags, ensure_ascii=False) if item.tags else None
                        
                        sql = '''
                        MERGE INTO TOMEHUB_LIBRARY_ITEMS li
                        USING (SELECT :p_id AS item_id, :p_uid AS firebase_uid FROM DUAL) src
                        ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
                        WHEN MATCHED THEN
                            UPDATE SET
                                ITEM_TYPE = COALESCE(:p_type, li.ITEM_TYPE),
                                TITLE = COALESCE(:p_title, li.TITLE),
                                AUTHOR = COALESCE(:p_author, li.AUTHOR),
                                PUBLISHER = COALESCE(:p_publisher, li.PUBLISHER),
                                GENERAL_NOTES = CASE WHEN :p_notes IS NOT NULL THEN TO_CLOB(:p_notes) ELSE li.GENERAL_NOTES END,
                                TAGS_JSON = CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE li.TAGS_JSON END,
                                PERSONAL_NOTE_CATEGORY = COALESCE(:p_category, li.PERSONAL_NOTE_CATEGORY),
                                UPDATED_AT = CURRENT_TIMESTAMP
                        '''
                        try:
                            # Truncate strings if extremely long but Firebase model should handle it
                            cur.execute(sql, {
                                "p_id": item.book_id,
                                "p_uid": uid,
                                "p_type": item.type or 'BOOK',
                                "p_title": item.title,
                                "p_author": item.author,
                                "p_publisher": item.publisher,
                                "p_notes": item.generalNotes,
                                "p_tags": tags_json,
                                "p_category": item.personalNoteCategory,
                            })
                        except Exception as e:
                            print(f"Update failed for {item.book_id}: {e}")
                w_conn.commit()
        print("Metadata backfill completed successfully!")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    from config import settings
    # Ensure environment is ready
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        print("FIREBASE_READY is not set! Attempting anyway...")
    sync_all()
