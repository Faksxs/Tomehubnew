
import os
import sys
import oracledb

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.db_manager import DatabaseManager
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

def apply_schema():
    print("=== Applying Memory Layer Schema ===")
    
    DatabaseManager.init_pool()
    
    # Read SQL file
    sql_path = os.path.join(os.path.dirname(__file__), '..', 'create_memory_schema.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    statements = [s.strip() for s in sql_content.split(';') if s.strip()]

    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            for params in statements:
                try:
                    print(f"Executing: {params[:50]}...")
                    cursor.execute(params)
                    print("[OK]")
                except oracledb.DatabaseError as e:
                    error, = e.args
                    if error.code == 955: # ORA-00955: name already used
                        print("[SKIP] Table/Index already exists.")
                    else:
                        print(f"[ERROR] {e}")

    print("=== Migration Complete ===")

if __name__ == "__main__":
    apply_schema()
