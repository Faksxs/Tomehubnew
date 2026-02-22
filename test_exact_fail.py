import sys, os, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.search_system.strategies import ExactMatchStrategy, _contains_exact_term_boundary, _normalize_match_text

def test():
    with io.open('test_exact_fail_out.txt', 'w', encoding='utf-8') as f:
        uid = None
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT firebase_uid FROM TOMEHUB_CONTENT WHERE title LIKE '%Sosyoloji%' FETCH FIRST 1 ROWS ONLY")
                row = cursor.fetchone()
                if row:
                    uid = row[0]
                    f.write(f"Found UID: {uid}\n")
                else:
                    f.write("UID not found\n")
                    return
                # Find all records with bilhassa in content_chunk
                sql = """
                    SELECT id, title, content_chunk, normalized_content, text_deaccented
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND (LOWER(content_chunk) LIKE '%bilhassa%' OR LOWER(normalized_content) LIKE '%bilhassa%')
                """
                cursor.execute(sql, {"p_uid": uid})
                rows = cursor.fetchall()
                f.write(f"Found {len(rows)} rows with 'bilhassa' in content_chunk or normalized_content.\n")
                
                for r in rows:
                    content = safe_read_clob(r[2])
                    norm_content = safe_read_clob(r[3])
                    deaccented = safe_read_clob(r[4])
                    
                    haystack = norm_content or content
                    match = _contains_exact_term_boundary(haystack, "bilhassa")
                    
                    # Also check if it's in text_deaccented
                    in_deaccented = "bilhassa" in (deaccented or "").lower()
                    
                    f.write(f"\nID: {r[0]} | Title: {r[1]}\n")
                    f.write(f"  Regex Match: {match}\n")
                    f.write(f"  In text_deaccented column: {in_deaccented}\n")
                    
                    if not match:
                        f.write(f"  Haystack (normalized): {_normalize_match_text(haystack)[:100]}\n")
                    if not in_deaccented:
                        f.write(f"  Deaccented string start: {(deaccented or '')[:100]}\n")

if __name__ == "__main__":
    test()
