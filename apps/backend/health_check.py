
import requests
import time
import sys

def check_health():
    url = "http://localhost:5000/api/smart-search"
    # POST body matches frontend request structure
    payload = {
        "question": "zaman",
        "firebase_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63",
        "limit": 5,
        "offset": 0
    }
    
    print(f"Pinging {url} with POST...")
    
    for i in range(10):
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                print(f"SUCCESS: API is up. Found {len(results)} results.")
                if results:
                    print(f"Top result type: {results[0].get('source_type')}")
                    print(f"Top result match: {results[0].get('match_type')}")
                return
            else:
                print(f"Server returned status {response.status_code}: {response.text}")
        except requests.exceptions.ConnectionError:
            print(f"Attempt {i+1}: Connection refused, waiting...")
            time.sleep(2)
        except Exception as e:
            print(f"Error: {e}")
            break
            
    print("FAILURE: Could not connect to backend.")
    sys.exit(1)

if __name__ == "__main__":
    check_health()
