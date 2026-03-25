import pytest
from unittest.mock import patch
from fastapi import HTTPException
from starlette.requests import Request
from middleware.admin_middleware import require_admin

def _build_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/admin/test", "headers": []})

@pytest.mark.asyncio
async def test_allowlist_uid_is_authorized_in_production():
    request = _build_request()
    with patch("middleware.admin_middleware.settings") as mock_settings:
        mock_settings.ADMIN_UID_ALLOWLIST = {"admin-1"}
        mock_settings.ENVIRONMENT = "production"
        result = await require_admin(request, "admin-1")
    assert result == "admin-1"

@pytest.mark.asyncio
async def test_admin_claim_is_authorized_in_production():
    request = _build_request()
    request.state.firebase_decoded_token = {"admin": True, "uid": "user-1"}
    with patch("middleware.admin_middleware.settings") as mock_settings:
        mock_settings.ADMIN_UID_ALLOWLIST = set()
        mock_settings.ENVIRONMENT = "production"
        result = await require_admin(request, "user-1")
    assert result == "user-1"

@pytest.mark.asyncio
async def test_non_admin_is_rejected_in_production():
    request = _build_request()
    with patch("middleware.admin_middleware.settings") as mock_settings:
        mock_settings.ADMIN_UID_ALLOWLIST = set()
        mock_settings.ENVIRONMENT = "production"
        with pytest.raises(HTTPException) as excinfo:
            await require_admin(request, "user-2")
    assert excinfo.value.status_code == 403

