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
        
        print(f"{'COLUMN_NAME':<30} | {'DATA_TYPE'}")
        print("-" * 60)
        for name, data_type in rows:
            print(f"{name:<30} | {data_type}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    list_columns()
