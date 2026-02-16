
import os
import sys
import logging

# Configure logging to see errors
logging.basicConfig(level=logging.INFO)

# Add apps/backend to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from services.search_system._deprecated.strategies_final import ExactMatchStrategy
from services.search_system.orchestrator import SearchOrchestrator

import traceback

def debug_search():
    query = "zaman"
    # Use a known UID from previous debug output
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63" 
    
    print(f"--- Debugging Search for '{query}' ---")
    
    # 1. Test ExactMatchStrategy Direct
    print("\n1. Testing ExactMatchStrategy individually...")
    try:
        print("DEBUG: Init strategy")
        strat = ExactMatchStrategy()
        print("DEBUG: Calling search")
        results = strat.search(query, uid, limit=10)
        print("DEBUG: Search returned")
        print(f"ExactMatchStrategy returned {len(results)} results.")
        if len(results) > 0:
            print(f"Sample: {results[0]['id']} - {results[0]['source_type']}")
    except Exception as e:
        print(f"ExactMatchStrategy FAILED: {e}")
        with open('debug_error.log', 'w') as f:
            traceback.print_exc(file=f)

    # 2. Test Orchestrator
    print("\n2. Testing Orchestrator...")
    try:
        orch = SearchOrchestrator()
        results, meta = orch.search(query, uid, limit=20, intent='DIRECT')
        print(f"Orchestrator returned {len(results)} results.")
        print(f"Metadata: {meta}")
        if len(results) > 0:
            print(f"Top Result: {results[0]['id']} - {results[0].get('match_type')} - {results[0].get('source_type')}")
    except Exception as e:
        print(f"Orchestrator FAILED: {e}")

if __name__ == "__main__":
    debug_search()
