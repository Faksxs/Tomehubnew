import os, json
path = 'services/firestore_sync_service.py'

patch_code = """
def _upsert_library_item_meta(cursor, uid: str, item: StrictFirestoreItem):
    try:
        tags_json = json.dumps(item.tags, ensure_ascii=False) if item.tags else None
        
        # Convert ms timestamp to Oracle TIMESTAMP if present
        updated_at_clause = "CURRENT_TIMESTAMP"
        # We just use CURRENT_TIMESTAMP for simplicity, or we could parse item.updatedAt
        
        sql = '''
        MERGE INTO TOMEHUB_LIBRARY_ITEMS li
        USING (SELECT :p_id AS item_id, :p_uid AS firebase_uid FROM DUAL) src
        ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
        WHEN NOT MATCHED THEN
            INSERT (
                ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, PUBLISHER, 
                GENERAL_NOTES, TAGS_JSON, PERSONAL_NOTE_CATEGORY, 
                ORIGIN_SYSTEM, CREATED_AT, UPDATED_AT
            ) VALUES (
                :p_id, :p_uid, :p_type, :p_title, :p_author, :p_publisher,
                :p_notes, :p_tags, :p_category,
                'FIRESTORE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        WHEN MATCHED THEN
            UPDATE SET
                ITEM_TYPE = COALESCE(:p_type, li.ITEM_TYPE),
                TITLE = COALESCE(:p_title, li.TITLE),
                AUTHOR = COALESCE(:p_author, li.AUTHOR),
                PUBLISHER = COALESCE(:p_publisher, li.PUBLISHER),
                GENERAL_NOTES = COALESCE(:p_notes, li.GENERAL_NOTES),
                TAGS_JSON = COALESCE(:p_tags, li.TAGS_JSON),
                PERSONAL_NOTE_CATEGORY = COALESCE(:p_category, li.PERSONAL_NOTE_CATEGORY),
                UPDATED_AT = CURRENT_TIMESTAMP
        '''
        cursor.execute(sql, {
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
        logger.warning(f"Failed to upsert library item metadata for {item.book_id}: {e}")
"""

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

if "_upsert_library_item_meta" not in text:
    # Insert definition after _build_item_text
    text = text.replace('def _write_quarantine', patch_code + '\n\ndef _write_quarantine')

    # Add call to _upsert_library_item_meta inside the main loop
    # Right after item validation
    insertion_point = """
            try:
                if dry_run:
"""
    new_insertion = """
            # Upsert library item FULL metadata early
            try:
                with DatabaseManager.get_write_connection() as _conn:
                    with _conn.cursor() as _cursor:
                        _upsert_library_item_meta(_cursor, scope_uid, item)
                    _conn.commit()
            except Exception as meta_ex:
                logger.warning(f"Meta upsert failed: {meta_ex}")

            try:
                if dry_run:
"""
    text = text.replace(insertion_point, new_insertion)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)
print("Patched firestore_sync_service.py")
