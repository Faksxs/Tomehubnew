# -*- coding: utf-8 -*-
"""
Firebase Authentication Middleware
===================================
Verifies Firebase JWT tokens for all protected endpoints.

Production: Real JWT validation using Firebase Admin SDK
Development: Request-body UID fallback (with security warning)
"""

import os
import logging
from fastapi import Request, HTTPException

# Local imports
from config import settings

logger = logging.getLogger(__name__)


async def verify_firebase_token(request: Request) -> str | None:
    """
    Verify Firebase JWT token from Authorization header.
    
    Args:
        request: FastAPI request object
    
    Returns:
        firebase_uid (str): Verified user UID from JWT
        None: In development mode when Firebase not configured (caller should use request body UID)
    
    Raises:
        HTTPException(401): Missing/invalid/expired token
        HTTPException(500): Firebase service error
    
    Usage in routes:
        @app.post("/api/search")
        async def search(
            request: SearchRequest,
            firebase_uid: str = Depends(verify_firebase_token)
        ):
            # firebase_uid is verified JWT or None (dev mode)
            if not firebase_uid:
                # Development mode: use request body UID (with logging)
                firebase_uid = request.firebase_uid
            # Use firebase_uid for query...
    """
    
    # 1. Check if we are in development mode without Firebase
    # (Allow fallback to query params or body UID)
    if settings.ENVIRONMENT == "development" and not settings.FIREBASE_READY:
        # Check for firebase_uid in query parameters (common for GET requests)
        uid = request.query_params.get("firebase_uid")
        if uid:
            logger.debug(f"✓ Using firebase_uid from query params (Dev Mode): {uid}")
            return uid
            
        # Return None to signal caller to check request body (for POST/PUT requests)
        logger.warning(
            "⚠️ DEVELOPMENT MODE: Missing Authorization header. "
            "UID must be provided in request body or query params."
        )
        return None

    # 2. Extract Authorization header
    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    # 3. Parse Bearer token
    try:
        parts = auth_header.split()
        if len(parts) != 2:
            raise ValueError("Invalid Authorization header format")
        
        scheme, token = parts
        if scheme.lower() != "bearer":
            raise ValueError("Invalid Authorization scheme. Expected 'Bearer'")
    
    except ValueError as e:
        logger.warning(f"Invalid Authorization header: {e}")
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    # 4. PRODUCTION/STRICT: Real JWT verification
    try:
        from firebase_admin import auth
        
        if not settings.FIREBASE_READY:
            logger.error("CRITICAL: Firebase Admin SDK not initialized")
            raise HTTPException(status_code=500, detail="Authentication service unavailable")
        
        # Verify the ID token
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")
        
        if not uid:
            logger.error("Firebase token missing 'uid' claim")
            raise HTTPException(status_code=401, detail="Invalid token claims")
        
        logger.debug(f"✓ Firebase JWT verified for UID: {uid}")
        return uid
    
    except ImportError:
        logger.error("firebase-admin not installed")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")
    
    except Exception as e:
        # Handle different Firebase exceptions
        exception_type = type(e).__name__
        
        if "ExpiredIdTokenError" in exception_type:
            logger.warning(f"Expired Firebase token")
            raise HTTPException(status_code=401, detail="Token expired")
        
        elif "InvalidIdTokenError" in exception_type:
            logger.warning(f"Invalid Firebase token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")
        
        elif "UserDisabledError" in exception_type:
            logger.warning(f"Firebase user disabled")
            raise HTTPException(status_code=403, detail="User account disabled")
        
        else:
            # Unknown error
            logger.error(f"Firebase verification failed ({exception_type}): {e}")
            raise HTTPException(status_code=500, detail="Authentication service error")
