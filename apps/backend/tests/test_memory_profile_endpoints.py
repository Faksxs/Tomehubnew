import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as tomehub_app
from infrastructure.db_manager import DatabaseManager


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
        self._orig_env = tomehub_app.settings.ENVIRONMENT
        self._orig_dev_bypass = getattr(tomehub_app.settings, "DEV_UNSAFE_AUTH_BYPASS", False)
        self._orig_firebase_ready = getattr(tomehub_app.settings, "FIREBASE_READY", False)
        tomehub_app.settings.ENVIRONMENT = "development"
        tomehub_app.settings.DEV_UNSAFE_AUTH_BYPASS = True
        tomehub_app.settings.FIREBASE_READY = False

    def tearDown(self):
        tomehub_app.settings.ENVIRONMENT = self._orig_env
        tomehub_app.settings.DEV_UNSAFE_AUTH_BYPASS = self._orig_dev_bypass
        tomehub_app.settings.FIREBASE_READY = self._orig_firebase_ready

    def test_get_memory_profile_returns_missing_shape_when_absent(self):
        with patch("services.memory_profile_service.get_memory_profile", return_value=None):
            response = self.client.get("/api/memory/profile", params={"firebase_uid": "u1"})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["firebase_uid"], "u1")
        self.assertEqual(body["status"], "missing")
        self.assertEqual(body["active_themes"], [])

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
