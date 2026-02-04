
import os
import sys
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager
from config import settings

def check():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                print("Checking source types for all content...")
                cursor.execute("SELECT source_type, COUNT(*) FROM TOMEHUB_CONTENT GROUP BY source_type")
                for row in cursor.fetchall():
                    print(f"Type: {row[0]}, Count: {row[1]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
