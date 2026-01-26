import sys
import os

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def inspect_columns():
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # Oracle specific query to list columns
        query = """
        SELECT column_name 
        FROM user_tab_columns 
        WHERE table_name = 'TOMEHUB_CONTENT'
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print("Columns in TOMEHUB_CONTENT:")
        for row in rows:
            print(f" - {row[0]}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_columns()
