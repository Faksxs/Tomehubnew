
import sys
import os
import oracledb

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.getcwd(), 'apps', 'backend', '.env'))

from infrastructure.db_manager import DatabaseManager

def apply_migration(file_path):
    print(f"Applying migration: {file_path}")
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False
        
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Split by semicolon, but handle cases where it might be tricky
        import re
        statements = re.split(r';\s*(?:\n|$)', content)
        
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                for stmt in statements:
                    stmt = stmt.strip()
                    if not stmt or stmt.upper() == 'COMMIT':
                        continue
                    
                    print(f"Executing: {stmt[:50]}...")
                    try:
                        cursor.execute(stmt)
                        print("✓ Success")
                    except oracledb.DatabaseError as de:
                        # Ignore "Name is already used" errors (ORA-00955)
                        error_obj, = de.args
                        if error_obj.code == 955:
                            print("ℹ Index already exists, skipping...")
                        else:
                            print(f"❌ Error: {de}")
                
                conn.commit()
                print("Migration committed.")
        return True
    except Exception as e:
        print(f"Fatal error: {e}")
        return False

if __name__ == "__main__":
    DatabaseManager.init_pool()
    apply_migration(os.path.join(os.getcwd(), 'apps', 'backend', 'migrations', 'phaseB_optimizations.sql'))
    DatabaseManager.close_pool()
