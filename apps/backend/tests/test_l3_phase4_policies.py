import unittest
from unittest.mock import patch

from config import settings
from services import search_service


def _classify_stub(_keywords, chunk):
    chunk.setdefault("answerability_score", 3.0)
    chunk.setdefault("epistemic_level", "A")
    return chunk


def _chunk(content_id: int, title: str, text: str, book_id: str = "b1", source_type: str = "PDF_CHUNK"):
    return {
        "id": content_id,
        "title": title,
        "content_chunk": text,
        "source_type": source_type,
        "page_number": 3,
        "chunk_index": content_id,
        "book_id": book_id,
        "score": 75.0,
    }


class TestL3Phase4Policies(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "L3_PHASE4_STEPBACK_ENABLED": settings.L3_PHASE4_STEPBACK_ENABLED,
            "L3_PHASE4_STEPBACK_SHADOW_ENABLED": settings.L3_PHASE4_STEPBACK_SHADOW_ENABLED,
            "L3_PHASE4_STEPBACK_CANARY_UIDS": set(settings.L3_PHASE4_STEPBACK_CANARY_UIDS),
            "L3_PHASE4_PARENT_CONTEXT_ENABLED": settings.L3_PHASE4_PARENT_CONTEXT_ENABLED,
            "L3_PHASE4_PARENT_CONTEXT_SHADOW_ENABLED": settings.L3_PHASE4_PARENT_CONTEXT_SHADOW_ENABLED,
            "L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS": set(settings.L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS),
            "L3_PHASE4_DUP_SUPPRESS_ENABLED": settings.L3_PHASE4_DUP_SUPPRESS_ENABLED,
            "L3_PHASE4_LONG_CONTEXT_REORDER_ENABLED": settings.L3_PHASE4_LONG_CONTEXT_REORDER_ENABLED,
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
        }
        settings.L3_PHASE4_STEPBACK_ENABLED = False
        settings.L3_PHASE4_STEPBACK_SHADOW_ENABLED = False
        settings.L3_PHASE4_STEPBACK_CANARY_UIDS = set()
        settings.L3_PHASE4_PARENT_CONTEXT_ENABLED = False
        settings.L3_PHASE4_PARENT_CONTEXT_SHADOW_ENABLED = False
        settings.L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS = set()
        settings.L3_PHASE4_DUP_SUPPRESS_ENABLED = False
        settings.L3_PHASE4_LONG_CONTEXT_REORDER_ENABLED = False
        settings.EXTERNAL_KB_ENABLED = False

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service._resolve_user_book_ids", return_value=set())
    @patch("services.search_service.resolve_book_ids_from_question", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["ibadet", "toplum", "ahlak"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service._build_stepback_query", return_value="stepback query")
    def test_stepback_apply_adds_candidates(
        self,
        _mock_stepback_query,
        _mock_graph,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_resolve_ids,
        _mock_user_books,
    ):
        settings.L3_PHASE4_STEPBACK_ENABLED = True
        settings.L3_PHASE4_STEPBACK_CANARY_UIDS = {"u1"}

        base = _chunk(1, "Base Doc", "ibadet toplum iliski " + ("x" * 120))
        stepback = _chunk(2, "Stepback Doc", "ahlak toplum catisma " + ("y" * 120))

        def _perform_search_side_effect(query, _uid, **kwargs):
            if query == "stepback query":
                return [stepback], {"search_log_id": None}
            return [base], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=_perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="ibadet toplumdaki rol nedir detayli anlat",
                firebase_uid="u1",
            )

        self.assertTrue(ctx.get("stepback_applied"))
        self.assertEqual(ctx.get("stepback_mode"), "apply")
        self.assertEqual(ctx.get("stepback_query"), "stepback query")
        self.assertGreaterEqual(ctx.get("stepback_candidate_count", 0), 1)
        self.assertTrue(any(c.get("_stepback_hit") for c in ctx.get("chunks", [])))

    @patch("services.search_service._resolve_user_book_ids", return_value=set())
    @patch("services.search_service.resolve_book_ids_from_question", return_value=[])
    @patch("services.search_service.classify_question_intent", return_value=("SYNTHESIS", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["ibadet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    @patch("services.search_service.get_graph_candidates", return_value=[])
    @patch("services.search_service._fetch_parent_context_neighbors")
    def test_parent_context_apply_adds_neighbors(
        self,
        mock_parent_fetch,
        _mock_graph,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_resolve_ids,
        _mock_user_books,
    ):
        settings.L3_PHASE4_PARENT_CONTEXT_ENABLED = True
        settings.L3_PHASE4_PARENT_CONTEXT_CANARY_UIDS = {"u1"}

        base = _chunk(10, "Base Doc", "ibadet toplum iliski " + ("x" * 120), book_id="book_10")
        parent_neighbor = _chunk(
            11,
            "Base Doc",
            "komsu baglam parent context " + ("z" * 120),
            book_id="book_10",
        )
        parent_neighbor["_parent_context"] = True
        parent_neighbor["_parent_anchor_id"] = 10
        mock_parent_fetch.return_value = (
            [parent_neighbor],
            {
                "status": "ok",
                "skip_reason": None,
                "latency_ms": 3,
                "scanned_seeds": 1,
                "candidate_count": 1,
            },
        )

        with patch("services.search_service.perform_search", return_value=([base], {"search_log_id": None})):
            ctx = search_service.get_rag_context(
                question="ibadet toplumdaki rolu nedir",
                firebase_uid="u1",
            )

        self.assertTrue(ctx.get("parent_applied"))
        self.assertEqual(ctx.get("parent_mode"), "apply")
        self.assertEqual(ctx.get("parent_added_count"), 1)
        self.assertTrue(any(c.get("_parent_context") for c in ctx.get("chunks", [])))

    def test_duplicate_suppression_removes_near_duplicates(self):
        chunks = [
            _chunk(1, "A", "adalet toplum ahlak hukuk denge " * 10),
            _chunk(2, "B", "adalet toplum ahlak hukuk denge " * 10),
            _chunk(3, "C", "sanat estetik deneyim yorum " * 10),
        ]
        kept, meta = search_service._apply_duplicate_suppression(
            chunks,
            threshold=0.8,
            compare_window=6,
        )
        self.assertEqual(meta.get("suppressed_count"), 1)
        self.assertEqual(len(kept), 2)

    def test_long_context_reorder_moves_second_rank_to_tail(self):
        chunks = [{"id": i, "content_chunk": f"text {i}", "title": f"T{i}"} for i in [1, 2, 3, 4, 5]]
        reordered = search_service._apply_long_context_reorder(chunks)
        ordered_ids = [c["id"] for c in reordered]
        self.assertEqual(ordered_ids, [1, 3, 5, 4, 2])


if __name__ == "__main__":
    unittest.main()
