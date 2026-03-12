import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as tomehub_app
from infrastructure.db_manager import DatabaseManager
from middleware.auth_middleware import verify_firebase_token


class MemoryProfileEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(tomehub_app.app)

    @classmethod
    def tearDownClass(cls):
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    def setUp(self):
        self._orig_overrides = dict(tomehub_app.app.dependency_overrides)
        tomehub_app.app.dependency_overrides[verify_firebase_token] = lambda: "u1"

    def tearDown(self):
        tomehub_app.app.dependency_overrides = self._orig_overrides

    def test_get_memory_profile_returns_missing_shape_when_absent(self):
        with patch("services.memory_profile_service.get_memory_profile", return_value=None), patch(
            "services.memory_profile_service.refresh_memory_profile",
            return_value=None,
        ):
            response = self.client.get("/api/memory/profile")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["firebase_uid"], "u1")
        self.assertEqual(body["status"], "missing")
        self.assertEqual(body["active_themes"], [])

    def test_get_memory_profile_bootstraps_profile_when_missing(self):
        bootstrapped = {
            "firebase_uid": "u1",
            "profile_summary": "Reader is revisiting conscience and discipline across sessions.",
            "active_themes": ["conscience", "discipline"],
            "recurring_sources": ["Stoicism"],
            "open_questions": ["How should discipline change action?"],
            "evidence_counts": {"notes": 8, "messages": 12},
            "status": "ready",
        }
        with patch("services.memory_profile_service.get_memory_profile", return_value=None), patch(
            "services.memory_profile_service.refresh_memory_profile",
            return_value=bootstrapped,
        ) as mock_refresh:
            response = self.client.get("/api/memory/profile")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["profile_summary"], bootstrapped["profile_summary"])
        mock_refresh.assert_called_once_with("u1", force=False)

    def test_refresh_memory_profile_endpoint_returns_profile(self):
        fake_profile = {
            "firebase_uid": "u1",
            "profile_summary": "Reader keeps revisiting justice and endurance.",
            "active_themes": ["justice", "endurance"],
            "recurring_sources": ["Marcus Aurelius"],
            "open_questions": ["How should endurance shape action?"],
            "evidence_counts": {"messages": 4, "notes": 3},
            "status": "ready",
        }
        with patch("services.memory_profile_service.refresh_memory_profile", return_value=fake_profile):
            response = self.client.post(
                "/api/memory/profile/refresh",
                json={"firebase_uid": "u1", "force": True},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["active_themes"], ["justice", "endurance"])


if __name__ == "__main__":
    unittest.main()
