
import sys
import os
import time
import hashlib
import oracledb

# Add 'backend' directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import DatabaseManager, acquire_lock

def verify_lock_logic():
    print("Verifying lock logic...")
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Simulate the key generation used in ingest_book
                title = "Test Book"
                author = "Test Author"
                if len(sys.argv) < 2:
                    print("Usage: python test_lock_mechanics.py <uid>")
                    sys.exit(1)
                uid = sys.argv[1]
                safe_key = hashlib.md5(f"{title}_{author}".encode('utf-8')).hexdigest()
                lock_name = f"ingest_{uid}_{safe_key}"
                
                print(f"Attempting to acquire lock: {lock_name}")
                acquire_lock(cursor, lock_name, timeout=2)
                print("Lock acquired successfully.")
                
                # Check if we can re-acquire (re-entrancy test for same session)
                print("Attempting re-entrant acquire...")
                acquire_lock(cursor, lock_name, timeout=2)
                print("Re-entrant acquire successful (expected for Oracle DBMS_LOCK).")
                
                # Lock releases on commit/rollback or session end
                conn.commit()
                print("Transaction committed. Lock released.")
                
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)
    finally:
         if DatabaseManager._pool:
            DatabaseManager.close_pool()

if __name__ == "__main__":
    verify_lock_logic()
