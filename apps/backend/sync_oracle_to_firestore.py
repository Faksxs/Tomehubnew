
import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_oracle_firestore")

async def sync_user_data(target_uid: str):
    if not settings.FIREBASE_READY:
        logger.error("Firebase Admin SDK is not ready. Check GOOGLE_APPLICATION_CREDENTIALS.")
        return

    from firebase_admin import firestore
    db = firestore.client()

    logger.info(f"Starting synchronization for UID: {target_uid}")

    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()

        # 1. Fetch Books
        logger.info("Fetching books from Oracle...")
        cursor.execute(
            "SELECT ITEM_ID, TITLE, AUTHOR, CREATED_AT FROM TOMEHUB_LIBRARY_ITEMS WHERE FIREBASE_UID = :p_uid",
            {"p_uid": target_uid}
        )
        books_rows = cursor.fetchall()
        logger.info(f"Found {len(books_rows)} items in Oracle.")

        for b_id, b_title, b_author, b_created_at in books_rows:
            logger.info(f"Processing item: {b_title} ({b_id})")
            
            # 2. Fetch Highlights/Insights for this item
            cursor.execute(
                "SELECT ID, CONTENT_TYPE, CONTENT_CHUNK, PAGE_NUMBER, CREATED_AT FROM TOMEHUB_CONTENT_V2 "
                "WHERE FIREBASE_UID = :p_uid AND ITEM_ID = :p_bid AND CONTENT_TYPE IN ('HIGHLIGHT', 'INSIGHT')",
                {"p_uid": target_uid, "p_bid": b_id}
            )
            content_rows = cursor.fetchall()
            
            highlights = []
            for c_id, c_type, c_chunk, c_page, c_created in content_rows:
                content_text = safe_read_clob(c_chunk)
                
                # Convert created_at to timestamp
                created_ts = int(c_created.timestamp() * 1000) if isinstance(c_created, datetime) else int(datetime.utcnow().timestamp() * 1000)
                
                highlights.append({
                    "id": c_id,
                    "text": content_text,
                    "type": c_type,
                    "pageNumber": c_page,
                    "createdAt": created_ts,
                    "tags": [],
                    "isFavorite": False
                })

            # 3. Create LibraryItem for Firestore
            added_at = int(b_created_at.timestamp() * 1000) if isinstance(b_created_at, datetime) else int(datetime.utcnow().timestamp() * 1000)
            
            library_item = {
                "id": b_id,
                "title": b_title,
                "author": b_author or "Unknown Author",
                "type": "PDF", # Defaulting to PDF as most books here seem to be PDFs
                "addedAt": added_at,
                "tags": [],
                "highlights": highlights,
                "contentLanguageMode": "AUTO",
                "isAnalyzed": False
            }

            # 4. Write to Firestore
            doc_ref = db.collection("users").document(target_uid).collection("items").document(b_id)
            doc_ref.set(library_item, merge=True)
            logger.info(f"Successfully synced book '{b_title}' with {len(highlights)} highlights.")

        cursor.close()
        conn.close()
        logger.info("Synchronization complete.")

    except Exception as e:
        logger.exception(f"Error during synchronization: {e}")

if __name__ == "__main__":
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    asyncio.run(sync_user_data(uid))
