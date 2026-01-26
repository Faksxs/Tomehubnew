import sys
import os

sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))
from services.ingestion_service import get_database_connection

def check_source_types():
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        query = """
        SELECT DISTINCT source_type, COUNT(*) as cnt
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :p_uid
        GROUP BY source_type
        """
        cursor.execute(query, {"p_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"})
        rows = cursor.fetchall()
        
        print("Source types in database:")
        for row in rows:
            print(f"  {row[0]}: {row[1]} entries")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_source_types()
