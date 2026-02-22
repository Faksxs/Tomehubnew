import sys, os
sys.path.insert(0, os.path.join('.', 'apps', 'backend'))
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'TOMEHUB_CONCEPTS' ORDER BY COLUMN_ID")
            for col in cursor.fetchall():
                print(col[0])
finally:
    DatabaseManager.close_pool()
