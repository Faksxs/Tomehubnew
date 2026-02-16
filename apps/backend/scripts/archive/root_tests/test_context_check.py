
from services.analytics_service import count_lemma_occurrences, resolve_book_id_from_question, get_keyword_distribution, get_keyword_contexts
from infrastructure.db_manager import DatabaseManager

def test_comparison():
    DatabaseManager.init_pool()
    firebase_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    question = "Mahur Beste kitabında zaman kelimesi kaç defa geçiyor?"
    book_id = resolve_book_id_from_question(firebase_uid, question)
    
    print(f"Book ID: {book_id}")
    
    # 1. token_freq count
    count_tf = count_lemma_occurrences(firebase_uid, book_id, "zaman")
    
    # 2. Live scan count
    dist = get_keyword_distribution(firebase_uid, book_id, "zaman")
    count_live = sum(d['count'] for d in dist)
    
    # 3. Contexts
    contexts = get_keyword_contexts(firebase_uid, book_id, "zaman", limit=5)
    
    print(f"TokenFreq Count: {count_tf}")
    print(f"Live Scan Count: {count_live}")
    print(f"Contexts Found: {len(contexts)}")
    if contexts:
        print(f"Sample: {contexts[0]['snippet']}")

if __name__ == "__main__":
    test_comparison()
