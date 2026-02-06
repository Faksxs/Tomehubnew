
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def check_columns():
    print("=== Checking TOMEHUB_CHAT_SESSIONS Columns ===")
    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT column_name, data_type, data_length 
            FROM user_tab_cols 
            WHERE table_name = 'TOMEHUB_CHAT_SESSIONS'
        """)
        
        rows = cursor.fetchall()
        print(f"{'COLUMN':<20} | {'TYPE':<10} | {'LENGTH'}")
        print("-" * 40)
        for col, dtype, dlen in rows:
            print(f"{col:<20} | {dtype:<10} | {dlen}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    check_columns()
