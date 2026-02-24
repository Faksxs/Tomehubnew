import os
import sys
import json
import firebase_admin
from firebase_admin import credentials, firestore

CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)

from infrastructure.db_manager import DatabaseManager

def _as_num(val):
    if not val: return None
    try: return int(val)
    except: return None

def sync_all():
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
                    print(f"Syncing user {uid} from Firestore...")
                    docs = db.collection("users").document(uid).collection("items").stream()
                    for doc in docs:
                        item_id = doc.id
                        raw = doc.to_dict() or {}
                        
                        title = str(raw.get("title", "")).strip() or "Untitled"
                        author = raw.get("author")
                        if isinstance(author, list):
                            author = ", ".join([str(a) for a in author])
                        else:
                            author = str(author or "").strip()
                            
                        item_type = str(raw.get("type", "BOOK")).upper()
                        if item_type in {"NOTE", "PERSONAL"}: item_type = "PERSONAL_NOTE"
                        elif item_type in {"NOTES", "HIGHLIGHTS"}: item_type = "HIGHLIGHT"
                        elif item_type == "INSIGHTS": item_type = "INSIGHT"
                        
                        publisher = raw.get("publisher")
                        translator = raw.get("translator")
                        publication_year = _as_num(raw.get("publicationYear"))
                        isbn = raw.get("isbn")
                        url = raw.get("url")
                        page_count = _as_num(raw.get("pageCount"))
                        cover_url = raw.get("coverUrl")
                        
                        summary_text = raw.get("summary") # might be summary or generalNotes
                        general_notes = raw.get("generalNotes")
                        
                        tags = raw.get("tags", [])
                        if not isinstance(tags, list): tags = []
                        tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                        
                        category_json = raw.get("categories")
                        if isinstance(category_json, list):
                            category_json = json.dumps(category_json, ensure_ascii=False)
                        else:
                            category_json = None
                            
                        # Mappings
                        reading_status = raw.get("readingStatus")
                        physical_status = raw.get("status")
                        is_favorite = 1 if raw.get("isFavorite") else 0
                        
                        personal_note_cat = raw.get("personalNoteCategory", "PRIVATE")
                        
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
                                TRANSLATOR = COALESCE(:p_translator, li.TRANSLATOR),
                                PUBLICATION_YEAR = COALESCE(:p_pub_year, li.PUBLICATION_YEAR),
                                ISBN = COALESCE(:p_isbn, li.ISBN),
                                SOURCE_URL = COALESCE(:p_url, li.SOURCE_URL),
                                PAGE_COUNT = COALESCE(:p_page_count, li.PAGE_COUNT),
                                COVER_URL = COALESCE(:p_cover_url, li.COVER_URL),
                                SUMMARY_TEXT = CASE WHEN :p_summary IS NOT NULL THEN TO_CLOB(:p_summary) ELSE li.SUMMARY_TEXT END,
                                GENERAL_NOTES = CASE WHEN :p_notes IS NOT NULL THEN TO_CLOB(:p_notes) ELSE li.GENERAL_NOTES END,
                                TAGS_JSON = CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE li.TAGS_JSON END,
                                CATEGORY_JSON = CASE WHEN :p_category_json IS NOT NULL THEN TO_CLOB(:p_category_json) ELSE li.CATEGORY_JSON END,
                                READING_STATUS = COALESCE(:p_read_status, li.READING_STATUS),
                                STATUS = COALESCE(:p_phys_status, li.STATUS),
                                IS_FAVORITE = COALESCE(:p_fav, li.IS_FAVORITE),
                                PERSONAL_NOTE_CATEGORY = COALESCE(:p_note_cat, li.PERSONAL_NOTE_CATEGORY),
                                UPDATED_AT = CURRENT_TIMESTAMP
                        '''
                        try:
                            # Truncate string bounds for VARCHAR2(2000) or similar limits
                            cur.execute(sql, {
                                "p_id": item_id,
                                "p_uid": uid,
                                "p_type": item_type[:50],
                                "p_title": title[:1000],
                                "p_author": author[:1000] if author else None,
                                "p_publisher": str(publisher)[:255] if publisher else None,
                                "p_translator": str(translator)[:255] if translator else None,
                                "p_pub_year": publication_year,
                                "p_isbn": str(isbn)[:255] if isbn else None,
                                "p_url": str(url)[:2000] if url else None,
                                "p_page_count": page_count,
                                "p_cover_url": str(cover_url)[:2000] if cover_url else None,
                                "p_summary": str(summary_text) if summary_text else None,
                                "p_notes": str(general_notes) if general_notes else None,
                                "p_tags": tags_json,
                                "p_category_json": category_json,
                                "p_read_status": str(reading_status)[:50] if reading_status else None,
                                "p_phys_status": str(physical_status)[:50] if physical_status else None,
                                "p_fav": is_favorite,
                                "p_note_cat": str(personal_note_cat)[:50] if personal_note_cat else None,
                            })
                        except Exception as e:
                            print(f"Update failed for {title}: {e}")
                
                w_conn.commit()
        print("Extended metadata backfill completed successfully!")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    from config import settings
    sync_all()
