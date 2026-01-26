import sys
import os

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def check():
    uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        query = "SELECT DISTINCT title FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid"
        cursor.execute(query, {"p_uid": uid})
        rows = cursor.fetchall()
        
        empty_titles = 0
        unknown_authors = 0
        total = len(rows)
        
        for row in rows:
            raw_title = row[0]
            if not raw_title or not raw_title.strip():
                empty_titles += 1
                continue
            
            parts = raw_title.split(" - ")
            title = parts[0].strip()
            author = parts[1].strip() if len(parts) > 1 else ""
            
            if not title: empty_titles += 1
            if not author or author.lower() == "unknown": unknown_authors += 1
            
        print(f"Total Unique Titles: {total}")
        print(f"Empty/Missing Titles: {empty_titles}")
        print(f"Unknown/Missing Authors: {unknown_authors}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check()
