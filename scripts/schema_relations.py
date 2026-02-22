import sys, os
sys.path.insert(0, os.path.join('.', 'apps', 'backend'))
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
with DatabaseManager.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'TOMEHUB_RELATIONS' ORDER BY COLUMN_ID")
        for col_name, data_type in cursor.fetchall():
            print(f'{col_name}: {data_type}')
DatabaseManager.close_pool()
