#!/usr/bin/env python3
"""Deep dive into Firestore based on discovered UIDs."""
import sys
import os
sys.path.insert(0, '/app')

from infrastructure.db_manager import DatabaseManager
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred_path = "/app/secrets/firebase-admin.json"
if os.path.exists(cred_path):
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
else:
    print(f"ERROR: Credentials not found at {cred_path}")
    sys.exit(1)

print("=" * 60)
print("FIRESTORE DEEP DIVE")
print("=" * 60)

db = firestore.client()

# UID discovered from rateLimits
target_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"

def check_path(path_str):
    print(f"\nChecking path: {path_str}")
    try:
        doc_ref = db.document(path_str)
        doc = doc_ref.get()
        if doc.exists:
            print(f"  [FOUND] Data: {list(doc.to_dict().keys())[:10]}")
            # Check subcollections
            for col in doc_ref.collections():
                print(f"    subcol: {col.id}")
                count = 0
                for _ in col.limit(5).stream():
                    count += 1
                print(f"      docs found: {count}+")
        else:
            print("  [NOT FOUND]")
    except Exception as e:
        print(f"  [ERROR] {e}")

# Try common paths based on what I see in the codebase and typical structures
check_path(f"users/{target_uid}")
# Sometimes it's plural or has different segments
check_path(f"accounts/{target_uid}")

# List first 10 docs in root collections
print("\n--- Root Collection Scan ---")
root_cols = db.collections()
for col in root_cols:
    print(f"\nCollection: {col.id}")
    count = 0
    for doc in col.limit(3).stream():
        count += 1
        data = doc.to_dict() or {}
        print(f"  - doc: {doc.id}, fields: {list(data.keys())[:5]}")
        # Peek into subcollections
        for subcol in doc.reference.collections():
            print(f"    - subcol: {subcol.id}")
            sub_count = 0
            for _ in subcol.limit(1).stream():
                sub_count += 1
            print(f"      - found docs: {sub_count}+")

print("\n--- Summary ---")
print("Audit complete.")
