import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
with DatabaseManager.get_read_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'TOMEHUB_BOOKS'")
    books_cols = [r[0] for r in cursor.fetchall()]
    print('TOMEHUB_BOOKS:', ','.join(books_cols))
    
    cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'")
    items_cols = [r[0] for r in cursor.fetchall()]
    print('TOMEHUB_LIBRARY_ITEMS:', ','.join(items_cols))
