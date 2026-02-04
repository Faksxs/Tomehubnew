
import os
import sys
import io

# Handle encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from infrastructure.db_manager import DatabaseManager

def inspect_columns():
    DatabaseManager.init_pool()
    try:
        with open("cols_dump.txt", "w", encoding="utf-8") as f:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    # Check FILE_REPORTS
                    f.write("\n--- TOMEHUB_FILE_REPORTS Columns ---\n")
                    cursor.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'TOMEHUB_FILE_REPORTS'")
                    for r in cursor.fetchall():
                        f.write(str(r) + "\n")

                    # Check FLOW_SEEN
                    f.write("\n--- TOMEHUB_FLOW_SEEN Columns ---\n")
                    cursor.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'TOMEHUB_FLOW_SEEN'")
                    for r in cursor.fetchall():
                         f.write(str(r) + "\n")

    except Exception as e:
        print(e)
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    inspect_columns()
