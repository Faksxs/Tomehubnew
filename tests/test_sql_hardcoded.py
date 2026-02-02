import oracledb
import os

def test():
    # Credentials from .env
    user = "ADMIN"
    password = "Aksoy.19671967"
    dsn = "tomehubdb_high"
    wallet = r"c:\Users\aksoy\Desktop\yeni tomehub\apps\backend\wallet"
    
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
            # Check for ANY data
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
            total = cursor.fetchone()[0]
            print(f"Total rows in TOMEHUB_CONTENT: {total}")
            
            # Check UIDs
            cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT")
            uids = [r[0] for r in cursor.fetchall()]
            print(f"UIDs found: {uids}")
            
            for uid in uids:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :u", {"u": uid})
                print(f"  - UID {uid}: {cursor.fetchone()[0]} rows")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
