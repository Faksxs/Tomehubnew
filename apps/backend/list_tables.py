
import os
import sys
import io

# Handle encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from infrastructure.db_manager import DatabaseManager

def list_tables():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM user_tables")
                rows = cursor.fetchall()
                print("--- VALID TABLES ---")
                for r in rows:
                    print(r[0])
    except Exception as e:
        print(e)
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    list_tables()
