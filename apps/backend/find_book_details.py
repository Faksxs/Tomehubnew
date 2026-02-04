import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def find_book_details(search_term):
    conn = DatabaseManager.get_read_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT DISTINCT title, source_type, book_id FROM TOMEHUB_CONTENT WHERE LOWER(title) LIKE :search"
        cursor.execute(query, {"search": f"%{search_term.lower()}%"})
        rows = cursor.fetchall()
        
        print(f"{'TYPE':<10} | {'TITLE':<50} | {'BOOK_ID'}")
        print("-" * 100)
        for type, title, book_id in rows:
            print(f"{str(type):<10} | {str(title):<50} | {book_id}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    find_book_details("Devlet Ana")
    print("\n" + "="*80 + "\n")
    find_book_details("Ahlak Felsefesi")
