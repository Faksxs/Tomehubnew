import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def list_columns():
    conn = DatabaseManager.get_read_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT column_name, data_type FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT' ORDER BY column_id"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        with open("content_columns_utf8.txt", "w", encoding="utf-8") as f:
            f.write(f"{'COLUMN_NAME':<30} | {'DATA_TYPE'}\n")
            f.write("-" * 60 + "\n")
            for name, data_type in rows:
                f.write(f"{name:<30} | {data_type}\n")
        print("Columns written to content_columns_utf8.txt")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    list_columns()
