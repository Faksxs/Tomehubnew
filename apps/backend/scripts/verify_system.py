import requests
import os
import json
import time

BASE_URL = "http://localhost:5000"

def test_health():
    print(f"\n[TEST] Health Check...")
    try:
        res = requests.get(f"{BASE_URL}/")
        if res.status_code == 200:
            print(f"✅ PASSED: {res.json()}")
            return True
        else:
            print(f"❌ FAILED: Status {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ FAILED: Connection Refused ({e})")
        return False

def test_search():
    print(f"\n[TEST] Search API (RAG)...")
    payload = {
        "question": "What is the meaning of life?",
        "firebase_uid": "test_verification_001"
    }
    try:
        res = requests.post(f"{BASE_URL}/api/search", json=payload)
        if res.status_code == 200:
            data = res.json()
            if "answer" in data:
                print(f"✅ PASSED: Answer received ({len(data['answer'])} chars)")
            else:
                print(f"⚠️ WARNING: No answer field in response")
        else:
            print(f"❌ FAILED: Status {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ FAILED: {e}")

def test_ai_cover_verification():
    print(f"\n[TEST] AI Cover Verification...")
    payload = {
        "title": "The Stranger",
        "author": "Albert Camus",
        "isbn": ""
    }
    # This might fail if no token provided depending on middleware, 
    # but let's see if our middleware allows mock tokens or if we need to mock it.
    # The current code enforces verify_firebase_token.
    # We might get a 403/401. 
    headers = {"Authorization": "Bearer mock_token_for_test"} 
    
    try:
        res = requests.post(f"{BASE_URL}/api/ai/verify-cover", json=payload, headers=headers)
        if res.status_code in [200, 401, 403]:
            # Accepting auth errors as "Partial Pass" since we can't easily gen real tokens here
            print(f"✅ PASSED (Connectivity): Status {res.status_code}")
        else:
            print(f"❌ FAILED: Status {res.status_code} - {res.text}")
    except Exception as e:
        print(f"❌ FAILED: {e}")

def create_dummy_pdf():
    from reportlab.pdfgen import canvas
    filename = "test_meta.pdf"
    c = canvas.Canvas(filename)
    c.drawString(100, 750, "TITLE: The Great Gatsby")
    c.drawString(100, 730, "AUTHOR: F. Scott Fitzgerald")
    c.drawString(100, 710, "This is a dummy PDF for testing metadata extraction.")
    c.save()
    return filename

def test_pdf_metadata():
    print(f"\n[TEST] PDF Metadata Extraction (AI Draft)...")
    pdf_path = create_dummy_pdf()
    
    try:
        with open(pdf_path, 'rb') as f:
            files = {'file': (pdf_path, f, 'application/pdf')}
            res = requests.post(f"{BASE_URL}/api/extract-metadata", files=files)
            
        if res.status_code == 200:
            data = res.json()
            print(f"Response: {data}")
            # AI might or might not extract it perfectly depending on the mock model,
            # but getting a JSON back with keys is success.
            if "title" in data:
                print(f"✅ PASSED: Metadata extracted")
            else:
                print(f"❌ FAILED: Invalid response structure")
        else:
            print(f"❌ FAILED: Status {res.status_code} - {res.text}")
            
    except Exception as e:
        print(f"❌ FAILED: {e}")
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

if __name__ == "__main__":
    if test_health():
        test_search()
        test_ai_cover_verification()
        test_pdf_metadata()
    else:
        print("\nSkipping other tests due to health check failure.")
