import os
import sys
import json
from dotenv import load_dotenv

# Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# Add backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import DatabaseManager
from services.smart_search_service import perform_smart_search

def run_test():
    print("--- SEARCH ARCHITECTURE VERIFICATION ---")
    
    # 0. Init Pool
    print("Initializing Database Pool...")
    DatabaseManager.init_pool()
    
    # 1. Get a valid user
    conn = DatabaseManager.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT firebase_uid FROM TOMEHUB_CONTENT FETCH FIRST 1 ROWS ONLY")
        row = cursor.fetchone()
        if not row:
            print("No data in DB.")
            return
        uid = row[0]
        print(f"Testing with UID: {uid}")
    finally:
        cursor.close()
        conn.close()

    # 2. Run Search
    query = "ahlak" # Generic term likely to be in DB
    print(f"Searching for: '{query}'")
    
    results = perform_smart_search(query, uid)
    
    print(f"\nResults Found: {len(results)}")
    for i, res in enumerate(results[:3]):
        print(f"\nResult #{i+1}:")
        print(f"Title: {res.get('title')}")
        print(f"Type: {res.get('match_type')}")
        print(f"Score: {res.get('score')}")
        print(f"Snippet: {res.get('content_chunk', '')[:100]}...")
        if 'debug_info' in res:
             print(f"Debug: {res['debug_info']}")

if __name__ == "__main__":
    run_test()
