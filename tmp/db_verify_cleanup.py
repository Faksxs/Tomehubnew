from infrastructure.db_manager import DatabaseManager

def verify():
    try:
        conn = DatabaseManager.get_read_connection()
        cur = conn.cursor()
        cur.execute("SELECT CONTENT_TYPE, COUNT(*) FROM TOMEHUB_CONTENT_V2 GROUP BY CONTENT_TYPE ORDER BY 2 DESC")
        print("\n--- TOMEHUB_CONTENT_V2 Content Types ---")
        for r in cur.fetchall():
            print(f"{r[0]}: {r[1]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Verification failed: {e}")

if __name__ == '__main__':
    verify()
