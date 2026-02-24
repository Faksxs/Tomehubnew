from infrastructure.db_manager import DatabaseManager
import sys
import io

# Set encoding to UTF-8 for printing
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def investigate_usage():
    try:
        conn = DatabaseManager.get_read_connection()
        cur = conn.cursor()
        
        print("Checking activity per day for the last 14 days...")
        
        # 1. TOMEHUB_LIBRARY_ITEMS counts per day
        print("\n--- TOMEHUB_LIBRARY_ITEMS activity (Last 14 Days) ---")
        cur.execute("""
            SELECT TO_CHAR(CREATED_AT, 'YYYY-MM-DD') as day, COUNT(*) 
            FROM TOMEHUB_LIBRARY_ITEMS 
            WHERE CREATED_AT >= TRUNC(SYSDATE) - 14
            GROUP BY TO_CHAR(CREATED_AT, 'YYYY-MM-DD')
            ORDER BY day DESC
        """)
        for r in cur.fetchall():
            print(f"Day: {r[0]}, Count: {r[1]}")

        # 2. TOMEHUB_CONTENT_V2 counts per day
        print("\n--- TOMEHUB_CONTENT_V2 activity (Last 14 Days) ---")
        cur.execute("""
            SELECT TO_CHAR(CREATED_AT, 'YYYY-MM-DD') as day, CONTENT_TYPE, COUNT(*) 
            FROM TOMEHUB_CONTENT_V2 
            WHERE CREATED_AT >= TRUNC(SYSDATE) - 14
            GROUP BY TO_CHAR(CREATED_AT, 'YYYY-MM-DD'), CONTENT_TYPE
            ORDER BY day DESC, CONTENT_TYPE
        """)
        for r in cur.fetchall():
            print(f"Day: {r[0]}, Type: {r[1]}, Count: {r[2]}")

        # 3. List recent titles regardless of date
        print("\n--- Top 20 Most Recent Library Items ---")
        cur.execute("""
            SELECT TITLE, CREATED_AT, FIREBASE_UID, ITEM_ID
            FROM TOMEHUB_LIBRARY_ITEMS 
            ORDER BY CREATED_AT DESC
            FETCH FIRST 20 ROWS ONLY
        """)
        for r in cur.fetchall():
            print(f"Title: {r[0]}, Created: {r[1]}, UID: {r[2]}, ID: {r[3]}")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    investigate_usage()
