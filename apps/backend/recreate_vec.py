import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def rebuild_index():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cur:
                print('Dropping UNUSABLE vector index IDX_CNT_VEC_V2...')
                try:
                    cur.execute("DROP INDEX IDX_CNT_VEC_V2")
                    print('Dropped.')
                except Exception as e:
                    print(f'Drop failed: {e}')
                
                print('Creating fresh vector index on TOMEHUB_CONTENT_V2...')
                try:
                    cur.execute("""
                        CREATE VECTOR INDEX IDX_CNT_VEC_V2 ON TOMEHUB_CONTENT_V2 (VEC_EMBEDDING) 
                        ORGANIZATION NEIGHBOR GRAPH 
                        DISTANCE COSINE 
                        WITH TARGET ACCURACY 95 
                        PARAMETERS (type HNSW, neighbor_partitions 100, efconstruction 150)
                    """)
                    print('Index created successfully!')
                except Exception as e:
                    print(f'Create failed, retrying simpler index: {e}')
                    try:
                        cur.execute("""
                            CREATE VECTOR INDEX IDX_CNT_VEC_V2 ON TOMEHUB_CONTENT_V2 (VEC_EMBEDDING) 
                        """)
                    except Exception as e2:
                        print(f"Fallback Creation Failed: {e2}")
                    
                # Double-check status
                cur.execute("SELECT index_name, status FROM user_indexes WHERE index_name = 'IDX_CNT_VEC_V2'")
                status = cur.fetchone()
                if status:
                    print(f'Current Status: {status[0]} -> {status[1]}')
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    rebuild_index()
