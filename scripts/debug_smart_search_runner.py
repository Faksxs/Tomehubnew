
import sys
import os

# Add backend to path
# Add backend to path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_path = os.path.join(current_dir, '..', 'apps', 'backend')
sys.path.append(backend_path)

from services.smart_search_service import perform_smart_search
import logging

# Setup basic logging to see output
logging.basicConfig(level=logging.INFO)

def test_smart_search_logic():
    print("--- Testing perform_smart_search Logic ---")
    query = "küfür"
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    
    print(f"Query: {query}")
    print(f"UID: {uid}")
    
    try:
        results = perform_smart_search(query, uid)
        print(f"\nResults found: {len(results)}")
        
        for i, res in enumerate(results):
            print(f"{i+1}. {res['title']} (Score: {res['score']})")
            
        if len(results) == 0:
            print("❌ Search returned NO results.")
        else:
            print("✅ Search returned results.")
            
    except Exception as e:
        print(f"Error running search: {e}")

if __name__ == "__main__":
    test_smart_search_logic()
