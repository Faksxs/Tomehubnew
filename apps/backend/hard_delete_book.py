import os
import sys
import io

# Handle Turkish encoding in windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def hard_delete():
    print("Starting deletion for Hayatin Anlami / Terry Eagleton...")
    DatabaseManager.init_pool()
    
    patterns = [
        "%Hayat%Anlam%",
        "%Hayatin%Anlami%",
        "%Eagleton%",
        "%Terry%Eagleton%"
    ]
    
    total_deleted = 0
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Identify Book IDs to delete
                book_ids = set()
                for pat in patterns:
                    # Check TOMEHUB_CONTENT for Book IDs associated with these titles
                    cursor.execute("SELECT DISTINCT book_id FROM TOMEHUB_CONTENT WHERE title LIKE :p_title AND book_id IS NOT NULL", {"p_title": pat})
                    rows = cursor.fetchall()
                    for r in rows:
                         book_ids.add(r[0])
                
                print(f"--> Found {len(book_ids)} related Book IDs: {book_ids}")
                
                # 2. Delete by Book ID from auxiliary tables
                for bid in book_ids:
                    # REPORTS (Confirmed to have BOOK_ID)
                    cursor.execute("DELETE FROM TOMEHUB_FILE_REPORTS WHERE book_id = :p_bid", {"p_bid": bid})
                    print(f"Deleted REPORTS for {bid}")
                    
                    # FLOW SEEN -> Skipped (No book_id column)
                    
                    # CONTENT table (by ID)
                    cursor.execute("DELETE FROM TOMEHUB_CONTENT WHERE book_id = :p_bid", {"p_bid": bid})
                    print(f"Deleted CONTENT for {bid}")

                # 3. Clean sweep Remaining Content by Title pattern (Ghost Chunks without book_id)
                for pat in patterns:
                     cursor.execute("DELETE FROM TOMEHUB_CONTENT WHERE title LIKE :p_title", {"p_title": pat})
                     print(f"Cleaned residual chunks for pattern '{pat}'")
                
                conn.commit()
                print(f"DONE. Complete cleanup finished.")
                
    except Exception as e:
        print(f"Error during deletion: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    hard_delete()
