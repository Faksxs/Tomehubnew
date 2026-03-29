import unittest
import importlib
import inspect
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as tomehub_app
from infrastructure.db_manager import DatabaseManager
from middleware.auth_middleware import verify_firebase_token
from models.flow_models import FlowCard, FlowNextResponse, FlowStartResponse


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
        self._orig_overrides = dict(tomehub_app.app.dependency_overrides)
        tomehub_app.app.dependency_overrides[verify_firebase_token] = lambda: "u1"

    def tearDown(self):
        tomehub_app.app.dependency_overrides = self._orig_overrides

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
            resp = self.client.get("/api/realtime/poll", params={"since_ms": 0, "limit": 10})

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
            resp = self.client.get("/api/books/book-1/ingestion-status")

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["match_source"], "exact_book_id")
        self.assertEqual(data["match_confidence"], 1.0)
        self.assertIn("item_index_state", data)
        self.assertEqual(data["item_index_state"]["index_freshness_state"], "READY")

    def test_ingestion_status_self_heals_stale_failed_status_when_content_exists(self):
        with patch.object(
            tomehub_app,
            "fetch_ingestion_status",
            return_value={
                "status": "FAILED",
                "file_name": "x.pdf",
                "chunk_count": 0,
                "embedding_count": 0,
                "updated_at": None,
                "item_index_state": None,
            },
        ), patch.object(
            tomehub_app,
            "get_index_freshness_state",
            return_value={"index_freshness_state": "READY"},
        ), patch.object(
            tomehub_app,
            "_get_pdf_index_stats",
            return_value={"effective_chunks": 47, "effective_embeddings": 45, "raw_chunks": 48},
        ), patch.object(
            tomehub_app,
            "upsert_ingestion_status",
        ) as mock_upsert:
            resp = self.client.get("/api/books/book-1/ingestion-status")

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["chunk_count"], 47)
        self.assertEqual(data["embedding_count"], 45)
        mock_upsert.assert_called_once_with(
            book_id="book-1",
            firebase_uid="u1",
            status="COMPLETED",
            file_name="x.pdf",
            chunk_count=47,
            embedding_count=45,
        )

    def test_smart_search_phase4_filters_propagate(self):
        captured = {}

        def _fake_perform_search(*args, **kwargs):
            captured["kwargs"] = kwargs
            return ([{"id": 1, "title": "T", "content_chunk": "c"}], {"total_count": 1})

        with patch("services.smart_search_service.perform_search", side_effect=_fake_perform_search):
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
        self.assertEqual(captured["kwargs"]["result_mix_policy"], "lexical_then_semantic_tail")
        self.assertEqual(captured["kwargs"]["search_surface"], "CORE")
        self.assertEqual(captured["kwargs"]["content_type"], "HIGHLIGHT")
        self.assertEqual(captured["kwargs"]["ingestion_type"], "MANUAL")
        self.assertEqual(data["metadata"]["visibility_scope"], "all")
        self.assertEqual(data["metadata"]["search_surface"], "CORE")
        self.assertEqual(data["metadata"]["content_type_filter"], "HIGHLIGHT")
        self.assertEqual(data["metadata"]["ingestion_type_filter"], "MANUAL")

    def test_smart_search_pdf_only_surface_propagates(self):
        captured = {}

        def _fake_perform_search(*args, **kwargs):
            captured["kwargs"] = kwargs
            return ([], {"total_count": 0})

        with patch("services.smart_search_service.perform_search", side_effect=_fake_perform_search):
            resp = self.client.post(
                "/api/smart-search",
                json={
                    "question": "kader",
                    "firebase_uid": "u1",
                    "search_surface": "PDF_ONLY",
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertIsNone(captured["kwargs"]["result_mix_policy"])
        self.assertEqual(captured["kwargs"]["search_surface"], "PDF_ONLY")
        self.assertEqual(data["metadata"]["search_surface"], "PDF_ONLY")

    def test_smart_search_service_contract_supports_phase4_filters(self):
        from services.smart_search_service import perform_search as smart_perform_search

        params = inspect.signature(smart_perform_search).parameters
        self.assertIn("search_surface", params)
        self.assertIn("content_type", params)
        self.assertIn("ingestion_type", params)

    def test_library_service_contract_supports_media_toggle(self):
        from services.library_service import list_library_items

        params = inspect.signature(list_library_items).parameters
        self.assertIn("include_media", params)

    def test_search_system_mix_policy_module_is_importable(self):
        mod = importlib.import_module("services.search_system.mix_policy")
        self.assertTrue(hasattr(mod, "resolve_result_mix_policy"))

    def test_search_service_generate_answer_contract_supports_phase4_filters(self):
        from services.search_service import generate_answer

        params = inspect.signature(generate_answer).parameters
        self.assertIn("visibility_scope", params)
        self.assertIn("content_type", params)
        self.assertIn("ingestion_type", params)

    def test_dual_ai_orchestrator_contract_matches_chat_route(self):
        from services.dual_ai_orchestrator import generate_evaluated_answer

        params = inspect.signature(generate_evaluated_answer).parameters
        self.assertIn("question", params)
        self.assertIn("chunks", params)
        self.assertIn("answer_mode", params)
        self.assertIn("confidence_score", params)
        self.assertIn("network_status", params)
        self.assertIn("conversation_state", params)
        self.assertIn("source_diversity_count", params)

    def test_search_phase4_filters_propagate_to_generate_answer(self):
        captured = {}

        def _fake_generate_answer(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return ("ok", [{"title": "s1", "similarity_score": 0.9}], {"status": "ok"})

        with patch.object(tomehub_app, "generate_answer", side_effect=_fake_generate_answer):
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
        self.assertEqual(captured["kwargs"]["visibility_scope"], "all")
        self.assertEqual(captured["kwargs"]["content_type"], "NOTE")
        self.assertEqual(captured["kwargs"]["ingestion_type"], "SYNC")
        self.assertEqual(data["metadata"]["visibility_scope"], "all")
        self.assertEqual(data["metadata"]["content_type_filter"], "NOTE")
        self.assertEqual(data["metadata"]["ingestion_type_filter"], "SYNC")

    def test_flow_start_route_smoke(self):
        fake_card = FlowCard(
            flow_id="f1",
            chunk_id="123",
            content="Metin",
            title="Card One",
            source_type="personal",
            epistemic_level="B",
            zone=1,
        )

        class _FakeFlowService:
            def start_session(self, flow_request):
                return FlowStartResponse(
                    session_id="s1",
                    initial_cards=[fake_card],
                    topic_label="Kader",
                )

        with patch("routes.flow_routes.get_flow_service", return_value=_FakeFlowService()), patch(
            "routes.flow_routes._prefetch_flow_batch",
            return_value=None,
        ):
            resp = self.client.post(
                "/api/flow/start",
                json={
                    "firebase_uid": "u1",
                    "anchor_type": "topic",
                    "anchor_id": "kader",
                    "mode": "FOCUS",
                    "horizon_value": 0.25,
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["session_id"], "s1")
        self.assertEqual(data["topic_label"], "Kader")
        self.assertEqual(data["initial_cards"][0]["chunk_id"], "123")

    def test_flow_next_route_smoke(self):
        fake_card = FlowCard(
            flow_id="f2",
            chunk_id="456",
            content="Metin",
            title="Card Two",
            source_type="pdf_chunk",
            epistemic_level="A",
            zone=2,
        )

        class _FakeFlowService:
            def get_next_batch(self, flow_request):
                return FlowNextResponse(
                    cards=[fake_card],
                    has_more=False,
                    session_state={"cards_shown": 1},
                )

        with patch("routes.flow_routes.get_flow_service", return_value=_FakeFlowService()), patch(
            "routes.flow_routes._prefetch_flow_batch",
            return_value=None,
        ):
            resp = self.client.post(
                "/api/flow/next",
                json={
                    "firebase_uid": "u1",
                    "session_id": "s1",
                    "batch_size": 1,
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["cards"][0]["chunk_id"], "456")
        self.assertFalse(data["has_more"])

    def test_translate_route_smoke(self):
        with patch(
            "services.translation_service.translate_chunk",
            return_value={"en": "Hello", "nl": "Hallo", "etymology": None, "cached": True},
        ):
            resp = self.client.post(
                "/api/ai/translate/123",
                json={
                    "firebase_uid": "u1",
                    "source_text": "Merhaba",
                    "book_title": "Book",
                    "book_author": "Author",
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["en"], "Hello")

    def test_translate_route_surfaces_validation_detail(self):
        with patch(
            "services.translation_service.translate_chunk",
            side_effect=ValueError("Translation payload invalid"),
        ):
            resp = self.client.post(
                "/api/ai/translate/123",
                json={
                    "firebase_uid": "u1",
                    "source_text": "Merhaba",
                },
            )

        self.assertEqual(resp.status_code, 422, resp.text)
        self.assertEqual(resp.json()["detail"], "Translation payload invalid")

    def test_article_upsert_triggers_external_enrichment(self):
        with patch.object(
            tomehub_app,
            "upsert_library_item",
            return_value={"success": True, "item_id": "article-1"},
        ) as mock_upsert, patch.object(
            tomehub_app,
            "maybe_trigger_external_enrichment_async",
            return_value=True,
        ) as mock_external:
            resp = self.client.put(
                "/api/library/items/article-1",
                json={
                    "id": "article-1",
                    "type": "ARTICLE",
                    "title": "OpenAlex Update",
                    "author": "TomeHub",
                    "url": "https://doi.org/10.1000/xyz123",
                    "tags": [],
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        mock_upsert.assert_called_once()
        mock_external.assert_called_once_with(
            book_id="article-1",
            firebase_uid="u1",
            title="OpenAlex Update",
            author="TomeHub",
            tags=[],
            mode_hint="INGEST",
            item_type="ARTICLE",
            source_url="https://doi.org/10.1000/xyz123",
        )


if __name__ == "__main__":
    unittest.main()
