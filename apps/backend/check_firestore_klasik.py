import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import settings

def check_firestore(uid):
    if not settings.FIREBASE_READY:
        print("Firebase Admin SDK is not ready.")
        return

    from firebase_admin import firestore
    db = firestore.client()
    
    print(f"Checking Firestore for UID: {uid}")
    docs = db.collection("users").document(uid).collection("items").stream()
    
    found = False
    for doc in docs:
        data = doc.to_dict()
        title = data.get("title", "")
        if "Klasik" in title or "Sosyoloji" in title:
            print(f"FOUND IN FIRESTORE -> ID: {doc.id} | Title: {title} | Type: {data.get('type')}")
            found = True
            
    if not found:
        print("Not found in Firestore either.")

if __name__ == "__main__":
    check_firestore("vpq1p0UzcCSLAh1d18WgZZeTebh1")
