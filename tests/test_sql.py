import os
import sys
import oracledb
from dotenv import load_dotenv

def test_sql():
    load_dotenv('apps/backend/.env')
    
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    dsn = os.getenv('DB_DSN')
    wallet = 'apps/backend/wallet'
    
    print(f"Connecting to {dsn}...")
    try:
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet,
            wallet_location=wallet,
            wallet_password=password
        )
        print("Connected!")
        
        firebase_uid = "aksoyfeth@gmail.com"
        term = "nedensellik"
        
        with conn.cursor() as cursor:
            # First, check if UID exists at all
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :u", {"u": firebase_uid})
            count = cursor.fetchone()[0]
            print(f"\nUID {firebase_uid} total rows: {count}")
            
            if count > 0:
                # Check for the term
                sql = """
                    SELECT title, content_chunk 
                    FROM TOMEHUB_CONTENT 
                    WHERE firebase_uid = :u 
                    AND (
                        LOWER(content_chunk) LIKE '%' || :t || '%'
                    )
                """
                cursor.execute(sql, {"u": firebase_uid, "t": term.lower()})
                rows = cursor.fetchall()
                print(f"Term '{term}' matches: {len(rows)}")
                for r in rows[:3]:
                    print(f"  - {r[0]}: {str(r[1])[:50]}...")
            
            # Check for OTHER UIDs just in case
            cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT")
            all_uids = [r[0] for r in cursor.fetchall()]
            print(f"\nAll UIDs in DB: {all_uids}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_sql()
