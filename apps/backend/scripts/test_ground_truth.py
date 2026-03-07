
__test__ = False

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from services.search_service import generate_answer

def test_ground_truth():
    print("\n[TEST] Starting Ground Truth Regression Suite...")
    
    # Load Golden Set
    with open(backend_dir / 'data' / 'golden_test_set.json', 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
        
    passed = 0
    total = 0
    
    for case_id, specs in test_cases.items():
        total += 1
        query = specs['query']
        print(f"\n--- Running Case: {case_id} ---")
        print(f"Query: {query}")
        
        start_time = time.time()
        try:
            # Assume user_id is fixed for testing or pull from env
            # Using a generic user_id if needed, or None if service handles it
            # search_service.generate_answer(questions, user_id)
            # We need a valid user_id.
            # Using the UID found via find_user.py
            user_id = "vpq1p0UzcCSLAh1d18WgZZWPBE63" 
            
            response = generate_answer(query, user_id)
            if isinstance(response, tuple) and len(response) == 3:
                answer, sources, _meta = response
            elif isinstance(response, tuple) and len(response) == 2:
                answer, sources = response
            else:
                raise RuntimeError("Unexpected generate_answer response payload")
            duration = time.time() - start_time
            
            print(f"Response Time: {duration:.2f}s")
            
            # 1. Check Mode
            actual_mode = "SYNTHESIS" # Default
            if "## Karşıt Görüşler" in answer or "## Karşıt Görüşler" in answer:
                actual_mode = "HYBRID"
            elif "## Doğrudan Tanımlar" in answer:
                actual_mode = "QUOTE"
            
            # Debug header check (if present in logs but not answer, we rely on content)
            
            expected_mode = specs.get('expected_mode')
            if expected_mode and expected_mode != actual_mode:
                print(f"❌ MODE FAILURE: Expected {expected_mode}, got {actual_mode}")
                # Print snippet for debug
                print(f"Answer Snippet: {answer[:300]}...")
                continue
            else:
                print(f"✅ Mode Verified: {actual_mode}")

            # 2. Check Must Quote
            quote_fail = False
            for phrase in specs.get('must_quote', []):
                if phrase not in answer:
                    print(f"❌ QUOTE MISSING: '{phrase}'")
                    quote_fail = True
            if quote_fail: continue
            print("✅ All Quotes Present")

            # 3. Check Forbidden
            forbidden_fail = False
            for phrase in specs.get('forbidden', []):
                if phrase in answer:
                    print(f"❌ FORBIDDEN PHRASE FOUND: '{phrase}'")
                    forbidden_fail = True
            if forbidden_fail: continue
            print("✅ No Forbidden Phrases")
            
            passed += 1
            print(f"✅ CASE {case_id} PASSED")
            
        except Exception as e:
            print(f"❌ EXCEPTION: {str(e)}")
            import traceback
            traceback.print_exc()

    print(f"\n[SUMMARY] {passed}/{total} Tests Passed")
    
if __name__ == "__main__":
    load_dotenv(backend_dir / '.env')
    test_ground_truth()
