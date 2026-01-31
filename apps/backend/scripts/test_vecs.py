import os
import oracledb
from dotenv import load_dotenv

# Mock settings for oracledb
class Settings:
    def __init__(self):
        load_dotenv()
        self.DB_USER = os.getenv("DB_USER")
        self.DB_PASSWORD = os.getenv("DB_PASSWORD")
        self.DB_DSN = os.getenv("DB_DSN")

settings = Settings()

def test_db():
    backend_dir = os.getcwd()
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    print(f"Connecting to {settings.DB_USER}@{settings.DB_DSN}...")
    print(f"Wallet location: {wallet_location}")
    
    conn = oracledb.connect(
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        dsn=settings.DB_DSN,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=settings.DB_PASSWORD
    )
    
    cursor = conn.cursor()
    
    # 1. Check total rows
    cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT")
    total = cursor.fetchone()[0]
    print(f"Total rows: {total}")
    
    # 2. Check vector count
    cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT WHERE VEC_EMBEDDING IS NOT NULL")
    vecs = cursor.fetchone()[0]
    print(f"Rows with VEC_EMBEDDING: {vecs}")
    
    # 3. Check sample UID
    cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT FETCH FIRST 5 ROWS ONLY")
    uids = cursor.fetchall()
    print(f"Sample UIDs: {[u[0] for u in uids]}")
    
    if uids:
        uid = uids[0][0]
        cursor.execute("SELECT id, title, VEC_EMBEDDING FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid AND VEC_EMBEDDING IS NOT NULL FETCH FIRST 1 ROW ONLY", {"uid": uid})
        row = cursor.fetchone()
        if row:
            print(f"Found item with vector: {row[1]} ({row[0]})")
            vec = row[2]
            print(f"Vector type: {type(vec)}")
            if hasattr(vec, 'read'):
                print("Vector is a LOB")
            elif isinstance(vec, list):
                print(f"Vector is a list, length: {len(vec)}")
            else:
                print(f"Vector is: {vec}")
    
    conn.close()

if __name__ == "__main__":
    try:
        test_db()
    except Exception as e:
        print(f"Error: {e}")
