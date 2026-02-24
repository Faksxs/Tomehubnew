import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def flag_pseudo_books():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cur:
                print('--- ADDING IS_PLACEHOLDER FLAG ---')
                try:
                    cur.execute("ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD (IS_PLACEHOLDER NUMBER(1) DEFAULT 0 NOT NULL CHECK (IS_PLACEHOLDER IN (0, 1)))")
                    print('Added IS_PLACEHOLDER column.')
                except Exception as e:
                    print(f'Add column note: {e}')
                    
                cur.execute("UPDATE TOMEHUB_LIBRARY_ITEMS SET IS_PLACEHOLDER = 1 WHERE TITLE LIKE '%(Highlight)%' OR TITLE LIKE '%(Note)%'")
                print(f'Flagged {cur.rowcount} items as pseudo-books (placeholders).')
                
                # Check the results
                cur.execute("SELECT TITLE FROM TOMEHUB_LIBRARY_ITEMS WHERE IS_PLACEHOLDER = 1")
                for row in cur.fetchall():
                    print(f'  [PLACEHOLDER] {row[0]}')
                
                conn.commit()
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    flag_pseudo_books()
