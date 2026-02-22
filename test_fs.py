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
            if cred_path and not os.path.exists(cred_path):
                # Try apps/backend
                cred_path = os.path.join("apps", "backend", cred_path.lstrip("./"))
            if cred_path and os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
    except Exception as e:
        print(f"Firebase init error: {e}")
        return

    db = firestore.client()
    users_ref = db.collection("users").stream()
    total_bilhassa_highlights = 0
    print("Scanning all users in Firestore...\n")
    
    for user_doc in users_ref:
        uid = user_doc.id
        books_ref = db.collection("users").document(uid).collection("books").stream()
        for doc in books_ref:
            data = doc.to_dict()
            title = data.get("title", "Unknown")
            highlights = data.get("highlights", [])
            
            for h in highlights:
                text = h.get("text", "").lower()
                if "bilhassa" in text:
                    total_bilhassa_highlights += 1
                    print(f"- [UID: {uid}] Book: {title} | Text: {text[:50]}...")
                    
    print(f"\nTotal 'bilhassa' highlights found in Firestore: {total_bilhassa_highlights}")

if __name__ == "__main__":
    test()
