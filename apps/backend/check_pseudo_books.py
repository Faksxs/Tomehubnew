import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def check_pseudo_books():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                print('--- ITEM TYPES IN LIBRARY ---')
                cur.execute("SELECT ITEM_TYPE, COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS GROUP BY ITEM_TYPE")
                for row in cur.fetchall():
                    print(f'{row[0]}: {row[1]}')
                
                print('\\n--- PSEUDO BOOKS ---')
                cur.execute("""
                SELECT ITEM_ID, ITEM_TYPE, TITLE 
                FROM TOMEHUB_LIBRARY_ITEMS 
                WHERE TITLE LIKE '%(Highlight)%' OR TITLE LIKE '%(Note)%'
                """)
                for row in cur.fetchall():
                    print(f'{row[0]} | {row[1]} | {row[2]}')

    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    check_pseudo_books()
