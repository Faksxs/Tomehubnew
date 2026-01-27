
import os
import sys
import uuid
import oracledb

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.db_manager import DatabaseManager
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

def fix_ids():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Find groups without ID
            cursor.execute("""
                SELECT DISTINCT TITLE, FIREBASE_UID 
                FROM TOMEHUB_CONTENT 
                WHERE BOOK_ID IS NULL
            """)
            
            groups = cursor.fetchall()
            print(f"Found {len(groups)} legacy books without IDs.")
            
            updated_books = 0
            
            for title, uid in groups:
                new_id = str(uuid.uuid4())
                print(f"Assigning {new_id} to '{title}'...")
                
                cursor.execute("""
                    UPDATE TOMEHUB_CONTENT
                    SET BOOK_ID = :bid
                    WHERE TITLE = :title AND FIREBASE_UID = :p_uid AND BOOK_ID IS NULL
                """, {"bid": new_id, "title": title, "p_uid": uid})
                
                updated_books += 1
                
            conn.commit()
            print(f"Fixed {updated_books} books.")

if __name__ == "__main__":
    fix_ids()
