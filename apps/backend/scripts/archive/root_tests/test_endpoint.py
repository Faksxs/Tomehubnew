
import requests

def test_endpoint():
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    url = f"http://localhost:5000/api/analytics/ingested-books?firebase_uid={uid}"
    
    print(f"Testing URL: {url}")
    try:
        response = requests.get(url, headers={"Authorization": f"Bearer {uid}"})
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_endpoint()
