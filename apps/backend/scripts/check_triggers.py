
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def check_triggers(table_name):
    print(f"--- Triggers for {table_name} ---")
    try:
        with DatabaseManager.get_read_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT trigger_name, trigger_type, triggering_event
                FROM user_triggers
                WHERE table_name = :p_table
            """
            cursor.execute(query, {"p_table": table_name.upper()})
            for row in cursor.fetchall():
                print(row)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_triggers("TOMEHUB_FILE_REPORTS")
