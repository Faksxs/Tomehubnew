import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def list_file_reports():
    conn = DatabaseManager.get_read_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT title, file_name, status FROM TOMEHUB_FILE_REPORTS"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'TITLE':<40} | {'FILE_NAME':<40} | {'STATUS'}")
        print("-" * 100)
        for title, file_name, status in rows:
            print(f"{str(title):<40} | {str(file_name):<40} | {status}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    list_file_reports()
