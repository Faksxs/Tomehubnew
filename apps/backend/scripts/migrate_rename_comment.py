import os
import sys
import oracledb
from dotenv import load_dotenv

# Go up to backend dir
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from infrastructure.db_manager import DatabaseManager

def migrate():
    print("Starting migration: Rename personal_note to COMMENT...")
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Check if column exists
                try:
                    cursor.execute("SELECT personal_note FROM TOMEHUB_CONTENT FETCH FIRST 1 ROWS ONLY")
                    print("Column 'personal_note' found.")
                except oracledb.DatabaseError as e:
                    print("Column 'personal_note' not found (maybe already renamed?). Checking for 'COMMENT'...")
                    try:
                        cursor.execute('SELECT "COMMENT" FROM TOMEHUB_CONTENT FETCH FIRST 1 ROWS ONLY')
                        print("Column 'COMMENT' already exists. Skipping rename.")
                        return
                    except:
                        print("Neither 'personal_note' nor 'COMMENT' found or other error.")
                        raise e

                # Rename
                print("Renaming column...")
                cursor.execute('ALTER TABLE TOMEHUB_CONTENT RENAME COLUMN personal_note TO "COMMENT"')
                print("Column renamed successfully to \"COMMENT\".")
                
                # Check indexes or triggers? 
                # Assuming no indexes specifically on personal_note that rely on the name 
                # (Oracle usually handles rename for valid indexes, but text indexes might need rebuild).
                # Since it's a simple text column, `ALTER TABLE ... RENAME` is usually sufficient.
                
    except Exception as e:
        print(f"Migration failed: {e}")
        # Manual rollback not needed for DDL (auto-commit), but good to know.
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    # Load env
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    load_dotenv(dotenv_path=env_path)
    migrate()
