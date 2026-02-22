import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def search_books():
    conn = DatabaseManager.get_read_connection()
    bid = '1763947192884s1obi7m9k'
    
    try:
        # Check TOMEHUB_BOOKS columns again to be sure
        cursor = conn.cursor()
        cursor.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'TOMEHUB_BOOKS' ORDER BY column_id")
        cols = [c[0] for c in cursor.fetchall()]
        print(f"Verified Cols in TOMEHUB_BOOKS: {cols}")
        
        # Search by ID
        print(f"\nSearching TOMEHUB_BOOKS for ID: {bid}")
        cursor.execute("SELECT * FROM TOMEHUB_BOOKS WHERE ID = :bid", {"bid": bid})
        row = cursor.fetchone()
        if row:
            print(f"BOOK FOUND: {dict(zip(cols, row))}")
        else:
            print("BOOK NOT FOUND by ID.")
            
        # List most recent 10 books
        print("\n=== RECENT 10 BOOKS IN TOMEHUB_BOOKS ===")
        cursor.execute("SELECT * FROM (SELECT * FROM TOMEHUB_BOOKS ORDER BY CREATED_AT DESC) WHERE ROWNUM <= 10")
        rows = cursor.fetchall()
        for r in rows:
            print(f"Book: {dict(zip(cols, r))}")
        cursor.close()

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    search_books()
