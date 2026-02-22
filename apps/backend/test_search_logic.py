
import sys
import os
from functools import partial

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.search_service import generate_answer
from infrastructure.db_manager import DatabaseManager

def test_search():
    # Initialize DB pool
    DatabaseManager.init_pool()
    
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63" # The "bad" UID that has data
    question = "islam felsefesi"
    
    print(f"Testing search for UID: {uid}")
    print(f"Question: {question}")
    
    try:
        # Call generate_answer (this is what the API calls)
        answer, sources, metadata = generate_answer(
            question=question,
            firebase_uid=uid,
            context_book_id=None,
            chat_history=None,
            session_summary="",
            limit=5,
            offset=0
        )
        
        print("\n--- ANSWER ---")
        print(answer)
        print("\n--- SOURCES ---")
        for s in sources:
            print(f"[{s.get('similarity_score', 0):.4f}] {s.get('title')} - Page {s.get('page_number')}")
            
    except Exception as e:
        print(f"Error during search: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    test_search()
