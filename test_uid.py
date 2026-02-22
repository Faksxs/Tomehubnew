import sys, os, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

from infrastructure.db_manager import DatabaseManager, safe_read_clob

def test():
    with io.open('test_uid_out.txt', 'w', encoding='utf-8') as f:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT id, title, firebase_uid, source_type
                    FROM TOMEHUB_CONTENT
                    WHERE dbms_lob.instr(lower(content_chunk), 'bilhassa') > 0
                """
                cursor.execute(sql)
                rows = cursor.fetchall()
                f.write(f"Found {len(rows)} matching rows overall.\n")
                
                for r in rows:
                    f.write(f"ID: {r[0]}, Title: {r[1]}, UID: {r[2]}, Source: {r[3]}\n")

if __name__ == "__main__":
    test()
