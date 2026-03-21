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


class SearchIslamicExternalTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "ISLAMIC_API_ENABLED": settings.ISLAMIC_API_ENABLED,
            "ISLAMIC_API_MAX_CANDIDATES": settings.ISLAMIC_API_MAX_CANDIDATES,
        }
        settings.ISLAMIC_API_ENABLED = True
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
    @patch(
        "services.search_service.get_islamic_external_candidates",
        return_value=(
            [
                {
                    "title": "QuranEnc - Ayet 23:118 - turkish_rwwad",
                    "content_chunk": "De ki: Rabbim! Bagisla, merhamet et...",
                    "page_number": 0,
                    "source_type": "ISLAMIC_EXTERNAL",
                    "score": 0.91,
                    "external_weight": 0.22,
                    "provider": "QURANENC",
                    "religious_source_kind": "QURAN",
                    "reference": "23:118",
                }
            ],
            {
                "used": True,
                "providers": {"QURANENC": 1},
                "quran_used": True,
                "hadith_used": False,
            },
        ),
    )
    def test_explorer_injects_islamic_external_candidates(
        self,
        _mock_islamic_external,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([_base_chunk()], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="merhamet ile ilgili ayet nedir",
            firebase_uid="u1",
            context_book_id=None,
            mode="EXPLORER",
        )

        self.assertIsNotNone(ctx)
        self.assertTrue(ctx.get("islamic_external_used"))
        self.assertEqual(ctx.get("islamic_external_candidates_count"), 1)
        self.assertEqual(ctx.get("islamic_provider_counts"), {"QURANENC": 1})
        self.assertTrue(ctx.get("quran_external_used"))
        self.assertTrue(any(c.get("source_type") == "ISLAMIC_EXTERNAL" for c in ctx.get("chunks", [])))
        self.assertTrue(ctx.get("metadata", {}).get("islamic_external_used"))

    @patch("services.search_service.perform_search")
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "MEDIUM"))
    @patch("services.search_service.extract_core_concepts", return_value=["zekat"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_islamic_external_candidates", return_value=([], {"used": False, "providers": {}, "quran_used": False, "hadith_used": False}))
    def test_religious_override_forces_islamic_external_call(
        self,
        mock_islamic_external,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_graph,
        mock_search,
    ):
        mock_search.return_value = ([], {"retrieval_path": "hybrid", "retrieval_fusion_mode": "concat"})

        ctx = search_service.get_rag_context(
            question="zekatla ilgili hadisleri araştır",
            firebase_uid="u1",
            context_book_id=None,
            mode="EXPLORER",
            domain_mode="RELIGIOUS",
        )

        self.assertIsNotNone(ctx)
        mock_islamic_external.assert_called_once()
        self.assertEqual(
            mock_islamic_external.call_args.kwargs.get("force_religious"),
            True,
        )


if __name__ == "__main__":
    unittest.main()
