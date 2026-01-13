
import os
import sys
import json
import oracledb
from dotenv import load_dotenv

# Path setup to import from utils
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir) 

from utils.text_utils import deaccent_text, get_lemmas

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

def backfill_metadata():
    print("--- Starting Backfill for Smart Search Metadata ---")
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # Select rows requiring update
        # We process rows where new columns are NULL
        print("Fetching rows to process...")
        sql_fetch = """
            SELECT id, content_chunk 
            FROM TOMEHUB_CONTENT 
            WHERE text_deaccented IS NULL OR lemma_tokens IS NULL
        """
        cursor.execute(sql_fetch)
        rows = cursor.fetchall()
        total = len(rows)
        print(f"Found {total} rows to process.")
        
        count = 0
        batch_data = []
        
        for row in rows:
            rid, content_clob = row
            content = content_clob.read() if content_clob else ""
            
            # 1. De-accent
            deaccented = deaccent_text(content)
            
            # 2. Lemmas
            lemma_list = get_lemmas(content)
            lemmas_json = json.dumps(lemma_list, ensure_ascii=False)
            
            batch_data.append((deaccented, lemmas_json, rid))
            count += 1
            
            # Batch Update
            if len(batch_data) >= 50:
                print(f"Updating batch... ({count}/{total})")
                sql_update = """
                    UPDATE TOMEHUB_CONTENT 
                    SET text_deaccented = :1, lemma_tokens = :2 
                    WHERE id = :3
                """
                cursor.executemany(sql_update, batch_data)
                conn.commit()
                batch_data = []

        # Final batch
        if batch_data:
            print(f"Updating final batch... ({count}/{total})")
            sql_update = """
                UPDATE TOMEHUB_CONTENT 
                SET text_deaccented = :1, lemma_tokens = :2 
                WHERE id = :3
            """
            cursor.executemany(sql_update, batch_data)
            conn.commit()
            
        print("✅ Backfill complete.")
        
    except Exception as e:
        print(f"Error during backfill: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    backfill_metadata()
