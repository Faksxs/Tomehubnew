import requests
import json

def test_enrichment():
    url = "http://localhost:5000/api/ai/enrich-book"
    payload = {
        "title": "Kral Lear",
        "author": "William Shakespeare",
        "summary": "",
        "tags": [],
        "translator": "Can Yücel",
        "publishedDate": "2014",
        "pageCount": 160
    }
    
    print(f"Sending request to {url}...")
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_enrichment()
