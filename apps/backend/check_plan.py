import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()
try:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            # 1. Check total rows in new vs old content tables
            cur.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
            old_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT_V2")
            new_count = cur.fetchone()[0]
            
            print(f"Old TOMEHUB_CONTENT Row Count: {old_count}")
            print(f"New TOMEHUB_CONTENT_V2 Row Count: {new_count}")
            
            # 2. Check EXPLAIN PLAN for a common RAG query
            explain_sql = """
            EXPLAIN PLAN FOR
            SELECT id, title, content_type 
            FROM TOMEHUB_CONTENT_V2 
            WHERE FIREBASE_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63' 
              AND AI_ELIGIBLE = 1
            """
            cur.execute(explain_sql)
            cur.execute("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(format=>'BASIC'))")
            plan = cur.fetchall()
            print("\\nEXPLAIN PLAN Output:")
            for row in plan:
                print(row[0])
finally:
    DatabaseManager.close_pool()
