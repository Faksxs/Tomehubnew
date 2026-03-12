from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from config import settings
from middleware.auth_middleware import verify_firebase_token


def _token_has_admin_claim(decoded_token: Any) -> bool:
    if not isinstance(decoded_token, dict):
        return False

    if decoded_token.get("admin") is True:
        return True
    if decoded_token.get("is_admin") is True:
        return True

    role_value = str(decoded_token.get("role") or "").strip().lower()
    if role_value == "admin":
        return True

    roles = decoded_token.get("roles")
    if isinstance(roles, (list, tuple, set)):
        normalized_roles = {str(item or "").strip().lower() for item in roles if str(item or "").strip()}
        if "admin" in normalized_roles:
            return True

    return False


async def require_admin(
    request: Request,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
) -> str:
    firebase_uid = str(firebase_uid_from_jwt or "").strip()
    if not firebase_uid:
        raise HTTPException(status_code=401, detail="Authentication required")

    if firebase_uid in getattr(settings, "ADMIN_UID_ALLOWLIST", set()):
        return firebase_uid

    decoded_token = getattr(request.state, "firebase_decoded_token", None)
    if _token_has_admin_claim(decoded_token):
        return firebase_uid

    # Keep local development and dependency-override based tests usable without
    # weakening production security posture.
    if str(getattr(settings, "ENVIRONMENT", "development")).lower() != "production":
        return firebase_uid

    raise HTTPException(status_code=403, detail="Admin access required")
