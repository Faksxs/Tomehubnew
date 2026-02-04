
from services.analytics_service import resolve_book_id_from_question
import sys

def debug_simple():
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    question = "mahur beste kitabinda @zaman kelimesi kac defa gecmektedir"
    
    print("Starting resolution check...")
    sys.stdout.flush()
    
    try:
        book_id = resolve_book_id_from_question(uid, question)
        print(f"RESULT: {book_id}")
    except Exception as e:
        print(f"CRASH: {e}")
    sys.stdout.flush()

if __name__ == "__main__":
    debug_simple()
