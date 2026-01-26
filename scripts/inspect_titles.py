import sys
import os

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def inspect():
    uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        sql = "SELECT DISTINCT title FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid AND title LIKE '%Hayat%'"
        cursor.execute(sql, {'p_uid': uid})
        rows = cursor.fetchall()
        
        for row in rows:
            title = row[0]
            print(f"Title: {title}")
            print(f"Codes: {[ord(c) for c in title]}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect()
