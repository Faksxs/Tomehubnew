import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def view_vector_indexes():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                print('--- VECTOR INDEXES PENDING ---')
                cur.execute("SELECT index_name, table_name, index_type, status FROM user_indexes WHERE index_type LIKE '%VECTOR%'")
                inds = cur.fetchall()
                for i in inds:
                    print(f'{i[0]} on {i[1]} ({i[2]}) - Status: {i[3]}')
                if not inds:
                    print('No vector indexes found!')
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    view_vector_indexes()
