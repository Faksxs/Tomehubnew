import time
import unittest

from config import settings
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.strategies import ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy


class _DummyExpander:
    def expand_query(self, query, max_variations=0):
        return []


class _FakeExact(ExactMatchStrategy):
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        return [dict(x) for x in self.by_query.get(query, [])]


class _FakeLemma(LemmaMatchStrategy):
    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        return []


class _FakeSemantic(SemanticMatchStrategy):
    def search(self, query, firebase_uid, limit=100, offset=0, intent="SYNTHESIS", resource_type=None, book_id=None, **kwargs):
        return []


class _FakeOdlRescue:
    def __init__(self, rows_by_query):
        self.rows_by_query = rows_by_query

    def search(self, query, firebase_uid, limit=8, offset=0, **kwargs):
        rows = [dict(x) for x in self.rows_by_query.get(query, [])]
        return rows[:limit]


class _SlowOdlRescue:
    def search(self, query, firebase_uid, limit=8, offset=0, **kwargs):
        time.sleep(0.2)
        return [
            {
                "id": "odl:slow",
                "title": "Slow ODL",
                "content_chunk": "x" * 120,
                "source_type": "ODL_SHADOW",
                "page_number": 1,
                "score": 60.0,
                "match_type": "odl_shadow_exact",
                "odl_shadow": True,
                "content_hash": "h_slow",
            }
        ]


def _row(item_id, title, score=100.0, source_type="HIGHLIGHT", match_type="exact_deaccented", content_hash=None):
    return {
        "id": item_id,
        "title": title,
        "content_chunk": "x" * 120,
        "source_type": source_type,
        "page_number": 1,
        "tags": "",
        "summary": "",
        "comment": "",
        "score": score,
        "match_type": match_type,
        "content_hash": content_hash,
    }


class TestSearchOdlRescue(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_MODE_ROUTING_ENABLED": settings.SEARCH_MODE_ROUTING_ENABLED,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
            "ODL_SECONDARY_ENABLED": settings.ODL_SECONDARY_ENABLED,
            "ODL_RESCUE_ENABLED": settings.ODL_RESCUE_ENABLED,
            "ODL_RESCUE_MIN_RESULTS": settings.ODL_RESCUE_MIN_RESULTS,
            "ODL_RESCUE_TOP1_SCORE_THRESHOLD": settings.ODL_RESCUE_TOP1_SCORE_THRESHOLD,
            "ODL_RESCUE_TIMEOUT_MS": settings.ODL_RESCUE_TIMEOUT_MS,
            "ODL_RESCUE_MAX_CANDIDATES": settings.ODL_RESCUE_MAX_CANDIDATES,
            "ODL_RESCUE_MAX_RATIO": settings.ODL_RESCUE_MAX_RATIO,
            "ODL_SECONDARY_UID_ALLOWLIST": set(settings.ODL_SECONDARY_UID_ALLOWLIST),
            "ODL_SECONDARY_BOOK_ALLOWLIST": set(settings.ODL_SECONDARY_BOOK_ALLOWLIST),
        }
        settings.SEARCH_MODE_ROUTING_ENABLED = False
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False
        settings.ODL_SECONDARY_ENABLED = True
        settings.ODL_RESCUE_ENABLED = True
        settings.ODL_RESCUE_MIN_RESULTS = 5
        settings.ODL_RESCUE_TOP1_SCORE_THRESHOLD = 0.0
        settings.ODL_RESCUE_TIMEOUT_MS = 250
        settings.ODL_RESCUE_MAX_CANDIDATES = 8
        settings.ODL_RESCUE_MAX_RATIO = 0.25
        settings.ODL_SECONDARY_UID_ALLOWLIST = set()
        settings.ODL_SECONDARY_BOOK_ALLOWLIST = set()

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def _make_orch(self, exact_map, odl_strategy):
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [_FakeExact(exact_map), _FakeLemma(), _FakeSemantic(None)]  # type: ignore[arg-type]
        orch.odl_rescue_strategy = odl_strategy
        orch._log_search = lambda *args, **kwargs: None
        return orch

    def test_odl_rescue_adds_candidates_with_ratio_cap(self):
        odl_rows = [
            _row("odl1", "ODL 1", score=60.0, source_type="ODL_SHADOW", match_type="odl_shadow_exact", content_hash="h1"),
            _row("odl2", "ODL 2", score=59.0, source_type="ODL_SHADOW", match_type="odl_shadow_exact", content_hash="h2"),
            _row("odl3", "ODL 3", score=58.0, source_type="ODL_SHADOW", match_type="odl_shadow_exact", content_hash="h3"),
        ]
        for r in odl_rows:
            r["odl_shadow"] = True

        orch = self._make_orch(
            exact_map={"soru": [_row(1, "Primary Exact", score=95.0, content_hash="p1")]},
            odl_strategy=_FakeOdlRescue({"soru": odl_rows}),
        )

        results, meta = orch.search(
            query="soru",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )

        self.assertTrue(meta["odl_rescue_applied"])
        self.assertEqual(meta["odl_rescue_reason"], "low_result_count")
        self.assertEqual(meta["odl_rescue_candidates_added"], 2)  # ratio cap: 25% of top-10
        self.assertEqual(meta["odl_rescue_candidates_topk"], 2)
        self.assertEqual(results[0]["title"], "Primary Exact")

    def test_odl_rescue_disabled_keeps_primary_only(self):
        settings.ODL_RESCUE_ENABLED = False
        orch = self._make_orch(
            exact_map={"soru": [_row(1, "Primary Exact", score=95.0)]},
            odl_strategy=_FakeOdlRescue({"soru": [_row("odl1", "ODL 1", score=60.0)]}),
        )
        results, meta = orch.search(
            query="soru",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertFalse(meta["odl_rescue_applied"])
        self.assertEqual(meta["odl_rescue_candidates_added"], 0)
        self.assertEqual(len(results), 1)

    def test_odl_rescue_timeout_does_not_break_search(self):
        settings.ODL_RESCUE_TIMEOUT_MS = 50
        orch = self._make_orch(
            exact_map={"soru": [_row(1, "Primary Exact", score=95.0)]},
            odl_strategy=_SlowOdlRescue(),
        )
        results, meta = orch.search(
            query="soru",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertTrue(meta["odl_rescue_timed_out"])
        self.assertFalse(meta["odl_rescue_applied"])
        self.assertEqual(meta["odl_rescue_candidates_added"], 0)
        self.assertEqual(results[0]["title"], "Primary Exact")


if __name__ == "__main__":
    unittest.main()
