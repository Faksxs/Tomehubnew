import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def rebuild_index():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cur:
                print('Rebuilding UNUSABLE vector index on TOMEHUB_CONTENT_V2...')
                try:
                    cur.execute("ALTER INDEX IDX_CNT_VEC_V2 REBUILD")
                    print('Index rebuilt successfully!')
                except Exception as e:
                    print(f'Rebuild failed: {e}')
                    
                # Double-check status
                cur.execute("SELECT index_name, status FROM user_indexes WHERE index_name = 'IDX_CNT_VEC_V2'")
                status = cur.fetchone()
                if status:
                    print(f'Current Status: {status[0]} -> {status[1]}')
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    rebuild_index()
