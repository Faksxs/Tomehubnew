import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
try:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT column_name, data_type FROM all_tab_columns WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'")
            cols = cur.fetchall()
            for col in cols:
                print(f"{col[0]}: {col[1]}")
finally:
    DatabaseManager.close_pool()
