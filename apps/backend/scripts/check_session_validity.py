
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def check_validity():
    print("=== Checking Logic Validity ===")
    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        # 1. Check CHAT_SESSIONS range
        cursor.execute("SELECT count(*), MIN(ID), MAX(ID) FROM TOMEHUB_CHAT_SESSIONS")
        c_count, c_min, c_max = cursor.fetchone()
        print(f"CHAT_SESSIONS: {c_count} rows. Range: {c_min}-{c_max}")
        
        # 2. Check FLOW_SEEN valid candidates
        cursor.execute("""
            SELECT count(*) FROM TOMEHUB_FLOW_SEEN 
            WHERE REGEXP_LIKE(session_id, '^[0-9]+$')
        """)
        valid_candidates = cursor.fetchone()[0]
        print(f"FLOW_SEEN: {valid_candidates} numeric-like IDs (Potential matches)")
        
        # 3. Check SEARCH_LOGS matches
        # We know they are all numeric from previous step, let's see if they exist in CHAT_SESSIONS
        cursor.execute("""
            SELECT count(*) FROM TOMEHUB_SEARCH_LOGS l
            WHERE l.session_id IN (SELECT TO_CHAR(ID) FROM TOMEHUB_CHAT_SESSIONS)
        """)
        matched_search = cursor.fetchone()[0]
        print(f"SEARCH_LOGS: {matched_search} records match active sessions.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    check_validity()
