import os
import sys

# Add apps/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def check():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT BOOK_ID, FIREBASE_UID, SOURCE_FILE_NAME, STATUS, UPDATED_AT 
                    FROM TOMEHUB_INGESTED_FILES 
                    WHERE SOURCE_FILE_NAME LIKE '%Klasik%' OR SOURCE_FILE_NAME LIKE '%Sosyoloji%'
                ''')
                rows = cursor.fetchall()
                print('--- TOMEHUB_INGESTED_FILES ---')
                for r in rows:
                    print(r)
                
                cursor.execute('''
                    SELECT id, title, firebase_uid
                    FROM TOMEHUB_BOOKS 
                    WHERE title LIKE '%Klasik Sosyoloji%'
                ''')
                books = cursor.fetchall()
                print('--- TOMEHUB_BOOKS ---')
                for b in books:
                    print(b)
                    
                cursor.execute('''
                    SELECT count(*) 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE '%Klasik Sosyoloji%'
                ''')
                c = cursor.fetchone()
                print('--- TOMEHUB_CONTENT CHUNKS ---')
                print(c)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    check()
