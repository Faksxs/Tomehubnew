import oracledb
import os
from dotenv import load_dotenv

load_dotenv()

def check_db():
    conn = oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dsn=os.getenv("DB_DSN")
    )
    cursor = conn.cursor()
    
    # Check total counts
    cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT")
    total = cursor.fetchone()[0]
    print(f"Total rows in TOMEHUB_CONTENT: {total}")
    
    # Check UIDs
    cursor.execute("SELECT firebase_uid, count(*) FROM TOMEHUB_CONTENT GROUP BY firebase_uid")
    rows = cursor.fetchall()
    print("UIDs in database:")
    for row in rows:
        print(f"  {row[0]}: {row[1]} rows")
        
    # Check vectors
    cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT WHERE VEC_EMBEDDING IS NOT NULL")
    vec_count = cursor.fetchone()[0]
    print(f"Rows with VEC_EMBEDDING: {vec_count}")
    
    conn.close()

if __name__ == "__main__":
    check_db()
