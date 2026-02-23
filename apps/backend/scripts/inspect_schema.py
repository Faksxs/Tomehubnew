
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def inspect_table(table_name):
    print(f"--- Full Schema for {table_name} ---")
    try:
        with DatabaseManager.get_read_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT column_name, data_type
                FROM user_tab_columns
                WHERE table_name = :p_table
                ORDER BY column_id
            """
            cursor.execute(query, {"p_table": table_name.upper()})
            for row in cursor.fetchall():
                print(f"Column: {row[0]}, Type: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_table("TOMEHUB_FILE_REPORTS")
