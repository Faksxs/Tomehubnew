import asyncio
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from middleware.admin_middleware import require_admin


def _build_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/admin/test", "headers": []})


class RequireAdminTests(unittest.TestCase):
    def test_allowlist_uid_is_authorized_in_production(self):
        request = _build_request()

        with patch("middleware.admin_middleware.settings") as mock_settings:
            mock_settings.ADMIN_UID_ALLOWLIST = {"admin-1"}
            mock_settings.ENVIRONMENT = "production"
            result = asyncio.run(require_admin(request, "admin-1"))

        self.assertEqual(result, "admin-1")

    def test_admin_claim_is_authorized_in_production(self):
        request = _build_request()
        request.state.firebase_decoded_token = {"admin": True, "uid": "user-1"}

        with patch("middleware.admin_middleware.settings") as mock_settings:
            mock_settings.ADMIN_UID_ALLOWLIST = set()
            mock_settings.ENVIRONMENT = "production"
            result = asyncio.run(require_admin(request, "user-1"))

        self.assertEqual(result, "user-1")

    def test_non_admin_is_rejected_in_production(self):
        request = _build_request()

        with patch("middleware.admin_middleware.settings") as mock_settings:
            mock_settings.ADMIN_UID_ALLOWLIST = set()
            mock_settings.ENVIRONMENT = "production"
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(require_admin(request, "user-2"))

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
