import unittest
from unittest.mock import patch

from config import settings
from services import search_service


def _base_chunk() -> dict:
    return {
        "title": "Doc A",
        "content_chunk": "Rahmet ve adalet uzerine notlar",
        "source_type": "HIGHLIGHT",
        "page_number": 1,
        "book_id": "b1",
        "score": 0.9,
    }


def _classify_stub(_keywords, chunk):
    chunk.setdefault("answerability_score", 2.0)
    chunk.setdefault("epistemic_level", "A")
    return chunk


class SearchDomainPolicyTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "ISLAMIC_API_ENABLED": settings.ISLAMIC_API_ENABLED,
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
            "ISLAMIC_API_MAX_CANDIDATES": settings.ISLAMIC_API_MAX_CANDIDATES,
        }
        settings.ISLAMIC_API_ENABLED = True
        settings.EXTERNAL_KB_ENABLED = True
        settings.ISLAMIC_API_MAX_CANDIDATES = 4

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["rahmet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_islamic_external_candidates", return_value=([], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}))
    @patch("services.search_service.get_external_graph_candidates")
    def test_religious_mode_blocks_external_kb(
        self,
        mock_external_graph,
        _mock_islamic,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="Bakara 2:255 ayeti ne diyor",
            firebase_uid="u1",
            mode="EXPLORER",
            domain_mode="RELIGIOUS",
        )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.get("resolved_domain_mode"), "RELIGIOUS")
        mock_external_graph.assert_not_called()

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["paper"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_islamic_external_candidates")
    def test_academic_mode_blocks_islamic_api(
        self,
        mock_islamic,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="literature review for this paper",
            firebase_uid="u1",
            mode="EXPLORER",
            domain_mode="ACADEMIC",
        )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.get("resolved_domain_mode"), "ACADEMIC")
        mock_islamic.assert_not_called()

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["paper"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_islamic_external_candidates", return_value=([], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}))
    @patch("services.search_service.get_external_graph_candidates", return_value=[])
    @patch("services.search_service.get_domain_external_candidates")
    def test_academic_mode_uses_direct_domain_external_candidates(
        self,
        mock_direct_external,
        _mock_graph_external,
        _mock_islamic,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})
        mock_direct_external.return_value = [
            {
                "title": "Academic Paper",
                "content_chunk": "Venue: Journal | Authors: Ada Writer",
                "page_number": 0,
                "source_type": "EXTERNAL_KB",
                "score": 0.71,
                "external_weight": 0.18,
                "provider": "OPENALEX",
                "source_url": "https://api.openalex.org/W1",
                "reference": "10.1000/xyz",
            }
        ]

        ctx = search_service.get_rag_context(
            question="literature review for this paper",
            firebase_uid="u1",
            mode="EXPLORER",
            domain_mode="ACADEMIC",
        )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.get("resolved_domain_mode"), "ACADEMIC")
        self.assertTrue(any(chunk.get("provider") == "OPENALEX" for chunk in ctx.get("chunks", [])))
        mock_direct_external.assert_called_once()

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["poem"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_islamic_external_candidates", return_value=([], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}))
    @patch("services.search_service.get_external_graph_candidates", return_value=[])
    @patch("services.search_service.get_domain_external_candidates")
    def test_literary_mode_uses_direct_domain_external_candidates(
        self,
        mock_direct_external,
        _mock_graph_external,
        _mock_islamic,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})
        mock_direct_external.return_value = [
            {
                "title": "Collected Poems",
                "content_chunk": "Author: Ada Writer",
                "page_number": 0,
                "source_type": "EXTERNAL_KB",
                "score": 0.69,
                "external_weight": 0.16,
                "provider": "POETRYDB",
                "source_url": None,
                "reference": "Ada Writer",
            }
        ]

        ctx = search_service.get_rag_context(
            question="poem imagery and metaphor",
            firebase_uid="u1",
            mode="EXPLORER",
            domain_mode="LITERARY",
        )

        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.get("resolved_domain_mode"), "LITERARY")
        self.assertTrue(any(chunk.get("provider") == "POETRYDB" for chunk in ctx.get("chunks", [])))
        mock_direct_external.assert_called_once()


if __name__ == "__main__":
    unittest.main()
