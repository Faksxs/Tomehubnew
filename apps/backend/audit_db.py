import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def scan_db():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                print("==============================")
                print("TOMEHUB DATABASE SCHEMA AUDIT")
                print("==============================\\n")
                
                # 1. Get all relevant tables
                cur.execute("""
                SELECT table_name 
                FROM user_tables 
                WHERE table_name LIKE 'TOMEHUB_%' 
                ORDER BY table_name
                """)
                tables = [r[0] for r in cur.fetchall()]
                
                print(f"Total Tables Found: {len(tables)}\\n")
                
                for t in tables:
                    print(f"--- TABLE: {t} ---")
                    
                    # Columns and Data Types
                    cur.execute(f"""
                    SELECT column_name, data_type, data_length, nullable 
                    FROM user_tab_cols 
                    WHERE table_name = '{t}'
                    ORDER BY column_id
                    """)
                    cols = cur.fetchall()
                    
                    # Missing indices
                    cur.execute(f"""
                    SELECT index_name, column_name 
                    FROM user_ind_columns 
                    WHERE table_name = '{t}'
                    ORDER BY index_name, column_position
                    """)
                    inds = cur.fetchall()
                    
                    if not inds:
                        print("  [WARNING] NO INDICES FOUND! This will cause Full Table Scans.")
                    else:
                        print(f"  Indices: {len(set(i[0] for i in inds))} found")
                            
                    # Partitioning checks
                    cur.execute(f"""
                    SELECT partitioning_type, partition_count 
                    FROM user_part_tables 
                    WHERE table_name = '{t}'
                    """)
                    parts = cur.fetchall()
                    if parts:
                        print(f"  Partitioning: {parts[0][0]} ({parts[0][1]} partitions)")
                    else:
                        # Recommend partitioning for large tables
                        if t in ['TOMEHUB_CONTENT', 'TOMEHUB_CONTENT_V2', 'TOMEHUB_SEARCH_LOGS', 'TOMEHUB_CHAT_MESSAGES']:
                            print("  [RECOMMENDATION] Large table should be partitioned (Interval-Range or Hash)!")
                        else:
                            print("  Partitioning: None (Acceptable depending on data size)")
                        
                    # primary keys / foreign keys checks
                    cur.execute(f"""
                    SELECT constraint_type, constraint_name 
                    FROM user_constraints 
                    WHERE table_name = '{t}' AND constraint_type IN ('P', 'R')
                    """)
                    cons = cur.fetchall()
                    has_pk = any(c[0] == 'P' for c in cons)
                    has_fk = any(c[0] == 'R' for c in cons)
                    
                    if not has_pk:
                        print("  [CRITICAL] NO PRIMARY KEY DEFINED!")
                    if not has_fk and t in ['TOMEHUB_CONTENT_V2', 'TOMEHUB_CHANGE_EVENTS']:
                        print(f"  [RECOMMENDATION] CONSIDER ADDING FOREIGN KEY TO TOMEHUB_LIBRARY_ITEMS(ITEM_ID) TO ENSURE RELATIONAL INTEGRITY.")
                        
                    # VEC_EMBEDDING checks
                    has_vector = any(c[0] == 'VEC_EMBEDDING' for c in cols)
                    if has_vector:
                        cur.execute(f"""
                        SELECT index_type FROM user_indexes 
                        WHERE table_name = '{t}' AND index_type LIKE '%VECTOR%'
                        """)
                        v_inds = cur.fetchall()
                        if not v_inds:
                            print("  [CRITICAL] HAS VECTOR COLUMN BUT NO VECTOR INDEX (HNSW/IVF)! Vector searches will be extremely slow.")
                            
                    print("")
                        
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    scan_db()
