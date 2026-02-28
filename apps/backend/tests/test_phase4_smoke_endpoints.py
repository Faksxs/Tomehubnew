import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as tomehub_app
from infrastructure.db_manager import DatabaseManager


class Phase4SmokeEndpointsTests(unittest.TestCase):
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

    def test_realtime_poll_outbox_first_shape(self):
        fake_changes = [
            {
                "event_id": 101,
                "event_type": "highlight.synced",
                "entity_type": "HIGHLIGHT",
                "book_id": "b1",
                "item_id": "b1",
                "updated_at_ms": 1234567890,
                "payload": {"inserted": 2},
            }
        ]
        with patch(
            "services.change_event_service.fetch_change_events_since",
            return_value=(fake_changes, 101),
        ):
            resp = self.client.get("/api/realtime/poll", params={"firebase_uid": "u1", "since_ms": 0, "limit": 10})

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["source"], "outbox")
        self.assertEqual(data["last_event_id"], 101)
        self.assertEqual(data["changes"], fake_changes)
        self.assertEqual(data["events"], fake_changes)
        self.assertIn("server_time", data)

    def test_ingestion_status_includes_phase4_metadata(self):
        with patch.object(
            tomehub_app,
            "fetch_ingestion_status",
            return_value={
                "status": "COMPLETED",
                "file_name": "x.pdf",
                "chunk_count": 12,
                "embedding_count": 12,
                "updated_at": None,
                "item_index_state": {
                    "index_freshness_state": "READY",
                    "total_chunks": 12,
                    "embedded_chunks": 12,
                },
            },
        ), patch.object(
            tomehub_app,
            "get_index_freshness_state",
            return_value={"index_freshness_state": "READY", "foo": "bar"},
        ), patch.object(
            tomehub_app,
            "_get_pdf_index_stats",
            return_value={"effective_chunks": 12, "effective_embeddings": 12, "raw_chunks": 12},
        ):
            resp = self.client.get("/api/books/book-1/ingestion-status", params={"firebase_uid": "u1"})

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["match_source"], "exact_book_id")
        self.assertEqual(data["match_confidence"], 1.0)
        self.assertIn("item_index_state", data)
        self.assertEqual(data["item_index_state"]["index_freshness_state"], "READY")

    def test_smart_search_phase4_filters_propagate(self):
        captured = {}

        def _fake_perform_search(*args, **kwargs):
            captured["kwargs"] = kwargs
            return ([{"id": 1, "title": "T", "content_chunk": "c"}], {"total_count": 1})

        with patch("services.smart_search_service.perform_search", side_effect=_fake_perform_search), patch.object(
            tomehub_app, "_allow_dev_unverified_auth", return_value=True
        ):
            resp = self.client.post(
                "/api/smart-search",
                json={
                    "question": "bilhassa",
                    "firebase_uid": "u1",
                    "include_private_notes": True,
                    "visibility_scope": "default",
                    "content_type": "HIGHLIGHT",
                    "ingestion_type": "MANUAL",
                    "limit": 5,
                    "offset": 0,
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(captured["kwargs"]["visibility_scope"], "all")
        self.assertEqual(captured["kwargs"]["content_type"], "HIGHLIGHT")
        self.assertEqual(captured["kwargs"]["ingestion_type"], "MANUAL")
        self.assertEqual(data["metadata"]["visibility_scope"], "all")
        self.assertEqual(data["metadata"]["content_type_filter"], "HIGHLIGHT")
        self.assertEqual(data["metadata"]["ingestion_type_filter"], "MANUAL")

    def test_search_phase4_filters_propagate_to_generate_answer(self):
        captured = {}

        def _fake_generate_answer(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return ("ok", [{"title": "s1", "similarity_score": 0.9}], {"status": "ok"})

        with patch.object(tomehub_app, "generate_answer", side_effect=_fake_generate_answer), patch.object(
            tomehub_app, "_allow_dev_unverified_auth", return_value=True
        ):
            resp = self.client.post(
                "/api/search",
                json={
                    "question": "test soru",
                    "firebase_uid": "u1",
                    "include_private_notes": True,
                    "visibility_scope": "default",
                    "content_type": "NOTE",
                    "ingestion_type": "SYNC",
                    "limit": 5,
                    "offset": 0,
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["answer"], "ok")
        # Positional tail added in app.py partial(generate_answer, ...)
        self.assertEqual(captured["args"][-3], "all")   # visibility_scope
        self.assertEqual(captured["args"][-2], "NOTE")  # content_type
        self.assertEqual(captured["args"][-1], "SYNC")  # ingestion_type
        self.assertEqual(data["metadata"]["visibility_scope"], "all")
        self.assertEqual(data["metadata"]["content_type_filter"], "NOTE")
        self.assertEqual(data["metadata"]["ingestion_type_filter"], "SYNC")


if __name__ == "__main__":
    unittest.main()
