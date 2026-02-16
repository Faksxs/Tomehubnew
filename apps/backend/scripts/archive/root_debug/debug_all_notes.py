
from infrastructure.db_manager import DatabaseManager
from utils.text_utils import normalize_text, normalize_canonical

def debug_all_notes(uid, term):
    print(f"--- Debugging 'All Notes' (BROAD SEARCH) for Term: {term} ---")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Search for the term in HIGHLIGHT regardless of UID
                sql = """
                    SELECT firebase_uid, source_type, content_chunk, normalized_content
                    FROM TOMEHUB_CONTENT
                    WHERE source_type = 'HIGHLIGHT'
                """
                cursor.execute(sql)
                rows = cursor.fetchall()
                print(f"\nTotal HIGHLIGHTS in DB: {len(rows)}")
                
                hits = 0
                for r_uid, st, raw, norm in rows:
                    if term.lower() in str(raw).lower() or term.lower() in str(norm).lower():
                        hits += 1
                        print(f"  Hit {hits}: [UID: {r_uid}] [Type: {st}]")
                
                print(f"\nTotal hits found in DB for 'zaman': {hits}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Get UID from logs if possible, or use the one from screenshot if visible
    # Screenshot shows UID: vpq1p0UzcCSLAhId18WgZ2wPBE63
    debug_all_notes("vpq1p0UzcCSLAhId18WgZ2wPBE63", "zaman")
