import os, sys
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
load_dotenv()

def check_fs():
    try:
        cred_path = os.getenv('FIREBASE_CREDENTIALS')
        if not firebase_admin._apps:
            if cred_path:
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                firebase_admin.initialize_app()
    except Exception as e:
        print(f"Failed to init Firebase: {e}")
        return

    db = firestore.client()
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    docs = db.collection("users").document(uid).collection("items").stream()
    
    summary_count = 0
    categories_count = 0
    total = 0
    
    for doc in docs:
        total += 1
        raw = doc.to_dict() or {}
        if raw.get('summary'):
            summary_count += 1
        if raw.get('categories') and len(raw.get('categories')) > 0:
            categories_count += 1
            
    print(f"Total Firestore items evaluated: {total}")
    print(f"Items with 'summary' data: {summary_count}")
    print(f"Items with 'categories' data: {categories_count}")

if __name__ == "__main__":
    check_fs()
