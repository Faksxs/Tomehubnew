import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()

if not firebase_admin._apps:
    cred_path = os.getenv('FIREBASE_CREDENTIALS') 
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
    else:
        firebase_admin.initialize_app()

db = firestore.client()
users = db.collection('users').stream()
found = False
for u in users:
    items = db.collection('users').document(u.id).collection('items').stream()
    for item in items:
        data = item.to_dict()
        title = data.get('title', '').replace('I', 'ı').lower()
        if 'kral lear' in title:
            print(f'Found for UID {u.id}, Doc ID {item.id}')
            print('Data Keys:', list(data.keys()))
            print('Data:', data)
            found = True
if not found:
    print('Kral Lear not found in Firestore')
