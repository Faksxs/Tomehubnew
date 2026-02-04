import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

def list_constraints():
    conn = DatabaseManager.get_read_connection()
    cursor = conn.cursor()
    
    try:
        query = "SELECT constraint_name, search_condition FROM user_constraints WHERE table_name = 'TOMEHUB_CONTENT' AND constraint_type = 'C'"
        cursor.execute(query)
        rows = cursor.fetchall()
        
        print(f"{'CONSTRAINT_NAME':<30} | {'SEARCH_CONDITION'}")
        print("-" * 100)
        for name, condition in rows:
            print(f"{name:<30} | {condition}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    list_constraints()
