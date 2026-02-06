
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def run_cleanup():
    print("=== Cleaning Orphaned File Reports ===")
    
    commands = [
        "DELETE FROM TOMEHUB_FILE_REPORTS WHERE BOOK_ID IS NOT NULL AND BOOK_ID NOT IN (SELECT ID FROM TOMEHUB_BOOKS)"
    ]

    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()
        
        for idx, cmd in enumerate(commands):
            print(f"Exec {idx+1}...")
            cursor.execute(cmd)
            print(f"  Deleted {cursor.rowcount} orphaned rows.")
                
        conn.commit()
        print("\nCleanup Completed.")
        
    except Exception as e:
        print(f"FATAL DB Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    run_cleanup()
