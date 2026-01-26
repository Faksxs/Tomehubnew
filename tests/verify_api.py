
import requests
import json

def verify_kufur():
    print("--- Verifying 'küfür' via API ---")
    url = "http://localhost:5000/api/smart-search"
    payload = {
        "question": "küfür",
        "firebase_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            data = res.json()
            results = data.get('results', [])
            print(f"✅ API returned {len(results)} results.")
            for r in results:
                print(f"   {r.get('title')} (Score: {r.get('score')})")
                if 'küfür' in r.get('content_chunk', '').lower() or 'kufur' in r.get('content_chunk', '').lower():
                     print("      -> MATCH FOUND in content!")
        else:
            print(f"❌ API Failed: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    verify_kufur()
