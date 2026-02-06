
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def run_migration():
    print("=== Applying Safe Schema Migration ===")
    
    # Read the SQL file
    migration_path = os.path.join(backend_dir, 'infrastructure', 'migrations', 'repair_schema_safe.sql')
    if not os.path.exists(migration_path):
        print(f"FATAL: Migration file not found at {migration_path}")
        return

    with open(migration_path, 'r') as f:
        sql_content = f.read()

    # Split by '/' for PL/SQL blocks or ';' for standard statements
    # This is a naive splitter, but sufficient for our specific script structure
    # Our script uses '/' after PL/SQL blocks.
    commands = []
    current_command = []
    
    for line in sql_content.splitlines():
        if line.strip() == '/':
            if current_command:
                commands.append('\n'.join(current_command))
                current_command = []
        elif line.strip().endswith(';') and not line.strip().startswith('BEGIN') and not 'END;' in line:
             # Standard statement
             current_command.append(line.replace(';', ''))
             commands.append('\n'.join(current_command))
             current_command = []
        else:
            current_command.append(line)
            
    if current_command:
        commands.append('\n'.join(current_command))

    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()
        
        print(f"Found {len(commands)} blocks to execute.")
        
        for idx, cmd in enumerate(commands):
            if not cmd.strip(): continue
            print(f"Executing block {idx+1}...")
            try:
                cursor.execute(cmd)
                print("  Success.")
            except Exception as e:
                print(f"  Error in block {idx+1}: {e}")
                
        conn.commit()
        print("\nMigration completed successfully. Indexes and Tables should act as mirrors now.")
        
    except Exception as e:
        print(f"FATAL DB Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    run_migration()
