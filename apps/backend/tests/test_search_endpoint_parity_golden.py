import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as tomehub_app
from infrastructure.db_manager import DatabaseManager
from middleware.auth_middleware import verify_firebase_token


class SearchEndpointParityGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(tomehub_app.app)
        dataset_path = Path("apps/backend/data/search_golden_queries.json")
        if not dataset_path.exists():
            dataset_path = Path("data/search_golden_queries.json")
        cls.cases = json.loads(dataset_path.read_text(encoding="utf-8-sig"))[:10]

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

    @staticmethod
    def _content_type_for(index: int) -> str:
        values = ["HIGHLIGHT", "NOTE", "BOOK"]
        return values[index % len(values)]

    @staticmethod
    def _ingestion_type_for(index: int) -> str:
        values = ["MANUAL", "SYNC", "IMPORT"]
        return values[index % len(values)]

    def test_golden_queries_keep_search_and_smart_search_metadata_in_parity(self):
        for index, case in enumerate(self.cases):
            with self.subTest(case_id=case["id"]):
                captured = {"smart": {}, "search": {}}
                content_type = self._content_type_for(index)
                ingestion_type = self._ingestion_type_for(index)
                expected_visibility = "all" if index % 2 == 0 else "default"

                def _fake_perform_search(*args, **kwargs):
                    query = kwargs.get("query") or (args[0] if args else None)
                    captured["smart"] = {"args": args, "kwargs": kwargs, "query": query}
                    return (
                        [{"id": 1, "title": f"Smart {case['id']}", "content_chunk": "matched"}],
                        {
                            "total_count": 1,
                            "retrieval_mode": case["expected_retrieval_mode"],
                            "result_mix_policy": "lexical_then_semantic_tail",
                            "visibility_scope": expected_visibility,
                            "content_type_filter": content_type,
                            "ingestion_type_filter": ingestion_type,
                            "source_types": ["HIGHLIGHT"],
                        },
                    )

                def _fake_generate_answer(*args, **kwargs):
                    query = kwargs.get("question") or (args[0] if args else None)
                    captured["search"] = {"args": args, "kwargs": kwargs, "query": query}
                    return (
                        "ok",
                        [{"title": f"Search {case['id']}", "similarity_score": 0.91, "source_type": "HIGHLIGHT"}],
                        {
                            "retrieval_mode": case["expected_retrieval_mode"],
                            "result_mix_policy": "lexical_then_semantic_tail",
                            "visibility_scope": expected_visibility,
                            "content_type_filter": content_type,
                            "ingestion_type_filter": ingestion_type,
                            "source_types": ["HIGHLIGHT"],
                        },
                    )

                smart_payload = {
                    "question": case["question"],
                    "firebase_uid": "u1",
                    "include_private_notes": index % 2 == 0,
                    "visibility_scope": "default",
                    "content_type": content_type,
                    "ingestion_type": ingestion_type,
                    "limit": 5,
                    "offset": 0,
                }
                search_payload = {
                    "question": case["question"],
                    "firebase_uid": "u1",
                    "include_private_notes": index % 2 == 0,
                    "visibility_scope": "default",
                    "content_type": content_type,
                    "ingestion_type": ingestion_type,
                    "limit": 5,
                    "offset": 0,
                }

                with patch("services.smart_search_service.perform_search", side_effect=_fake_perform_search), patch.object(
                    tomehub_app,
                    "generate_answer",
                    side_effect=_fake_generate_answer,
                ):
                    smart_resp = self.client.post("/api/smart-search", json=smart_payload)
                    search_resp = self.client.post("/api/search", json=search_payload)

                self.assertEqual(smart_resp.status_code, 200, smart_resp.text)
                self.assertEqual(search_resp.status_code, 200, search_resp.text)

                smart_data = smart_resp.json()
                search_data = search_resp.json()

                self.assertEqual(captured["smart"]["query"], case["question"])
                self.assertEqual(captured["search"]["query"], case["question"])
                self.assertEqual(smart_data["metadata"]["retrieval_mode"], case["expected_retrieval_mode"])
                self.assertEqual(search_data["metadata"]["retrieval_mode"], case["expected_retrieval_mode"])
                self.assertEqual(
                    smart_data["metadata"]["result_mix_policy"],
                    search_data["metadata"]["result_mix_policy"],
                )
                self.assertEqual(
                    smart_data["metadata"]["visibility_scope"],
                    search_data["metadata"]["visibility_scope"],
                )
                self.assertEqual(
                    smart_data["metadata"]["content_type_filter"],
                    search_data["metadata"]["content_type_filter"],
                )
                self.assertEqual(
                    smart_data["metadata"]["ingestion_type_filter"],
                    search_data["metadata"]["ingestion_type_filter"],
                )
                self.assertEqual(smart_data["metadata"]["source_types"], ["HIGHLIGHT"])
                self.assertEqual(search_data["metadata"]["source_types"], ["HIGHLIGHT"])
                self.assertEqual(
                    smart_data["metadata"]["diagnostic_trace_v1"]["endpoint"],
                    "/api/smart-search",
                )
                self.assertEqual(
                    search_data["metadata"]["diagnostic_trace_v1"]["endpoint"],
                    "/api/search",
                )
                self.assertIn(
                    "endpoint=/api/smart-search",
                    smart_data["metadata"]["diagnostic_trace_line"],
                )
                self.assertIn(
                    "endpoint=/api/search",
                    search_data["metadata"]["diagnostic_trace_line"],
                )
                self.assertEqual(
                    smart_data["metadata"]["generation_failure_plane"],
                    "not_applicable",
                )
                self.assertEqual(
                    search_data["metadata"]["freshness_plane"],
                    "not_checked",
                )
                self.assertEqual(search_data["answer"], "ok")
                self.assertEqual(smart_data["total"], 1)


if __name__ == "__main__":
    unittest.main()
