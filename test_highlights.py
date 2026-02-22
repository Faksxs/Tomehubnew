import sys, os, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

from infrastructure.db_manager import DatabaseManager, safe_read_clob

def test():
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            # Let's find exactly the texts from the screenshot in the DB
            queries = [
                "%kıt kaynaklara (bilhassa iktisadi%",
                "%tamamı, bilhassa kasabalarda%",
                "%Fransa ve bilhassa İngilteredeki%",
                "%gelişiminde bilhassa önemli%",
                "%sürüklemez, bilhassa onu derhal%",
                "%kişi bilhassa özfarkındalık%",
                "%dolduracağının farkındaydı; bilhassa%"
            ]
            
            with io.open("test_highlights_out.txt", "w", encoding="utf-8") as f:
                for q in queries:
                    sql = """
                        SELECT id, title, source_type, is_highlight
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid AND LOWER(content_chunk) LIKE :p_q
                    """
                    try:
                        cursor.execute(sql, {"p_uid": uid, "p_q": q})
                        rows = cursor.fetchall()
                        f.write(f"\nQuery: {q[:30]}...\n")
                        if not rows:
                            f.write("  -> NOT FOUND\n")
                        for r in rows:
                            f.write(f"  -> ID: {r[0]}, Title: {r[1]}, Source_Type: {r[2]}, is_highlight: {r[3]}\n")
                    except Exception as e:
                        # If is_highlight doesn't exist, try without it
                        sql = """
                            SELECT id, title, source_type
                            FROM TOMEHUB_CONTENT
                            WHERE firebase_uid = :p_uid AND LOWER(content_chunk) LIKE :p_q
                        """
                        cursor.execute(sql, {"p_uid": uid, "p_q": q})
                        rows = cursor.fetchall()
                        f.write(f"\nQuery: {q[:30]}... (without is_highlight)\n")
                        if not rows:
                            f.write("  -> NOT FOUND\n")
                        for r in rows:
                            f.write(f"  -> ID: {r[0]}, Title: {r[1]}, Source_Type: {r[2]}\n")

if __name__ == "__main__":
    test()
