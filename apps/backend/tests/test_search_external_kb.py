import unittest
from unittest.mock import patch

from config import settings
from services import search_service


def _base_chunk() -> dict:
    return {
        "title": "Doc A",
        "content_chunk": "Toplum ve devlet teorisi uzerine notlar",
        "source_type": "HIGHLIGHT",
        "page_number": 1,
        "book_id": "b1",
        "score": 0.9,
    }


def _classify_stub(_keywords, chunk):
    chunk.setdefault("answerability_score", 2.0)
    chunk.setdefault("epistemic_level", "A")
    return chunk


class SearchExternalKBTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
            "EXTERNAL_KB_MAX_CANDIDATES": settings.EXTERNAL_KB_MAX_CANDIDATES,
            "EXTERNAL_KB_GRAPH_WEIGHT": settings.EXTERNAL_KB_GRAPH_WEIGHT,
        }
        settings.EXTERNAL_KB_ENABLED = True
        settings.EXTERNAL_KB_MAX_CANDIDATES = 5
        settings.EXTERNAL_KB_GRAPH_WEIGHT = 0.15

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["toplum"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_external_meta", return_value={"academic_scope": True, "wikidata_qid": "Q10", "openalex_id": "W20"})
    @patch("services.search_service.maybe_refresh_external_for_explorer_async", return_value=True)
    @patch(
        "services.search_service.get_external_graph_candidates",
        return_value=[
            {
                "title": "External KB (OPENALEX)",
                "content_chunk": "Toplum has topic modernite",
                "page_number": 0,
                "source_type": "EXTERNAL_KB",
                "score": 0.61,
                "external_weight": 0.15,
            }
        ],
    )
    def test_explorer_injects_external_candidates(
        self,
        _mock_external_candidates,
        _mock_refresh,
        _mock_external_meta,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="toplum modernite iliskisi nedir",
            firebase_uid="u1",
            context_book_id="b1",
            mode="EXPLORER",
        )

        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("external_kb_used"))
        self.assertEqual(ctx.get("external_graph_candidates_count"), 1)
        self.assertEqual(ctx.get("wikidata_qid"), "Q10")
        self.assertTrue(ctx.get("openalex_used"))
        self.assertTrue(any(c.get("source_type") == "EXTERNAL_KB" for c in ctx.get("chunks", [])))
        self.assertTrue(ctx.get("metadata", {}).get("external_kb_used"))

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["medeniyet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_external_meta", return_value={"academic_scope": False, "wikidata_qid": "Q404567", "openalex_id": None})
    @patch("services.search_service.maybe_refresh_external_for_explorer_async", return_value=True)
    @patch(
        "services.search_service.get_external_graph_candidates",
        return_value=[
            {
                "title": "External KB (WIKIDATA)",
                "content_chunk": "medeniyet related to urban civilization",
                "page_number": 0,
                "source_type": "EXTERNAL_KB",
                "score": 0.7,
                "external_weight": 0.15,
            }
        ],
    )
    def test_explorer_uses_inferred_book_ids_without_context_book_id(
        self,
        _mock_external_candidates,
        _mock_refresh,
        _mock_external_meta,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="medeniyet nedir",
            firebase_uid="u1",
            context_book_id=None,
            mode="EXPLORER",
        )

        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("external_kb_used"))
        self.assertEqual(ctx.get("wikidata_qid"), "Q404567")
        self.assertEqual(ctx.get("external_graph_candidates_count"), 1)


if __name__ == "__main__":
    unittest.main()
