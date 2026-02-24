import os, json
path = 'services/firestore_sync_service.py'

patch_code = """
def _upsert_library_item_meta(cursor, uid: str, item: StrictFirestoreItem):
    try:
        tags_json = json.dumps(item.tags, ensure_ascii=False) if item.tags else None
        
        category_json = None
        if hasattr(item, 'categories') and item.categories:
            category_json = json.dumps(item.categories, ensure_ascii=False)
            
        sql = '''
        MERGE INTO TOMEHUB_LIBRARY_ITEMS li
        USING (SELECT :p_id AS item_id, :p_uid AS firebase_uid FROM DUAL) src
        ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
        WHEN NOT MATCHED THEN
            INSERT (
                ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, PUBLISHER, 
                TRANSLATOR, PUBLICATION_YEAR, ISBN, SOURCE_URL, PAGE_COUNT, COVER_URL,
                GENERAL_NOTES, SUMMARY_TEXT, TAGS_JSON, CATEGORY_JSON, 
                READING_STATUS, STATUS, IS_FAVORITE, PERSONAL_NOTE_CATEGORY, 
                CONTENT_LANGUAGE_MODE, CONTENT_LANGUAGE_RESOLVED, SOURCE_LANGUAGE_HINT,
                LANGUAGE_DECISION_REASON, LANGUAGE_DECISION_CONFIDENCE,
                PERSONAL_FOLDER_ID, FOLDER_PATH,
                ORIGIN_SYSTEM, CREATED_AT, UPDATED_AT
            ) VALUES (
                :p_id, :p_uid, CAST(:p_type AS VARCHAR2(50)), CAST(:p_title AS VARCHAR2(1000)), 
                CAST(:p_author AS VARCHAR2(1000)), CAST(:p_publisher AS VARCHAR2(255)),
                CAST(:p_translator AS VARCHAR2(255)), CAST(:p_pub_year AS NUMBER), 
                CAST(:p_isbn AS VARCHAR2(255)), CAST(:p_url AS VARCHAR2(2000)),
                CAST(:p_page_count AS NUMBER), CAST(:p_cover_url AS VARCHAR2(2000)),
                CASE WHEN :p_notes IS NOT NULL THEN TO_CLOB(:p_notes) ELSE NULL END,
                CASE WHEN :p_summary IS NOT NULL THEN TO_CLOB(:p_summary) ELSE NULL END,
                CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE NULL END,
                CASE WHEN :p_category_json IS NOT NULL THEN TO_CLOB(:p_category_json) ELSE NULL END,
                CAST(:p_read_status AS VARCHAR2(50)), CAST(:p_phys_status AS VARCHAR2(50)), 
                CAST(:p_fav AS NUMBER), CAST(:p_category AS VARCHAR2(50)),
                CAST(:p_lang_mode AS VARCHAR2(50)), CAST(:p_lang_res AS VARCHAR2(50)), CAST(:p_lang_hint AS VARCHAR2(50)),
                CAST(:p_lang_reason AS VARCHAR2(255)), CAST(:p_lang_conf AS NUMBER),
                CAST(:p_folder_id AS VARCHAR2(255)), CASE WHEN :p_folder_path IS NOT NULL THEN TO_CLOB(:p_folder_path) ELSE NULL END,
                'FIRESTORE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        WHEN MATCHED THEN
            UPDATE SET
                ITEM_TYPE = COALESCE(CAST(:p_type AS VARCHAR2(50)), li.ITEM_TYPE),
                TITLE = COALESCE(CAST(:p_title AS VARCHAR2(1000)), li.TITLE),
                AUTHOR = COALESCE(CAST(:p_author AS VARCHAR2(1000)), li.AUTHOR),
                PUBLISHER = COALESCE(CAST(:p_publisher AS VARCHAR2(255)), li.PUBLISHER),
                TRANSLATOR = COALESCE(CAST(:p_translator AS VARCHAR2(255)), li.TRANSLATOR),
                PUBLICATION_YEAR = COALESCE(CAST(:p_pub_year AS NUMBER), li.PUBLICATION_YEAR),
                ISBN = COALESCE(CAST(:p_isbn AS VARCHAR2(255)), li.ISBN),
                SOURCE_URL = COALESCE(CAST(:p_url AS VARCHAR2(2000)), li.SOURCE_URL),
                PAGE_COUNT = COALESCE(CAST(:p_page_count AS NUMBER), li.PAGE_COUNT),
                COVER_URL = COALESCE(CAST(:p_cover_url AS VARCHAR2(2000)), li.COVER_URL),
                GENERAL_NOTES = CASE WHEN :p_notes IS NOT NULL THEN TO_CLOB(:p_notes) ELSE li.GENERAL_NOTES END,
                SUMMARY_TEXT = CASE WHEN :p_summary IS NOT NULL THEN TO_CLOB(:p_summary) ELSE li.SUMMARY_TEXT END,
                TAGS_JSON = CASE WHEN :p_tags IS NOT NULL THEN TO_CLOB(:p_tags) ELSE li.TAGS_JSON END,
                CATEGORY_JSON = CASE WHEN :p_category_json IS NOT NULL THEN TO_CLOB(:p_category_json) ELSE li.CATEGORY_JSON END,
                READING_STATUS = COALESCE(CAST(:p_read_status AS VARCHAR2(50)), li.READING_STATUS),
                STATUS = COALESCE(CAST(:p_phys_status AS VARCHAR2(50)), li.STATUS),
                IS_FAVORITE = COALESCE(CAST(:p_fav AS NUMBER), li.IS_FAVORITE),
                PERSONAL_NOTE_CATEGORY = COALESCE(CAST(:p_category AS VARCHAR2(50)), li.PERSONAL_NOTE_CATEGORY),
                CONTENT_LANGUAGE_MODE = COALESCE(CAST(:p_lang_mode AS VARCHAR2(50)), li.CONTENT_LANGUAGE_MODE),
                CONTENT_LANGUAGE_RESOLVED = COALESCE(CAST(:p_lang_res AS VARCHAR2(50)), li.CONTENT_LANGUAGE_RESOLVED),
                SOURCE_LANGUAGE_HINT = COALESCE(CAST(:p_lang_hint AS VARCHAR2(50)), li.SOURCE_LANGUAGE_HINT),
                LANGUAGE_DECISION_REASON = COALESCE(CAST(:p_lang_reason AS VARCHAR2(255)), li.LANGUAGE_DECISION_REASON),
                LANGUAGE_DECISION_CONFIDENCE = COALESCE(CAST(:p_lang_conf AS NUMBER), li.LANGUAGE_DECISION_CONFIDENCE),
                PERSONAL_FOLDER_ID = COALESCE(CAST(:p_folder_id AS VARCHAR2(255)), li.PERSONAL_FOLDER_ID),
                FOLDER_PATH = CASE WHEN :p_folder_path IS NOT NULL THEN TO_CLOB(:p_folder_path) ELSE li.FOLDER_PATH END,
                UPDATED_AT = CURRENT_TIMESTAMP
        '''
        
        # safely extract from model
        translator = getattr(item, 'translator', None)
        pub_year = getattr(item, 'publicationYear', None)
        isbn = getattr(item, 'isbn', None)
        url = getattr(item, 'url', None)
        page_count = getattr(item, 'pageCount', None)
        cover_url = getattr(item, 'coverUrl', None)
        summary = getattr(item, 'summary', None)
        reading_status = getattr(item, 'readingStatus', None)
        phys_status = getattr(item, 'status', None)
        is_fav = 1 if getattr(item, 'isFavorite', False) else 0

        lang_mode = getattr(item, 'contentLanguageMode', None)
        lang_res = getattr(item, 'contentLanguageResolved', None)
        lang_hint = getattr(item, 'sourceLanguageHint', None)
        lang_reason = getattr(item, 'languageDecisionReason', None)
        lang_conf = getattr(item, 'languageDecisionConfidence', None)
        folder_id = getattr(item, 'personalFolderId', None)
        folder_path = getattr(item, 'folderPath', None)

        cursor.execute(sql, {
            "p_id": item.book_id,
            "p_uid": uid,
            "p_type": item.type or 'BOOK',
            "p_title": item.title,
            "p_author": item.author,
            "p_publisher": item.publisher,
            "p_translator": translator,
            "p_pub_year": pub_year,
            "p_isbn": isbn,
            "p_url": url,
            "p_page_count": page_count,
            "p_cover_url": cover_url,
            "p_notes": item.generalNotes,
            "p_summary": summary,
            "p_tags": tags_json,
            "p_category_json": category_json,
            "p_read_status": reading_status,
            "p_phys_status": phys_status,
            "p_fav": is_fav,
            "p_category": item.personalNoteCategory,
            "p_lang_mode": lang_mode,
            "p_lang_res": lang_res,
            "p_lang_hint": lang_hint,
            "p_lang_reason": lang_reason,
            "p_lang_conf": lang_conf,
            "p_folder_id": folder_id,
            "p_folder_path": folder_path
        })
    except Exception as e:
        logger.warning(f"Failed to upsert library item metadata for {item.book_id}: {e}")
"""

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

import re
text = re.sub(r'def _upsert_library_item_meta.*?(?=def _write_quarantine)', patch_code + '\n\n', text, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Patched firestore_sync_service.py with parity metadata fields")
