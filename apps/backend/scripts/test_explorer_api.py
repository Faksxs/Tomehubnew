
import json
import http.client
import time

def call_api(path, payload):
    conn = http.client.HTTPConnection("localhost", 5001)
    headers = {'Content-Type': 'application/json'}
    conn.request("POST", path, json.dumps(payload), headers)
    response = conn.getresponse()
    data = response.read().decode()
    conn.close()
    return response.status, json.loads(data)

def test_explorer_flow():
    test_uid = "system_test_user_99" # Mock UID
    question = "Can you explain the relationship between ethics and existentialism from a dialectical perspective?"
    
    print(f"\n[TEST] Question: {question}")
    
    # 1. Test Standard Mode
    print("\n--- Phase 1: Standard Mode ---")
    status, res = call_api("/api/search", {
        "question": question,
        "firebase_uid": test_uid,
        "mode": "STANDARD"
    })
    
    print(f"Status: {status}")
    if status == 200:
        print("Success: Standard Mode responded.")
        # print("Answer Snippet:", res['answer'][:100])
    else:
        print(f"ERROR: {res}")

    # 2. Test Explorer Mode
    print("\n--- Phase 2: Explorer Mode ---")
    start = time.time()
    status, res = call_api("/api/search", {
        "question": question,
        "firebase_uid": test_uid,
        "mode": "EXPLORER"
    })
    latency = time.time() - start
    
    print(f"Status: {status} | Latency: {latency:.2f}s")
    
    if status == 200:
        answer = res['answer']
        print("Success: Explorer Mode responded.")
        
        # Verify Requirements
        has_thesis = "## Temel Bulgular" in answer or "Thesis" in answer or "MEVCUT BİLGİ" in answer
        has_antithesis = "## Eleştirel Açılar" in answer or "Antithesis" in answer or "Eksikler" in answer
        has_synthesis = "## Genişletilmiş Perspektif" in answer or "Synthesis" in answer
        has_genel_bilgi = "[GENEL BİLGİ]" in answer
        
        # Note: Prompts are in Turkish, so we check for Turkish headers
        print(f"CHECK: Dialectical Structure (Thesis)? {'PASS' if has_thesis else 'FAIL'}")
        print(f"CHECK: Dialectical Structure (Antithesis)? {'PASS' if has_antithesis else 'FAIL'}")
        print(f"CHECK: Dialectical Structure (Synthesis)? {'PASS' if has_synthesis else 'FAIL'}")
        print(f"CHECK: General Knowledge Labeling? {'PASS' if has_genel_bilgi else 'FAIL'}")
        
        if not (has_thesis and has_antithesis and has_synthesis):
             print("\nFull Answer Sample for Debugging:")
             print("-" * 20)
             print(answer[:500] + "...")
             print("-" * 20)
    else:
        print(f"ERROR: {res}")

if __name__ == "__main__":
    # Wait for server if needed, but assuming it's up
    try:
        test_explorer_flow()
    except Exception as e:
        print(f"CRITICAL TEST FAILURE: {e}")
