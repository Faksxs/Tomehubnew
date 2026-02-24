import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore

CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)

from infrastructure.db_manager import DatabaseManager
from models.firestore_sync_models import normalize_and_validate_item
from services.firestore_sync_service import _upsert_library_item_meta

def sync_all_parity():
    try:
        if not firebase_admin._apps:
            cred_path = os.getenv('FIREBASE_CREDENTIALS') 
            if cred_path:
                 cred = credentials.Certificate(cred_path)
                 firebase_admin.initialize_app(cred)
            else:
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
                    print(f"Syncing user {uid} from Firestore parity...")
                    docs = db.collection("users").document(uid).collection("items").stream()
                    for doc in docs:
                        item_id = doc.id
                        raw = doc.to_dict() or {}
                        
                        try:
                            # Parse into model (now includes all missing fields)
                            item = normalize_and_validate_item(item_id, raw)
                            # Upsert via original patched backend logic!
                            _upsert_library_item_meta(cur, uid, item)
                        except Exception as e:
                            print(f'Sync error on {item_id}: {e}')
                
                w_conn.commit()
        print("Parity backfill completed successfully!")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    from config import settings
    sync_all_parity()
