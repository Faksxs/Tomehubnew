import asyncio
from unittest.mock import patch
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from middleware.auth_middleware import verify_firebase_token


class DummyRequest:
    def __init__(self, authorization: str):
        self.headers = {"Authorization": authorization}
        self.state = SimpleNamespace()


def test_verify_firebase_token_returns_uid_when_firebase_ready():
    request = DummyRequest("Bearer test-token")

    with patch("middleware.auth_middleware.settings") as mock_settings:
        mock_settings.FIREBASE_READY = True
        with patch("firebase_admin.auth.verify_id_token", return_value={"uid": "user-123"}):
            uid = asyncio.run(verify_firebase_token(request))

    assert uid == "user-123"


def test_verify_firebase_token_returns_500_when_firebase_not_ready():
    request = DummyRequest("Bearer test-token")

    with patch("middleware.auth_middleware.settings") as mock_settings:
        mock_settings.FIREBASE_READY = False
        with pytest.raises(HTTPException) as exc:
            asyncio.run(verify_firebase_token(request))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Authentication service unavailable"


def test_verify_firebase_token_returns_500_for_unexpected_internal_error():
    request = DummyRequest("Bearer test-token")

    with patch("middleware.auth_middleware.settings") as mock_settings:
        mock_settings.FIREBASE_READY = True
        with patch("firebase_admin.auth.verify_id_token", side_effect=RuntimeError("boom")):
            with pytest.raises(HTTPException) as exc:
                asyncio.run(verify_firebase_token(request))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Authentication service unavailable"
