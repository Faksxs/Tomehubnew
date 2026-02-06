
import sys
import os

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager


def diag():
    with open("diag_result.txt", "w", encoding="utf-8") as f:
        def log(msg):
            print(msg)
            f.write(msg + "\n")
            
        log("=== Diagnostic: Schema Check ===")
        try:
            DatabaseManager.init_pool()
            conn = DatabaseManager.get_read_connection()
            cursor = conn.cursor()
            
            # 1. Check for TOMEHUB_BOOKS
            log("\n[1] Checking TOMEHUB_BOOKS...")
            cursor.execute("SELECT count(*) FROM user_tables WHERE table_name = 'TOMEHUB_BOOKS'")
            exists = cursor.fetchone()[0]
            if exists:
                log("YES: TOMEHUB_BOOKS table exists.")
                cursor.execute("SELECT count(*) FROM TOMEHUB_BOOKS")
                count = cursor.fetchone()[0]
                log(f"     Row count: {count}")
            else:
                log("NO: TOMEHUB_BOOKS table DOES NOT exist.")
                # Check for generic BOOKS
                cursor.execute("SELECT count(*) FROM user_tables WHERE table_name = 'BOOKS'")
                if cursor.fetchone()[0]:
                    log("     Found 'BOOKS' table instead.")

            # 2. Check SESSION_ID types
            log("\n[2] Checking SESSION_ID types...")
            tables_to_check = [
                ('TOMEHUB_CHAT_SESSIONS', 'ID'), 
                ('TOMEHUB_FLOW_SEEN', 'SESSION_ID'),
                ('TOMEHUB_SEARCH_LOGS', 'SESSION_ID')
            ]
            
            for table, col in tables_to_check:
                try:
                    cursor.execute(f"""
                        SELECT data_type, data_length, data_precision 
                        FROM user_tab_cols 
                        WHERE table_name = '{table}' AND column_name = '{col}'
                    """)
                    row = cursor.fetchone()
                    if row:
                        log(f"  {table}.{col}: {row[0]} (Len: {row[1]}, Prec: {row[2]})")
                    else:
                        log(f"  {table}.{col}: COLUMN NOT FOUND")
                except Exception as e:
                    log(f"  {table}.{col}: Error {e}")

        except Exception as e:
            log(f"FATAL: {e}")
        finally:
            try:
                if 'cursor' in locals() and cursor:
                    cursor.close()
                if 'conn' in locals() and conn:
                    conn.close()
                DatabaseManager.close_pool()
            except Exception as e:
                log(f"Cleanup Error: {e}")

if __name__ == "__main__":
    diag()
