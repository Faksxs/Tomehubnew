import sys
import os

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def check_book():
    uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        print("Searching for books by Terry Eagleton or 'Hayatin Anlami'...")
        
        # Case-insensitive search for flexibility
        sql = """
        SELECT DISTINCT title 
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :p_uid 
          AND (lower(title) LIKE '%eagleton%' OR lower(title) LIKE '%hayat%')
        """
        
        cursor.execute(sql, {'p_uid': uid})
        rows = cursor.fetchall()
        
        if rows:
            print(f"Found {len(rows)} matching books:")
            for r in rows:
                print(f" - {r[0]}")
        else:
            print("No books found matching criteria.")
            
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_book()
