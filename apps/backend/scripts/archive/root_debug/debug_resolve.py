
from services.analytics_service import resolve_book_id_from_question, extract_book_phrase
from infrastructure.db_manager import DatabaseManager
import sys

def debug_resolve():
    uid = "vpq1p0UzcCSLAhId18WgZ2wPBE63"
    question = "mahur beste kitabinda @zaman kelimesi kac defa gecmektedir"
    
    print(f"UID: {uid}")
    print(f"Question: {question}")
    sys.stdout.flush()
    
    # 1. Test extraction
    try:
        phrase = extract_book_phrase(question)
        print(f"Extracted phrase: '{phrase}'")
    except Exception as e:
        print(f"Extraction failed: {e}")
    sys.stdout.flush()
    
    # 2. Test resolution
    try:
        print("Calling resolve_book_id_from_question...")
        book_id = resolve_book_id_from_question(uid, question)
        print(f"Resolved Book ID: {book_id}")
    except Exception as e:
        print(f"Resolution error: {e}")
    sys.stdout.flush()
        
    # 3. Check DB content manually
    print("\n--- DB Check ---")
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                print("Executing manual query...")
                cursor.execute(
                    "SELECT DISTINCT title, book_id, source_type FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid AND source_type = 'PDF_CHUNK'",
                    {"uid": uid}
                )
                rows = cursor.fetchall()
                print(f"Found {len(rows)} distinct books/chunks for this UID:")
                seen = set()
                for title, bid, st in rows:
                    if bid not in seen:
                        print(f"  Title: '{title}' | ID: {bid} | Type: {st}")
                        seen.add(bid)
                        
    except Exception as e:
        print(f"DB Error: {e}")
    sys.stdout.flush()

if __name__ == "__main__":
    debug_resolve()
