import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))
from services.ingestion_service import get_database_connection

def check_pdf_books():
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT title, book_id
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :p_uid AND source_type = 'PDF'
        """
        cursor.execute(query, {"p_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"})
        rows = cursor.fetchall()
        
        print(f"PDF books found: {len(rows)}")
        for row in rows:
            print(f"  - {row[0]}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_pdf_books()
