
import os
import sys
import oracledb
from dotenv import load_dotenv

# Adjust path to find .env
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
env_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path=env_path)

def get_database_connection():
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    return oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=password
    )

def add_columns():
    print("--- Migrating Schema for Smart Search ---")
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # 1. Add text_deaccented
        try:
            print("Attempting to add 'text_deaccented' (CLOB)...")
            cursor.execute("ALTER TABLE TOMEHUB_CONTENT ADD (text_deaccented CLOB)")
            print("✅ 'text_deaccented' column added successfully.")
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            if error_obj.code == 1430: # Column exists
                print("ℹ️ 'text_deaccented' already exists. Skipping.")
            else:
                print(f"❌ Failed to add 'text_deaccented': {e}")

        # 2. Add lemma_tokens
        try:
            print("Attempting to add 'lemma_tokens' (CLOB with JSON check)...")
            cursor.execute("ALTER TABLE TOMEHUB_CONTENT ADD (lemma_tokens CLOB CHECK (lemma_tokens IS JSON))")
            print("✅ 'lemma_tokens' column added successfully.")
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            if error_obj.code == 1430: # Column exists
                print("ℹ️ 'lemma_tokens' already exists. Skipping.")
            else:
                print(f"❌ Failed to add 'lemma_tokens': {e}")

        conn.close()
        print("\nMigration complete.")
        
    except Exception as e:
        print(f"\n[FATAL] Migration failed: {e}")

if __name__ == "__main__":
    add_columns()
