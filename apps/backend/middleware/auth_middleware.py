# -*- coding: utf-8 -*-
"""
Firebase Authentication Middleware
===================================
Verifies Firebase JWT tokens for protected endpoints.
"""

import logging
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


async def verify_firebase_token(request: Request) -> str | None:
    """
    Verify Firebase JWT token from Authorization header.

    Returns:
        firebase_uid: Verified user UID from JWT.
    """

    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        logger.warning("Missing Authorization header")
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    try:
        parts = auth_header.split()
        if len(parts) != 2:
            raise ValueError("Invalid Authorization header format")

        scheme, token = parts
        if scheme.lower() != "bearer":
            raise ValueError("Invalid Authorization scheme. Expected 'Bearer'")

    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    try:
        from firebase_admin import auth

        if not settings.FIREBASE_READY:
            logger.error("Firebase Admin SDK is not initialized")
            raise HTTPException(status_code=500, detail="Authentication service unavailable")

        decoded_token = auth.verify_id_token(token)
        uid = decoded_token.get("uid")

        if not uid:
            logger.error("Firebase token missing 'uid' claim")
            raise HTTPException(status_code=401, detail="Invalid token claims")

        return uid

    except ImportError:
        logger.error("firebase-admin is not installed")
        raise HTTPException(status_code=500, detail="Authentication service unavailable")

    except HTTPException:
        raise

    except Exception as e:
        exception_type = type(e).__name__

        if "ExpiredIdTokenError" in exception_type:
            raise HTTPException(status_code=401, detail="Token expired")
        if "InvalidIdTokenError" in exception_type:
            raise HTTPException(status_code=401, detail="Invalid token")
        if "UserDisabledError" in exception_type:
            raise HTTPException(status_code=403, detail="User account disabled")

        logger.warning(f"Firebase verification failed ({exception_type}): {e}")
        raise HTTPException(status_code=401, detail="Authentication verification failed")
