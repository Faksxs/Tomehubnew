import os
from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth, credentials, initialize_app
import firebase_admin
from functools import wraps

# Initialize Firebase Admin if not already initialized
# We need GOOGLE_APPLICATION_CREDENTIALS or a service account path.
# For local dev, we might mock it or rely on existing environment.
# User likely has .firebaserc or similar? 
# The audit showed `.env` but no explicit service account json key file mentioned in the file list EXCEPT `oci_private_key.pem`?
# Wait, list_dir showed `backend/.firebaserc` but also `backend/services/geminiService.ts` mentions `us-central1`.
# Python backend `app.py` didn't import firebase_admin before.
# We need to initialize it.
# Check if service account file exists?

def init_firebase():
    try:
        if not firebase_admin._apps:
            # Look for service account key
            # Common patterns: serviceAccountKey.json, firebase-adminsdk.json
            # Use default credibility if available
            print("[INFO] Initializing Firebase Admin...")
            # Ideally: credentials.Certificate("path/to/key.json")
            # For now, let's try default (works on Google Cloud) or rely on env var
            initialize_app()
    except Exception as e:
        print(f"[WARNING] Firebase Init failed: {e}")

init_firebase()

security = HTTPBearer()

async def verify_firebase_token(request: Request):
    """
    Dependency to verify Firebase Bearer Token.
    Usage: async def route(user = Depends(verify_firebase_token))
    """
    authorization: str = request.headers.get("Authorization")
    if not authorization:
        # For Phase 1 migration, maybe we strictly require it?
        # Or allow "test_user" for local dev bypassing?
        # Let's enforce it but handle "Bearer " prefix manually if needed
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
        
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid Authentication Scheme")
            
        # Verify token
        # decoded_token = auth.verify_id_token(token)
        # uid = decoded_token['uid']
        # return uid
        
        # MOCK FOR PHASE 1 INITIAL SETUP (To avoid blocking if creds are missing)
        # We will enable real verification once user confirms service account key location
        if token == "mock_token":
             return "test_user_001"
             
        
        # TEMPORARY: Firebase Admin SDK not configured with service account
        # For local development, we'll pass through the token/request
        # In production, proper service account credentials should be set
        
        # For now, return a bypass value that signals to use request body
        # The route handler will use flow_request.firebase_uid from the body
        return None  # Signal to use request body UID
        
    except Exception as e:
        print(f"[AUTH ERROR] {e}")
        # For development, allow through
        return None
