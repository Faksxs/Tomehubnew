import os
import sys
import logging
import traceback
from typing import List, Dict

# Add backend dir to path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager
from services.report_service import generate_file_report

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("backfill_reports")

def get_books_needing_reports() -> List[Dict]:
    """Find library items that dont have reports yet."""
    items = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Select books/articles that don't have a record in TOMEHUB_FILE_REPORTS
                query = """
                    SELECT li.ITEM_ID, li.FIREBASE_UID, li.TITLE
                    FROM TOMEHUB_LIBRARY_ITEMS li
                    LEFT JOIN TOMEHUB_FILE_REPORTS fr 
                      ON li.ITEM_ID = fr.BOOK_ID AND li.FIREBASE_UID = fr.FIREBASE_UID
                    WHERE li.ITEM_TYPE IN ('BOOK', 'ARTICLE')
                      AND fr.BOOK_ID IS NULL
                """
                cursor.execute(query)
                for row in cursor.fetchall():
                    items.append({
                        "id": row[0],
                        "uid": row[1],
                        "title": row[2]
                    })
    except Exception as e:
        logger.error(f"Failed to fetch books: {e}")
    return items

def run_backfill(limit: int = 50):
    logger.info("Starting File Report Backfill...")
    items = get_books_needing_reports()
    
    if not items:
        logger.info("No books need reports. Everything is up to date.")
        return

    logger.info(f"Found {len(items)} books needing reports. Processing up to {limit}.")
    
    processed = 0
    success_count = 0
    
    for item in items[:limit]:
        processed += 1
        logger.info(f"[{processed}/{min(len(items), limit)}] Processing: {item['title']} ({item['id']})")
        
        try:
            # generate_file_report already handles DB merge
            success = generate_file_report(item['id'], item['uid'])
            if success:
                success_count += 1
                logger.info(f"  ✓ Success")
            else:
                logger.warning(f"  ✗ Failed (no chunks or other issue)")
        except Exception as e:
            logger.error(f"  ! Error processing {item['id']}: {e}")
            # Continue to next item
            
    logger.info(f"Backfill finished. Processed: {processed}, Success: {success_count}")

if __name__ == "__main__":
    # You can pass a limit as an argument
    batch_limit = 10
    if len(sys.argv) > 1:
        try:
            batch_limit = int(sys.argv[1])
        except ValueError:
            pass
            
    run_backfill(batch_limit)
