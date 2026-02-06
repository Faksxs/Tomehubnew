import oracledb
import os
from dotenv import load_dotenv
import sys
from infrastructure.db_manager import DatabaseManager

# Force UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def list_books():
    print("Connecting to database...")
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Query from Master Table TOMEHUB_BOOKS
                query = """
                    SELECT title, 'BOOK' as source_type, id as book_id, total_chunks as chunk_count
                    FROM TOMEHUB_BOOKS
                    ORDER BY title
                """
                cursor.execute(query)
                rows = cursor.fetchall()
                
                print(f"\nFound {len(rows)} books in TOMEHUB_BOOKS (Master Table):\n")
                print(f"{'TYPE':<10} | {'TITLE':<60} | {'BOOK_ID':<36} | {'CHUNKS'}")
                print("-" * 60)
                
                for title, source_type, book_id, chunk_count in rows:
                    if not source_type: source_type = "UNKNOWN"
                    print(f"{source_type:<10} | {str(title)[:60]:<60} | {book_id or '':<36} | {chunk_count}")
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        try:
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    list_books()
