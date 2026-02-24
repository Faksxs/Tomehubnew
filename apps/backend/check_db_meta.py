import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
try:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ITEM_ID, AUTHOR, PUBLISHER FROM TOMEHUB_LIBRARY_ITEMS WHERE ROWNUM <= 5 AND AUTHOR IS NOT NULL")
            for row in cur.fetchall():
                print(f"ID: {row[0]} | AUTHOR: {row[1]} | PUBLISHER: {row[2]}")
finally:
    DatabaseManager.close_pool()
