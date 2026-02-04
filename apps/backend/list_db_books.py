import oracledb
import os
from dotenv import load_dotenv
import sys
from infrastructure.db_manager import DatabaseManager

# Force UTF-8 encoding for stdout to handle special characters in book titles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

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
                    SELECT title, source_type, book_id, COUNT(*) as chunk_count
                    FROM TOMEHUB_CONTENT
                    GROUP BY title, source_type, book_id
                    ORDER BY title
                """
                cursor.execute(query)
                rows = cursor.fetchall()
                
                print(f"\nFound {len(rows)} unique book(s) in database:\n")
                print(f"{'TYPE':<10} | {'TITLE':<60} | {'BOOK_ID':<36} | {'CHUNKS'}")
                print("-" * 60)
                
                for title, source_type, book_id, chunk_count in rows:
                    if not source_type: source_type = "UNKNOWN"
                    print(f"{source_type:<10} | {str(title)[:60]:<60} | {book_id or '':<36} | {chunk_count}")
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    list_books()
