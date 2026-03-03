import os
import json
import sys
import logging
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("migration")

# Add backend dir to path for imports
backend_dir = r"c:\Users\aksoy\Desktop\yeni tomehub\apps\backend"
sys.path.append(backend_dir)
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.category_taxonomy_service import normalize_book_category_label

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, '.env'))

def migrate_db_categories():
    DatabaseManager.init_pool()
    conn = DatabaseManager.get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Update TOMEHUB_CONTENT (CATEGORIES column is comma-separated strings)
        logger.info("Updating TOMEHUB_CONTENT.CATEGORIES...")
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name = 'TOMEHUB_CONTENT'")
        if cursor.fetchone():
            cursor.execute("SELECT ID, CATEGORIES FROM TOMEHUB_CONTENT WHERE CATEGORIES IS NOT NULL")
            rows = cursor.fetchall()
            
            update_count = 0
            for row_id, cats_str in rows:
                if not cats_str: continue
                
                old_cats = [c.strip() for c in cats_str.split(',') if c.strip()]
                new_cats = []
                seen = set()
                
                for cat in old_cats:
                    canonical = normalize_book_category_label(cat)
                    if canonical and canonical not in seen:
                        new_cats.append(canonical)
                        seen.add(canonical)
                
                new_cats_str = ",".join(new_cats)
                if new_cats_str != cats_str:
                    cursor.execute("UPDATE TOMEHUB_CONTENT SET CATEGORIES = :cats WHERE ID = :rid", {"cats": new_cats_str, "rid": row_id})
                    update_count += 1
        
        conn.commit()
        logger.info(f"Updated {update_count} records in TOMEHUB_CONTENT.")

        # 2. Update TOMEHUB_LIBRARY_ITEMS (TAGS_JSON and CATEGORY_JSON)
        # Assuming TAGS_JSON/CATEGORY_JSON are CLOBs containing JSON arrays
        logger.info("Updating TOMEHUB_LIBRARY_ITEMS...")
        
        cursor.execute("SELECT table_name FROM user_tables WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'")
        if cursor.fetchone():
            cursor.execute("SELECT ID, TAGS_JSON FROM TOMEHUB_LIBRARY_ITEMS WHERE TAGS_JSON IS NOT NULL")
            lib_rows = cursor.fetchall()
            lib_update_count = 0
            
            for lib_id, tags_clob in lib_rows:
                tags_str = safe_read_clob(tags_clob)
                try:
                    tags = json.loads(tags_str)
                    if not isinstance(tags, list): continue
                    
                    new_tags = []
                    changed = False
                    seen = set()
                    
                    for tag in tags:
                        canonical = normalize_book_category_label(tag)
                        if canonical:
                            if canonical not in seen:
                                new_tags.append(canonical)
                                seen.add(canonical)
                                if canonical != tag: changed = True
                        else:
                            # If it's not a category, keep it as is (might be a generic tag)
                            if tag not in seen:
                                new_tags.append(tag)
                                seen.add(tag)
                    
                    if changed or len(new_tags) != len(tags):
                        cursor.execute("UPDATE TOMEHUB_LIBRARY_ITEMS SET TAGS_JSON = :tags WHERE ID = :rid", 
                                     {"tags": json.dumps(new_tags, ensure_ascii=False), "rid": lib_id})
                        lib_update_count += 1
                except:
                    continue
            
            conn.commit()
            logger.info(f"Updated {lib_update_count} records in TOMEHUB_LIBRARY_ITEMS.")
        
        logger.info("Migration finished successfully.")
        
    except Exception as e:
        logger.error(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()
        DatabaseManager.close_pool()

if __name__ == "__main__":
    migrate_db_categories()
