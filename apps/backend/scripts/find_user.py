
import os
import sys
import oracledb
from dotenv import load_dotenv

# Setup paths
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
env_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path=env_path)

def find_users():
    try:
        user = os.getenv("DB_USER", "ADMIN")
        password = os.getenv("DB_PASSWORD")
        dsn = os.getenv("DB_DSN")
        wallet_location = os.path.join(backend_dir, 'wallet')
        
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet_location,
            wallet_location=wallet_location,
            wallet_password=password
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT firebase_uid, COUNT(*) FROM TOMEHUB_CONTENT GROUP BY firebase_uid")
        rows = cursor.fetchall()
        
        print("\n--- Found Users ---")
        for r in rows:
            print(f"UID: {r[0]} | Note Count: {r[1]}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_users()
