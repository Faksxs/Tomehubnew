
import oracledb
import json
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))
load_dotenv(os.path.join(os.getcwd(), 'apps', 'backend', '.env'))

def get_db_connection():
    user = os.getenv("DB_USER", "TOMEHUB")
    password = os.getenv("DB_PASSWORD", "Tomehub123")
    dsn = os.getenv("DB_DSN", "localhost:1521/XEPDB1")
    return oracledb.connect(user=user, password=password, dsn=dsn)

def list_all_tomehub_columns():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'TOMEHUB_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    table_schemas = {}
    for table in tables:
        cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}'")
        table_schemas[table] = [row[0] for row in cursor.fetchall()]
        
    with open("tomehub_column_map.json", "w", encoding="utf-8") as f:
        json.dump(table_schemas, f, indent=2)
    
    print(f"Mapped {len(tables)} tables to tomehub_column_map.json")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    list_all_tomehub_columns()
