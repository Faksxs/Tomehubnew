import os
import sys
import oracledb
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'apps', 'backend', '.env')
load_dotenv(dotenv_path=env_path)

def get_database_connection():
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN", "tomehubdb_high")
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'apps', 'backend')
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    try:
        connection = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet_location,
            wallet_location=wallet_location,
            wallet_password=password
        )
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def check_book_content(title):
    connection = get_database_connection()
    if not connection:
        return
    
    try:
        cursor = connection.cursor()
        # Query to see if any content exists for this title
        # The title in TOMEHUB_CONTENT is often "Title - Author"
        query = """
        SELECT DISTINCT title, firebase_uid 
        FROM TOMEHUB_CONTENT 
        WHERE LOWER(title) LIKE :p_title
        """
        cursor.execute(query, {"p_title": f"%{title.lower()}%"})
        rows = cursor.fetchall()
        
        if rows:
            print(f"Found content matches for '{title}':")
            for row in rows:
                print(f"  - Title-Author: {row[0]} | User: {row[1]}")
        else:
            print(f"No content found for '{title}' in the AI library (TOMEHUB_CONTENT table).")
            
        cursor.close()
    finally:
        connection.close()

if __name__ == "__main__":
    search_title = "Mahur Beste"
    if len(sys.argv) > 1:
        search_title = sys.argv[1]
    
    check_book_content(search_title)
