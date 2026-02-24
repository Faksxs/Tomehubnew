# -*- coding: utf-8 -*-
"""
Firebase Authentication Middleware
===================================
Verifies Firebase JWT tokens for protected endpoints.

Production: Real JWT validation using Firebase Admin SDK.
Development: Optional unsafe bypass only when DEV_UNSAFE_AUTH_BYPASS=true.
"""

import logging
from fastapi import Request, HTTPException

from config import settings

logger = logging.getLogger(__name__)


def _allow_dev_unverified_auth() -> bool:
    return (
        settings.ENVIRONMENT == "development"
        and bool(getattr(settings, "DEV_UNSAFE_AUTH_BYPASS", False))
    )


async def verify_firebase_token(request: Request) -> str | None:
    """
    Verify Firebase JWT token from Authorization header.

    Returns:
        firebase_uid: Verified user UID from JWT.
        None: Only when DEV_UNSAFE_AUTH_BYPASS is enabled in development.
    """

    # Dev-only unsafe bypass path (explicit opt-in).
    if _allow_dev_unverified_auth():
        uid = request.query_params.get("firebase_uid")
        if uid:
            logger.warning(
                "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from query params"
            )
            return uid

        try:
            content_type = request.headers.get("content-type", "").lower()

            if "application/json" in content_type:
                payload = await request.json()
                if isinstance(payload, dict):
                    body_uid = payload.get("firebase_uid")
                    if body_uid:
                        logger.warning(
                            "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from JSON body"
                        )
                        return str(body_uid)

            if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = await request.form()
                form_uid = form.get("firebase_uid")
                if form_uid:
                    logger.warning(
                        "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from form body"
                    )
                    return str(form_uid)
        except Exception:
            # Non-blocking in dev bypass mode: fall through to normal auth checks.
            pass

    auth_header = request.headers.get("Authorization", "").strip()
    if not auth_header:
        if _allow_dev_unverified_auth():
            logger.warning(
                "DEV_UNSAFE_AUTH_BYPASS enabled: Missing Authorization header; "
                "allowing request-body UID fallback"
            )
            return None
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

        if _allow_dev_unverified_auth():
            logger.warning(
                "DEV_UNSAFE_AUTH_BYPASS enabled: Firebase token verification failed; "
                "allowing route-level UID fallback",
                extra={"exception_type": exception_type},
            )
            return None

        if "ExpiredIdTokenError" in exception_type:
            raise HTTPException(status_code=401, detail="Token expired")
        if "InvalidIdTokenError" in exception_type:
            raise HTTPException(status_code=401, detail="Invalid token")
        if "UserDisabledError" in exception_type:
            raise HTTPException(status_code=403, detail="User account disabled")

        logger.warning(f"Firebase verification failed ({exception_type}): {e}")
        raise HTTPException(status_code=401, detail="Authentication verification failed")
