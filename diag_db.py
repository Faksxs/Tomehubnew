import os
import sys
import oracledb
from dotenv import load_dotenv

def diagnostic():
    load_dotenv('apps/backend/.env')
    
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    dsn = os.getenv('DB_DSN')
    wallet = 'apps/backend/wallet'
    
    print(f"Connecting to {dsn} as {user}...")
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
        
        with conn.cursor() as cursor:
            # Check table columns
            cursor.execute("SELECT column_name FROM user_tab_cols WHERE table_name = 'TOMEHUB_CONTENT'")
            cols = [r[0] for r in cursor.fetchall()]
            print(f"Columns in TOMEHUB_CONTENT: {cols}")
            
            # Check UIDs
            cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT")
            uids = [r[0] for r in cursor.fetchall()]
            print(f"UIDs found in DB: {uids}")
            
            # Check rows for specific UIDs
            for uid in uids:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :u", {"u": uid})
                count = cursor.fetchone()[0]
                print(f"UID {uid}: {count} rows")
                
                # Check if columns are empty
                if 'TEXT_DEACCENTED' in cols:
                    cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :u AND text_deaccented IS NOT NULL", {"u": uid})
                    da_count = cursor.fetchone()[0]
                    print(f"  - text_deaccented populated: {da_count}")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnostic()
