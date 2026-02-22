import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

import firebase_admin
from firebase_admin import credentials, firestore

def test():
    # Initialize Firebase Admin if not already
    try:
        if not firebase_admin._apps:
            cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if cred_path:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
    except Exception as e:
        print(f"Firebase init error: {e}")
        return

    db = firestore.client()
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    
    books_ref = db.collection("users").document(uid).collection("books")
    docs = books_ref.stream()
    
    total_bilhassa_highlights = 0
    print(f"Fetching books for UID {uid} from Firestore...\n")
    
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title", "Unknown")
        highlights = data.get("highlights", [])
        
        bilhassa_count = 0
        for h in highlights:
            text = h.get("text", "").lower()
            if "bilhassa" in text:
                bilhassa_count += 1
                total_bilhassa_highlights += 1
                print(f"- [FS HIGHLIGHT] Book: {title} | Text: {text[:50]}...")
                
        if bilhassa_count > 0:
            print(f"Found {bilhassa_count} bilhassa highlights in '{title}'\n")

    print(f"\nTotal 'bilhassa' highlights found in Firestore: {total_bilhassa_highlights}")

if __name__ == "__main__":
    test()
