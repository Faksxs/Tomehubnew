import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def test():
    uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT title, book_id
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :p_uid
        """
        cursor.execute(query, {"p_uid": uid})
        rows = cursor.fetchall()
        
        print(f"Total rows found: {len(rows)}")
        for i, row in enumerate(rows):
            raw_title = row[0]
            title_parts = raw_title.split(" - ")
            title = title_parts[0]
            author = title_parts[1] if len(title_parts) > 1 else "Unknown"
            print(f"[{i}] Raw: '{raw_title}' -> Title: '{title}', Author: '{author}'")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
