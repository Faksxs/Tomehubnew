import io
import os
import re
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

def normalize_bilingual_titles():
    """
    Normalize concept names like "Düşüş (The Fall)" into:
      NAME = "Düşüş"
      ALIAS = "The Fall"
    """
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name
                    FROM TOMEHUB_CONCEPTS
                    WHERE REGEXP_LIKE(name, '\\\\(.+\\\\)')
                """)
                rows = cursor.fetchall()

                for cid, name in rows:
                    m = re.match(r"^(.+?)\\s*\\((.+)\\)\\s*$", name)
                    if not m:
                        continue
                    primary = m.group(1).strip()
                    alias = m.group(2).strip()

                    if primary:
                        cursor.execute("""
                            UPDATE TOMEHUB_CONCEPTS
                            SET name = :p_name
                            WHERE id = :p_id
                        """, {"p_name": primary[:255], "p_id": cid})

                    if alias:
                        try:
                            cursor.execute("""
                                INSERT INTO TOMEHUB_CONCEPT_ALIASES (concept_id, alias)
                                VALUES (:p_cid, :p_alias)
                            """, {"p_cid": cid, "p_alias": alias[:255]})
                        except Exception:
                            pass

            conn.commit()
        print("NORMALIZATION_DONE")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    normalize_bilingual_titles()
