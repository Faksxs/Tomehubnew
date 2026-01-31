import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Check how many content items exist for the user
            sql = """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN source_type IN ('PDF', 'EPUB', 'PDF_CHUNK') THEN 1 ELSE 0 END) as pdfs,
                       SUM(CASE WHEN source_type = 'ARTICLE' THEN 1 ELSE 0 END) as articles,
                       SUM(CASE WHEN source_type = 'WEBSITE' THEN 1 ELSE 0 END) as websites,
                       SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END) as with_embeddings
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = (SELECT firebase_uid FROM TOMEHUB_CONTENT WHERE ROWNUM = 1)
            """
            cursor.execute(sql)
            row = cursor.fetchone()
            print(f"Total content: {row[0]}")
            print(f"PDFs: {row[1]}")
            print(f"Articles: {row[2]}")
            print(f"Websites: {row[3]}")
            print(f"With embeddings: {row[4]}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
