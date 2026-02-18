import time
import unittest
from unittest.mock import patch

from config import settings
from services import search_service


def _classify_stub(_keywords, chunk):
    chunk.setdefault("answerability_score", 3.0)
    chunk.setdefault("epistemic_level", "A")
    return chunk


def _make_chunk(item_id: int, book_id: str, source_type: str, score: float) -> dict:
    return {
        "id": item_id,
        "title": f"{book_id}-title",
        "content_chunk": f"{source_type} content for {book_id} " + ("x" * 120),
        "source_type": source_type,
        "page_number": 1,
        "book_id": book_id,
        "score": score,
    }


class SearchComparePolicyTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_COMPARE_POLICY_ENABLED": settings.SEARCH_COMPARE_POLICY_ENABLED,
            "SEARCH_COMPARE_CANARY_UIDS": settings.SEARCH_COMPARE_CANARY_UIDS,
            "SEARCH_COMPARE_TARGET_MAX": settings.SEARCH_COMPARE_TARGET_MAX,
            "SEARCH_COMPARE_PRIMARY_PER_BOOK": settings.SEARCH_COMPARE_PRIMARY_PER_BOOK,
            "SEARCH_COMPARE_SECONDARY_PER_BOOK": settings.SEARCH_COMPARE_SECONDARY_PER_BOOK,
            "SEARCH_COMPARE_GLOBAL_MAX": settings.SEARCH_COMPARE_GLOBAL_MAX,
            "SEARCH_COMPARE_TIMEOUT_MS": settings.SEARCH_COMPARE_TIMEOUT_MS,
            "SEARCH_COMPARE_SECONDARY_MAX_RATIO": settings.SEARCH_COMPARE_SECONDARY_MAX_RATIO,
            "SEARCH_COMPARE_SECONDARY_WEIGHT": settings.SEARCH_COMPARE_SECONDARY_WEIGHT,
            "SEARCH_SCOPE_POLICY_ENABLED": settings.SEARCH_SCOPE_POLICY_ENABLED,
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
        }
        settings.SEARCH_COMPARE_POLICY_ENABLED = True
        settings.SEARCH_COMPARE_CANARY_UIDS = set()
        settings.SEARCH_COMPARE_TARGET_MAX = 8
        settings.SEARCH_COMPARE_PRIMARY_PER_BOOK = 6
        settings.SEARCH_COMPARE_SECONDARY_PER_BOOK = 2
        settings.SEARCH_COMPARE_GLOBAL_MAX = 48
        settings.SEARCH_COMPARE_TIMEOUT_MS = 2500
        settings.SEARCH_COMPARE_SECONDARY_MAX_RATIO = 0.25
        settings.SEARCH_COMPARE_SECONDARY_WEIGHT = 0.45
        settings.SEARCH_SCOPE_POLICY_ENABLED = False
        settings.EXTERNAL_KB_ENABLED = False

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2"})
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["vicdan"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_compare_primary_first_and_secondary_ratio(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_user_books,
    ):
        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            if resource_type == "BOOK":
                rows = [
                    _make_chunk(100 + i, book_id, "PDF_CHUNK", score=90.0 - i)
                    for i in range(3)
                ] + [
                    _make_chunk(200 + i, book_id, "HIGHLIGHT", score=99.0 - i)
                    for i in range(2)
                ]
                return rows, {"search_log_id": None}
            if resource_type == "ALL_NOTES":
                rows = [
                    _make_chunk(300 + i, book_id, "HIGHLIGHT", score=99.0 - i)
                    for i in range(2)
                ]
                return rows, {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="bu gorusu diger kitaplarla karsilastir",
                firebase_uid="u1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=["b1", "b2"],
            )

        self.assertTrue(ctx.get("compare_applied"))
        self.assertEqual(ctx.get("evidence_policy"), "TEXT_PRIMARY_NOTES_SECONDARY_V1")
        chunks = ctx.get("chunks", [])
        primaries = [c for c in chunks if c.get("_compare_primary")]
        secondaries = [c for c in chunks if c.get("_compare_secondary")]
        self.assertGreaterEqual(len(primaries), 1)
        if chunks and secondaries:
            first_secondary_idx = next(i for i, c in enumerate(chunks) if c.get("_compare_secondary"))
            self.assertTrue(all(c.get("_compare_primary") for c in chunks[:first_secondary_idx]))
        self.assertLessEqual(len(secondaries), max(1, len(primaries) // 3))

    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["adalet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_compare_target_truncation_and_unauthorized_drop(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
    ):
        authorized = {f"b{i}" for i in range(1, 11)}
        requested = [f"b{i}" for i in range(1, 21)]

        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            if resource_type == "BOOK":
                return [_make_chunk(1000, book_id, "PDF_CHUNK", score=88.0)], {"search_log_id": None}
            if resource_type == "ALL_NOTES":
                return [_make_chunk(2000, book_id, "HIGHLIGHT", score=70.0)], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service._resolve_user_book_ids", return_value=authorized), patch(
            "services.search_service.perform_search",
            side_effect=perform_search_side_effect,
        ):
            ctx = search_service.get_rag_context(
                question="yazarin gorusunu diger kitaplarla karsilastir",
                firebase_uid="u1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=requested,
            )

        self.assertTrue(ctx.get("compare_applied"))
        self.assertTrue(ctx.get("target_books_truncated"))
        unauthorized_ids = set(ctx.get("unauthorized_target_book_ids") or [])
        self.assertTrue(any(bid in unauthorized_ids for bid in ["b11", "b20"]))
        self.assertLessEqual(len(ctx.get("target_books_used") or []), 8)

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2", "b3"})
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["degisim"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_compare_timeout_partial_results(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_user_books,
    ):
        settings.SEARCH_COMPARE_TIMEOUT_MS = 5

        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            time.sleep(0.06)
            if resource_type == "BOOK":
                return [_make_chunk(5000, book_id, "PDF_CHUNK", score=80.0)], {"search_log_id": None}
            if resource_type == "ALL_NOTES":
                return [_make_chunk(6000, book_id, "HIGHLIGHT", score=65.0)], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="x kavrami diger kitaplarda nasil degismis karsilastir",
                firebase_uid="u1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=["b1", "b2", "b3"],
            )

        self.assertTrue(ctx.get("compare_applied"))
        self.assertTrue(ctx.get("latency_budget_hit"))
        self.assertEqual(ctx.get("compare_degrade_reason"), "timeout_partial_results")

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2"})
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["adalet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_notes_vs_single_book_compare_fetches_global_notes(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_user_books,
    ):
        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            if resource_type == "BOOK" and book_id == "b1":
                return [
                    _make_chunk(7001, "b1", "PDF_CHUNK", score=91.0),
                    _make_chunk(7002, "b1", "PDF_CHUNK", score=89.0),
                ], {"search_log_id": None}
            if resource_type == "ALL_NOTES" and book_id is None:
                return [
                    _make_chunk(7101, "b2", "HIGHLIGHT", score=86.0),
                    _make_chunk(7102, "b2", "INSIGHT", score=84.0),
                ], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="notlarimdaki adalet kavrami ile bu kitaptaki adaleti karsilastir",
                firebase_uid="u1",
                context_book_id="b1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=None,
            )

        self.assertTrue(ctx.get("compare_applied"))
        used = set(ctx.get("target_books_used") or [])
        self.assertIn("b1", used)
        self.assertIn("__USER_NOTES__", used)
        chunks = ctx.get("chunks", [])
        self.assertTrue(any(c.get("_compare_primary") for c in chunks))
        self.assertTrue(any(c.get("_compare_secondary") for c in chunks))
        self.assertTrue(any(str(c.get("book_id")) == "b2" for c in chunks if c.get("_compare_secondary")))

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2"})
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["adalet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_notes_vs_single_book_compare_works_when_compare_flag_off(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_user_books,
    ):
        settings.SEARCH_COMPARE_POLICY_ENABLED = False

        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            if resource_type == "BOOK" and book_id == "b1":
                return [_make_chunk(7201, "b1", "PDF_CHUNK", score=92.0)], {"search_log_id": None}
            if resource_type == "ALL_NOTES" and book_id is None:
                return [_make_chunk(7301, "b2", "HIGHLIGHT", score=85.0)], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="notlarimdaki adalet ile bu kitaptaki adaleti karsilastir",
                firebase_uid="u1",
                context_book_id="b1",
                compare_mode="EXPLICIT_ONLY",
            )

        self.assertTrue(ctx.get("compare_applied"))
        self.assertIn("__USER_NOTES__", set(ctx.get("target_books_used") or []))

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2"})
    @patch("services.search_service.resolve_book_ids_from_question", return_value=["b1", "b2"])
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["adalet"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_compare_auto_resolves_targets_when_not_provided(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_resolve_books,
        _mock_user_books,
    ):
        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            if resource_type == "BOOK":
                item_id = 8101 if str(book_id) == "b1" else 8102
                return [_make_chunk(item_id, book_id, "PDF_CHUNK", score=89.0)], {"search_log_id": None}
            if resource_type == "ALL_NOTES":
                return [_make_chunk(8200, book_id, "HIGHLIGHT", score=70.0)], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="ahlak felsefesi ve mahur beste kitaplarindaki adalet kavramini karsilastir",
                firebase_uid="u1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=None,
                scope_mode="BOOK_FIRST",
                apply_scope_policy=True,
            )

        self.assertTrue(ctx.get("compare_applied"))
        used = set(ctx.get("target_books_used") or [])
        self.assertIn("b1", used)
        self.assertIn("b2", used)
        self.assertEqual(set(ctx.get("auto_resolved_target_book_ids") or []), {"b1", "b2"})

    @patch("services.search_service._resolve_user_book_ids", return_value={"b1", "b2"})
    @patch("services.search_service.classify_question_intent", return_value=("COMPARATIVE", "LOW"))
    @patch("services.search_service.extract_core_concepts", return_value=["adalet", "kavram"])
    @patch("services.search_service.classify_chunk", side_effect=_classify_stub)
    @patch("services.search_service.classify_network_status", return_value={"status": "IN_NETWORK", "reason": "ok"})
    def test_compare_uses_focus_query_for_per_book_retrieval(
        self,
        _mock_network,
        _mock_classify,
        _mock_extract,
        _mock_intent,
        _mock_user_books,
    ):
        def perform_search_side_effect(
            _query,
            _uid,
            intent=None,
            book_id=None,
            resource_type=None,
            limit=None,
            offset=0,
            session_id=None,
            result_mix_policy=None,
            semantic_tail_cap=None,
            **kwargs
        ):
            q = str(_query or "").strip().lower()
            if resource_type == "BOOK" and q == "adalet":
                item_id = 8301 if str(book_id) == "b1" else 8302
                return [_make_chunk(item_id, book_id, "PDF_CHUNK", score=90.0)], {"search_log_id": None}
            if resource_type == "ALL_NOTES":
                return [], {"search_log_id": None}
            return [], {"search_log_id": None}

        with patch("services.search_service.perform_search", side_effect=perform_search_side_effect):
            ctx = search_service.get_rag_context(
                question="ahlak felsefesi ve mahur beste kitaplarindaki adalet kavramini karsilastir",
                firebase_uid="u1",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=["b1", "b2"],
            )

        self.assertTrue(ctx.get("compare_applied"))
        self.assertEqual(ctx.get("compare_focus_query"), "adalet")
        used = set(ctx.get("target_books_used") or [])
        self.assertIn("b1", used)
        self.assertIn("b2", used)


if __name__ == "__main__":
    unittest.main()
