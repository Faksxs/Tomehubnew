from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from middleware.auth_middleware import verify_firebase_token
from models.discovery_models import (
    DiscoveryBoardResponse,
    DiscoveryCategory,
    DiscoveryInnerSpaceResponse,
)
from services.discovery_board_service import get_discovery_board
from services.discovery_inner_space_service import get_discovery_inner_space


router = APIRouter(prefix="/api/discovery", tags=["Discovery"])


def get_verified_uid(uid_from_jwt: str | None) -> str:
    if uid_from_jwt:
        return uid_from_jwt
    raise HTTPException(status_code=401, detail="Authentication required")


@router.get("/board", response_model=DiscoveryBoardResponse)
async def get_discovery_board_endpoint(
    category: DiscoveryCategory = Query(...),
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    try:
        uid = get_verified_uid(firebase_uid_from_jwt)
        return get_discovery_board(category.value, uid)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/inner-space", response_model=DiscoveryInnerSpaceResponse)
async def get_discovery_inner_space_endpoint(
    firebase_uid_from_jwt: Annotated[str | None, Depends(verify_firebase_token)] = None,
):
    try:
        uid = get_verified_uid(firebase_uid_from_jwt)
        return get_discovery_inner_space(uid)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
