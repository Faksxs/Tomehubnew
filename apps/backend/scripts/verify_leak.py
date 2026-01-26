import sys
import os
import time

# Add 'backend' directory to sys.path so 'config.py' can be found
# backend/scripts/verify_leak.py -> .. -> backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import DatabaseManager
from services.search_system.strategies import ExactMatchStrategy

def test_leak():
    try:
        DatabaseManager.init_pool()
        print("Pool initialized.")
        
        pool = DatabaseManager._pool
        if not pool:
            print("Pool failed to init")
            return

        initial_busy = pool.busy
        print(f"Initial Busy Connections: {initial_busy}")

        strategy = ExactMatchStrategy()
        results = strategy.search("test", "test_uid_001")
        print(f"Search results: {len(results)}")
        
        final_busy = pool.busy
        print(f"Final Busy Connections: {final_busy}")
        
        if final_busy > initial_busy:
            print("FAIL: Connection leak detected!")
        else:
            print("SUCCESS: No leak detected.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if DatabaseManager._pool:
            DatabaseManager.close_pool()

if __name__ == "__main__":
    test_leak()
