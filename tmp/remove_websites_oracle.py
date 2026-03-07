import sys
import os
import asyncio

# Add apps/backend to path so we can import modules
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "backend"))
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager
from config import settings

async def remove_websites():
    print("Initializing DB pool...")
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Delete from TOMEHUB_CONTENT_V2
                cursor.execute("DELETE FROM TOMEHUB_CONTENT_V2 WHERE content_type = 'WEBSITE'")
                content_deleted = cursor.rowcount
                print(f"Deleted {content_deleted} chunks from TOMEHUB_CONTENT_V2")
                
                # 2. Delete from TOMEHUB_LIBRARY_ITEMS
                cursor.execute("DELETE FROM TOMEHUB_LIBRARY_ITEMS WHERE item_type = 'WEBSITE'")
                items_deleted = cursor.rowcount
                print(f"Deleted {items_deleted} items from TOMEHUB_LIBRARY_ITEMS")
                
                conn.commit()
                print("Transaction committed.")
    except Exception as e:
        print(f"Error during deletion: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(remove_websites())
