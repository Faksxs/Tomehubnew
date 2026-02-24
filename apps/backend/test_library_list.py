from infrastructure.db_manager import DatabaseManager
from services.library_service import list_library_items
import time
import logging

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_library")

def test_list():
    try:
        conn = DatabaseManager.get_read_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT FIREBASE_UID FROM TOMEHUB_LIBRARY_ITEMS")
        uids = [r[0] for r in cur.fetchall()]
        print(f"Found UIDs with data: {uids}")
        
        if not uids:
            print("No UIDs found with library items.")
            return

        uid = uids[0]
        print(f"\nTesting library list for real user: {uid}")
        
        start = time.time()
        # We'll just call the service function directly
        result = list_library_items(uid, limit=100)
        print(f"Success! Found {len(result.get('items', []))} items.")
        print(f"Total time: {time.time()-start:.4f}s")
        
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_list()
