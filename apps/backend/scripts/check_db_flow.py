import oracledb
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_pool():
    user = os.getenv("DB_USER")
    pwd = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    
    # Try thin mode first
    return oracledb.create_pool(user=user, password=pwd, dsn=dsn, min=1, max=5, increment=1)

def check_schema():
    pool = get_db_pool()
    with pool.acquire() as conn:
        with conn.cursor() as cursor:
            print("--- TOMEHUB_CONTENT Columns ---")
            cursor.execute("SELECT * FROM TOMEHUB_CONTENT FETCH FIRST 1 ROW ONLY")
            for desc in cursor.description:
                print(f"Column: {desc[0]} (Type: {desc[1]})")
            
            print("\n--- Sample Record Count ---")
            cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT")
            print(f"Total Rows: {cursor.fetchone()[0]}")
            
            print("\n--- UIDs in table ---")
            cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT")
            uids = cursor.fetchall()
            for uid in uids:
                print(f"UID: {uid[0]}")
            
            if uids:
                sample_uid = uids[0][0]
                cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid and VEC_EMBEDDING IS NOT NULL", {"uid": sample_uid})
                print(f"Rows with vectors for UID {sample_uid}: {cursor.fetchone()[0]}")

if __name__ == "__main__":
    try:
        check_schema()
    except Exception as e:
        print(f"Error: {e}")
