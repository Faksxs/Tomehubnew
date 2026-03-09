import unittest

from fastapi import HTTPException
from starlette.requests import Request

from middleware.external_api_auth import (
    ExternalApiPrincipal,
    extract_external_api_key_from_request,
    require_external_scope,
)


def _build_request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ext/v1/search",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ],
    }
    return Request(scope)


class ExternalApiAuthTests(unittest.TestCase):
    def test_extracts_x_api_key_header(self):
        request = _build_request({"X-API-Key": "th_live_abc"})
        self.assertEqual(extract_external_api_key_from_request(request), "th_live_abc")

    def test_extracts_bearer_token_when_x_api_key_missing(self):
        request = _build_request({"Authorization": "Bearer th_live_xyz"})
        self.assertEqual(extract_external_api_key_from_request(request), "th_live_xyz")

    def test_require_external_scope_allows_present_scope(self):
        principal = ExternalApiPrincipal(
            owner_firebase_uid="u1",
            key_id=1,
            key_prefix="th_live_123",
            scopes=["search:read", "notes:read_private"],
        )
        require_external_scope(principal, "search:read")

    def test_require_external_scope_rejects_missing_scope(self):
        principal = ExternalApiPrincipal(
            owner_firebase_uid="u1",
            key_id=1,
            key_prefix="th_live_123",
            scopes=["search:read"],
        )
        with self.assertRaises(HTTPException) as ctx:
            require_external_scope(principal, "notes:read_private")
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
