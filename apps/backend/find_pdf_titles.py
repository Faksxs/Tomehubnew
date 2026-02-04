import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def find_pdf_titles():
    conn = DatabaseManager.get_read_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT DISTINCT title FROM TOMEHUB_CONTENT WHERE LOWER(title) LIKE '%.pdf%'"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            print("No titles found with '.pdf' in the database.")
        else:
            print("Titles found with '.pdf':")
            for row in rows:
                print(f"- {row[0]}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    find_pdf_titles()
