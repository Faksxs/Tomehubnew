
import sys
import os
import io

# Fix encoding issues for Windows terminal
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def inspect_table(table_name):
    print(f"START_INSPECT_{table_name}")
    try:
        with DatabaseManager.get_read_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT column_name
                FROM user_tab_columns
                WHERE table_name = :p_table
                ORDER BY column_id
            """
            cursor.execute(query, {"p_table": table_name.upper()})
            for i, row in enumerate(cursor.fetchall()):
                print(f"COL_{i}: {row[0]}")
    except Exception as e:
        print(f"ERROR: {str(e)}")
    print(f"END_INSPECT_{table_name}")

if __name__ == "__main__":
    inspect_table("TOMEHUB_FILE_REPORTS")
