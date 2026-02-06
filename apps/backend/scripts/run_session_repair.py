
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def run_repair():
    print("=== Applying Session Integrity Repair ===")
    
    commands = [
        # 1. Cleanup FLOW_SEEN (Invalid UUIDs)
        "DELETE FROM TOMEHUB_FLOW_SEEN WHERE NOT REGEXP_LIKE(SESSION_ID, '^[0-9]+$')",
        
        # 2. Cleanup Orphans (Numeric but not in Chat Sessions)
        # Note: We cast ID to char for comparison with old varchar session_id
        "DELETE FROM TOMEHUB_FLOW_SEEN WHERE SESSION_ID NOT IN (SELECT TO_CHAR(ID) FROM TOMEHUB_CHAT_SESSIONS)",
        
        # 3. Cleanup SEARCH_LOGS
        "DELETE FROM TOMEHUB_SEARCH_LOGS WHERE NOT REGEXP_LIKE(SESSION_ID, '^[0-9]+$')",
        "DELETE FROM TOMEHUB_SEARCH_LOGS WHERE SESSION_ID NOT IN (SELECT TO_CHAR(ID) FROM TOMEHUB_CHAT_SESSIONS)",
        
        # 4. Convert FLOW_SEEN
        "ALTER TABLE TOMEHUB_FLOW_SEEN MODIFY (SESSION_ID NUMBER)",
        
        # 5. Convert SEARCH_LOGS
        "ALTER TABLE TOMEHUB_SEARCH_LOGS MODIFY (SESSION_ID NUMBER)",
        
        # 6. Add Constraints
        "ALTER TABLE TOMEHUB_FLOW_SEEN ADD CONSTRAINT fk_flow_session FOREIGN KEY (SESSION_ID) REFERENCES TOMEHUB_CHAT_SESSIONS(ID) ON DELETE CASCADE",
        "ALTER TABLE TOMEHUB_SEARCH_LOGS ADD CONSTRAINT fk_search_session FOREIGN KEY (SESSION_ID) REFERENCES TOMEHUB_CHAT_SESSIONS(ID) ON DELETE CASCADE"
    ]

    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()
        
        for idx, cmd in enumerate(commands):
            print(f"Exec {idx+1}...")
            try:
                cursor.execute(cmd)
                print("  Success.")
            except Exception as e:
                # ORA-02275: constraint already exists
                # ORA-01439: column to be modified must be empty to change datatype (if conversion fails)
                print(f"  Info/Error: {e}")
                
        conn.commit()
        print("\nSession Integrity Repair Completed.")
        
    except Exception as e:
        print(f"FATAL DB Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    run_repair()
