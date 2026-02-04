
import os
import sys

# Add apps/backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager
from utils.text_utils import deaccent_text

def check_content():
    term = "zaman"
    print(f"Checking for term '{term}' in HIGHLIGHT/ARTICLE/PERSONAL_NOTE...")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Same logic as ExactMatch without the strat wrapper
                sql = """
                    SELECT id, source_type, DBMS_LOB.SUBSTR(content_chunk, 100, 1) as snippet
                    FROM TOMEHUB_CONTENT
                    WHERE source_type IN ('HIGHLIGHT', 'ARTICLE', 'PERSONAL_NOTE')
                    AND (
                        text_deaccented LIKE '%' || :p_term || '%'
                        OR LOWER(content_chunk) LIKE '%' || :p_term_lower || '%'
                    )
                    FETCH FIRST 10 ROWS ONLY
                """
                params = {
                    "p_term": deaccent_text(term),
                    "p_term_lower": term.lower()
                }
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                
                print(f"Found {len(rows)} matches in valid types.")
                for r in rows:
                    print(f"[{r[1]}] ID: {r[0]} | Snippet: {r[2]}")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_content()
