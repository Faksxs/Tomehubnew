
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def analyze_session_ids():
    print("=== Analyzing SESSION_ID Data Types ===")
    
    tables_to_check = ['TOMEHUB_FLOW_SEEN', 'TOMEHUB_SEARCH_LOGS']
    
    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        for table in tables_to_check:
            print(f"\nChecking table: {table}")
            
            # 1. Total Count
            cursor.execute(f"SELECT count(*) FROM {table}")
            total = cursor.fetchone()[0]
            print(f"  Total Rows: {total}")
            
            if total == 0:
                print("  (Empty table, safe to convert)")
                continue

            # 2. Check for Non-Numeric
            # REGEXP_LIKE(column, '^[[:digit:]]+$') returns true for only digits
            query = f"""
                SELECT count(*), MIN(session_id), MAX(session_id)
                FROM {table} 
                WHERE session_id IS NOT NULL 
                AND NOT REGEXP_LIKE(session_id, '^[0-9]+$')
            """
            cursor.execute(query)
            non_numeric_count, sample_min, sample_max = cursor.fetchone()
            
            if non_numeric_count > 0:
                print(f"  ⚠️ WARNING: Found {non_numeric_count} non-numeric SESSION_IDs!")
                print(f"  Sample: {sample_min} ... {sample_max}")
            else:
                print("  ✅ All SESSION_IDs are numeric. Safe to convert.")

    except Exception as e:
        print(f"FATAL DB Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    analyze_session_ids()
