
import sys
import os

# Add 'backend' directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import DatabaseManager
import oracledb

def check_lock():
    print("Checking DBMS_LOCK privileges...")
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Try to allocate a unique handle (safe test)
                lock_name = "TEST_LOCK_1"
                handle = cursor.var(str)
                cursor.callproc("DBMS_LOCK.ALLOCATE_UNIQUE", [lock_name, handle])
                print("DBMS_LOCK.ALLOCATE_UNIQUE successful.")
                
                # Try to request
                res = cursor.callfunc("DBMS_LOCK.REQUEST", int, [handle, 6, 2, True]) # 6=X_MODE, Timeout=2
                print(f"DBMS_LOCK.REQUEST result: {res} (0=Success)")
                
                # Release
                cursor.callfunc("DBMS_LOCK.RELEASE", int, [handle])
                print("DBMS_LOCK.RELEASE successful.")
                
    except oracledb.DatabaseError as e:
        error, = e.args
        print(f"Database Error: {error.message}")
        if "PLS-00201" in error.message:
            print("DBMS_LOCK is NOT accessible (PLS-00201).")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if DatabaseManager._pool:
            DatabaseManager.close_pool()

if __name__ == "__main__":
    check_lock()
