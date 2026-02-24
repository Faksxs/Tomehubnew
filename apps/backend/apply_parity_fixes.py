import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def apply_parity_fixes():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cur:
                print('--- 1. FIXING PDF ITEM TYPE ANOMALY ---')
                cur.execute("UPDATE TOMEHUB_LIBRARY_ITEMS SET ITEM_TYPE = 'BOOK' WHERE ITEM_TYPE = 'PDF'")
                print(f'Updated {cur.rowcount} lines from PDF to BOOK in TOMEHUB_LIBRARY_ITEMS.')
                
                print('--- 2. ADDING MISSING COLUMNS FROM TYPES.TS ---')
                cols_to_add = [
                    'CONTENT_LANGUAGE_MODE VARCHAR2(50)',
                    'CONTENT_LANGUAGE_RESOLVED VARCHAR2(50)',
                    'SOURCE_LANGUAGE_HINT VARCHAR2(50)',
                    'LANGUAGE_DECISION_REASON VARCHAR2(255)',
                    'LANGUAGE_DECISION_CONFIDENCE NUMBER',
                    'PERSONAL_FOLDER_ID VARCHAR2(255)',
                    'FOLDER_PATH CLOB'
                ]
                for col_def in cols_to_add:
                    try:
                        cur.execute(f"ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD ({col_def})")
                        print(f'Added column: {col_def}')
                    except Exception as e:
                        if 'ORA-01430' in str(e): # column being added already exists
                            print(f'Column already exists: {col_def}')
                        else:
                            print(f'Error adding {col_def}: {e}')
                            
                print('--- 3. FIXING MULTI-TENANT KEY AMBIGUITY ---')
                try:
                    cur.execute("ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD CONSTRAINT uq_lib_items_id UNIQUE (ITEM_ID)")
                    print('Added UNIQUE constraint on ITEM_ID.')
                except Exception as e:
                    print(f'Unique constraint note: {e}')
                    
                print('--- 4. DOMAIN CONSTRAINTS ---')
                try:
                    cur.execute("ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD CONSTRAINT chk_lib_item_type CHECK (ITEM_TYPE IN ('BOOK', 'ARTICLE', 'WEBSITE', 'PERSONAL_NOTE', 'HIGHLIGHT', 'INSIGHT'))")
                    print('Added CHECK constraint for ITEM_TYPE.')
                except Exception as e:
                    print(f'Check constraint note: {e}')
                    
                print('--- 5. ADDING FOREIGN KEY FOR TOMEHUB_CONTENT_V2 ORPHANS ---')
                try:
                    # First, we need to ensure the parent is unique to use it as an FK target (FIREBASE_UID, ITEM_ID)
                    cur.execute("ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD CONSTRAINT uq_lib_items_composite UNIQUE (FIREBASE_UID, ITEM_ID)")
                    print('Added UNIQUE composite constraint.')
                except Exception as e:
                    print(f'Composite unique note: {e}')
                    
                try:
                    # Clean up the 1 orphan in TOMEHUB_CONTENT_V2 we discovered earlier
                    cur.execute("""
                    DELETE FROM TOMEHUB_CONTENT_V2 
                    WHERE (FIREBASE_UID, ITEM_ID) NOT IN (
                        SELECT FIREBASE_UID, ITEM_ID FROM TOMEHUB_LIBRARY_ITEMS
                    )
                    """)
                    print(f'Deleted {cur.rowcount} orphan rows in TOMEHUB_CONTENT_V2.')
                    
                    # Add FK
                    cur.execute("""
                    ALTER TABLE TOMEHUB_CONTENT_V2 
                    ADD CONSTRAINT fk_content_v2_to_lib 
                    FOREIGN KEY (FIREBASE_UID, ITEM_ID) REFERENCES TOMEHUB_LIBRARY_ITEMS(FIREBASE_UID, ITEM_ID)
                    """)
                    print('Added FOREIGN KEY from TOMEHUB_CONTENT_V2 to TOMEHUB_LIBRARY_ITEMS.')
                except Exception as e:
                    print(f'FK constraint note: {e}')
                    
                conn.commit()
    except Exception as e:
        print(f'General error: {e}')
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    apply_parity_fixes()
