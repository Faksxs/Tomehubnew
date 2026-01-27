
import os
import sys
import oracledb

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.db_manager import DatabaseManager
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

def check_data():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Check total rows
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
            total = cursor.fetchone()[0]
            
            # Check rows with BOOK_ID
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE BOOK_ID IS NOT NULL")
            with_id = cursor.fetchone()[0]
            
            print(f"Total Content Rows: {total}")
            print(f"Rows with BOOK_ID: {with_id}")
            
            if with_id < total:
                print("WARNING: Some content has missing BOOK_ID. Memory Layer requires BOOK_ID.")
                
            # Sample BOOK_IDs
            if with_id > 0:
                cursor.execute("SELECT DISTINCT BOOK_ID FROM TOMEHUB_CONTENT WHERE BOOK_ID IS NOT NULL FETCH FIRST 5 ROWS ONLY")
                print("Sample IDs:", cursor.fetchall())

if __name__ == "__main__":
    check_data()
