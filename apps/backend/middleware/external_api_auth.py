from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from services.external_api_key_service import (
    ExternalApiKeyRecord,
    ensure_external_api_enabled,
    resolve_external_api_key,
    touch_external_api_key,
)


@dataclass
class ExternalApiPrincipal:
    owner_firebase_uid: str
    key_id: int
    key_prefix: str
    scopes: list[str]
    label: Optional[str] = None


def extract_external_api_key_from_request(request: Request) -> str:
    x_api_key = str(request.headers.get("X-API-Key", "") or "").strip()
    if x_api_key:
        return x_api_key

    auth_header = str(request.headers.get("Authorization", "") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


def require_external_scope(principal: ExternalApiPrincipal, required_scope: str) -> None:
    scope = str(required_scope or "").strip().lower()
    if not scope:
        return
    scopes = {str(item or "").strip().lower() for item in principal.scopes}
    if scope not in scopes:
        raise HTTPException(status_code=403, detail=f"Missing required scope: {scope}")


async def verify_external_api_key(request: Request) -> ExternalApiPrincipal:
    try:
        ensure_external_api_enabled()
    except RuntimeError:
        raise HTTPException(status_code=404, detail="External API is disabled")

    raw_key = extract_external_api_key_from_request(request)
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    record: ExternalApiKeyRecord | None = resolve_external_api_key(raw_key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    remote_addr = None
    if request.client is not None:
        remote_addr = request.client.host
    touch_external_api_key(record.key_id, remote_addr=remote_addr)

    return ExternalApiPrincipal(
        owner_firebase_uid=record.owner_firebase_uid,
        key_id=record.key_id,
        key_prefix=record.key_prefix,
        scopes=record.scopes,
        label=record.label,
    )

