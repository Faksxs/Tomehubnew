from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from middleware.auth_middleware import verify_firebase_token
from models.discovery_models import (
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceResponse,
    DiscoveryPageResponse,
)
from services.discovery_cache_service import get_discovery_board_cached, get_discovery_inner_space_cached
from services.discovery_page_service import get_discovery_page


router = APIRouter(prefix="/api/discovery", tags=["Discovery"])


def get_verified_uid(uid_from_jwt: str | None) -> str:
    if uid_from_jwt:
        return uid_from_jwt
    raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/board", response_model=DiscoveryBoardResponse)
async def get_discovery_board_endpoint(
    category: DiscoveryCategory = Query(...),
    force_refresh: bool = Query(False),
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    try:
        uid = get_verified_uid(firebase_uid_from_jwt)
        response, _status, _error = get_discovery_board_cached(category, uid, force_refresh=force_refresh)
        return response
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/inner-space", response_model=DiscoveryInnerSpaceResponse)
async def get_discovery_inner_space_endpoint(
    force_refresh: bool = Query(False),
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    try:
        uid = get_verified_uid(firebase_uid_from_jwt)
        response, _status, _error = get_discovery_inner_space_cached(uid, force_refresh=force_refresh)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/page", response_model=DiscoveryPageResponse)
async def get_discovery_page_endpoint(
    force_refresh: bool = Query(False),
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    try:
        uid = get_verified_uid(firebase_uid_from_jwt)
        return get_discovery_page(uid, force_refresh=force_refresh)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
