import asyncio
from typing import Annotated
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings
from middleware.external_api_auth import (
    ExternalApiPrincipal,
    require_external_scope,
    verify_external_api_key,
)
from models.external_api_models import ExternalSearchRequest, ExternalSearchResponse
from services.external_retrieval_service import run_external_search


router = APIRouter(prefix="/ext/v1", tags=["External API"])


def get_rate_limit_key(request: Request) -> str:
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key, default_limits=[settings.RATE_LIMIT_GLOBAL])


@router.get("/health")
async def external_health() -> dict:
    return {
        "service": "TomeHub External API",
        "enabled": bool(getattr(settings, "EXTERNAL_API_ENABLED", False)),
        "version": "v1",
    }


@router.post("/search", response_model=ExternalSearchResponse)
@limiter.limit(settings.RATE_LIMIT_EXTERNAL_SEARCH)
async def external_search_endpoint(
    request: Request,
    payload: ExternalSearchRequest,
    principal: Annotated[ExternalApiPrincipal, Depends(verify_external_api_key)],
):
    try:
        require_external_scope(principal, "search:read")
        if payload.include_private_notes:
            require_external_scope(principal, "notes:read_private")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(run_external_search, payload, principal.owner_firebase_uid),
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
