
import os
import oracledb
from dotenv import load_dotenv
from utils.text_utils import normalize_text

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

def get_database_connection():
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    wallet_location = os.path.join(backend_dir, 'wallet')
    return oracledb.connect(
        user=user, password=password, dsn=dsn,
        config_dir=wallet_location, wallet_location=wallet_location, wallet_password=password
    )

def count_matches_for_uid(uid, query):
    print(f"--- Counting matches for '{query}' (UID: {uid}) ---")
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        norm_query = normalize_text(query)
        sql = """
            SELECT count(*)
            FROM TOMEHUB_CONTENT
            WHERE firebase_uid = :bv_uid
            AND (
                source_type NOT IN ('PDF', 'BOOK', 'EPUB')
                OR normalized_content LIKE '%arsiv notu%'
                OR normalized_content LIKE '%tags:%'
                OR normalized_content LIKE '%highlight from%'
            )
            AND normalized_content LIKE '%' || :bv_norm_query || '%'
        """
        cursor.execute(sql, {"bv_uid": uid, "bv_norm_query": norm_query})
        count = cursor.fetchone()[0]
        print(f"Total matches found in DB: {count}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    count_matches_for_uid("vpq1p0UzcCSLAh1d18WgZZWPBE63", "küfür")
