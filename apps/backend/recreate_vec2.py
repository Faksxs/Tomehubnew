import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def recreate_index():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cur:
                print('Creating fresh vector index on TOMEHUB_CONTENT_V2 (Oracle 23ai Syntax)...')
                try:
                    # In 23ai, default index is often just CREATE VECTOR INDEX ... ON ... (col) ORGANIZATION INMEMORY NEIGHBOR GRAPH ...
                    # But the simplest bulletproof way:
                    cur.execute("""
                        CREATE VECTOR INDEX IDX_CNT_VEC_V2 ON TOMEHUB_CONTENT_V2 (VEC_EMBEDDING) 
                        ORGANIZATION NEIGHBOR PARTITIONS
                        DISTANCE COSINE
                        WITH TARGET ACCURACY 90
                    """)
                    print('Index created successfully!')
                except Exception as e:
                    print(f'Creation Failed: {e}')
                    
                # Double-check status
                cur.execute("SELECT index_name, status FROM user_indexes WHERE index_name = 'IDX_CNT_VEC_V2'")
                status = cur.fetchone()
                if status:
                    print(f'Current Status: {status[0]} -> {status[1]}')
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    recreate_index()
