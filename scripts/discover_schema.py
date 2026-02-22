#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname('.'), 'apps', 'backend'))
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS WHERE TABLE_NAME = 'TOMEHUB_SEARCH_LOGS' ORDER BY COLUMN_ID")
            print('TOMEHUB_SEARCH_LOGS columns:')
            for col_name, data_type in cursor.fetchall():
                print(f'  {col_name}: {data_type}')
finally:
    DatabaseManager.close_pool()
