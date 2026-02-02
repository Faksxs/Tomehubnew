import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

# Load env for local run
load_dotenv()

def list_books():
    print("Connecting to database...")
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Query distinct titles/authors
                # Note: Schema might store 'Title - Author' in title column based on previous code
                query = """
                    SELECT DISTINCT title, source_type 
                    FROM TOMEHUB_CONTENT
                    ORDER BY title
                """
                cursor.execute(query)
                rows = cursor.fetchall()
                
                print(f"\nFound {len(rows)} unique book(s) in database:\n")
                print(f"{'TYPE':<10} | {'TITLE'}")
                print("-" * 60)
                
                for title, source_type in rows:
                    if not source_type: source_type = "UNKNOWN"
                    print(f"{source_type:<10} | {title}")
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    list_books()
