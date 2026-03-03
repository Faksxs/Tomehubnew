
import sys
import os
import json

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add apps/backend if needed
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def list_all_tomehub_columns():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'TOMEHUB_%'")
                tables = [row[0] for row in cursor.fetchall()]
                
                table_schemas = {}
                for table in tables:
                    cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}'")
                    table_schemas[table] = [row[0] for row in cursor.fetchall()]
                    
                with open("tomehub_column_map.json", "w", encoding="utf-8") as f:
                    json.dump(table_schemas, f, indent=2)
                
                print(f"Mapped {len(tables)} tables to tomehub_column_map.json")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    list_all_tomehub_columns()
