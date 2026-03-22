import logging
from typing import Annotated, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from middleware.auth_middleware import verify_firebase_token
from services.user_preferences_service import get_user_preferences, update_user_preferences

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/user", tags=["User"])

def get_verified_uid(uid_from_jwt: str | None) -> str:
    if uid_from_jwt:
        return uid_from_jwt
    raise HTTPException(status_code=401, detail="Authentication required")

@router.get("/preferences/providers")
async def get_providers_preferences(
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    """Get dynamic Layer 3 API provider overrides for the user."""
    uid = get_verified_uid(firebase_uid_from_jwt)
    prefs = get_user_preferences(uid)
    
    # Return JUST the api_preferences dictionary to make frontend consumption easier
    # Example: {"ARXIV": True, "OPENALEX": False}
    return prefs.get("api_preferences", {})

@router.put("/preferences/providers")
async def update_providers_preferences(
    request: Request,
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None
):
    """
    Update dynamic Layer 3 API provider overrides for the user.
    Expects a JSON object like {"ARXIV": true, "OPENALEX": false}
    """
    uid = get_verified_uid(firebase_uid_from_jwt)
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    prefs = get_user_preferences(uid)
    prefs["api_preferences"] = data
    
    success = update_user_preferences(uid, prefs)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update preferences")
        
    return {"success": True, "api_preferences": data}
