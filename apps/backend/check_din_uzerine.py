import asyncio
import os
import sys

# Add the app path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def check_book_status(title_keyword="Din Uzerine"):
    print(f"Checking status for book containing: '{title_keyword}'")
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            # Check chunks count based on title
            cursor.execute("""
                SELECT book_id, COUNT(id), SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END)
                FROM TOMEHUB_CONTENT
                WHERE title LIKE :p_title
                GROUP BY book_id
                FETCH FIRST 1 ROWS ONLY
            """, {"p_title": f"%{title_keyword}%"})
            
            row = cursor.fetchone()
            if not row:
                print("1. Chunks: Not Found. The book was not ingested properly.")
                return
            
            book_id, total_chunks, vector_chunks = row
            print(f"1. Book ID: {book_id}")
            print(f"2. Chunks: {total_chunks} total, {vector_chunks} with vectors")
            
            # Check file reports
            cursor.execute("""
                SELECT COUNT(*)
                FROM TOMEHUB_FILE_REPORTS
                WHERE book_id = :p_bid
            """, {"p_bid": book_id})
            
            reports_row = cursor.fetchone()
            print(f"3. File Report Exists: {reports_row[0] > 0}")

if __name__ == "__main__":
    check_book_status()
