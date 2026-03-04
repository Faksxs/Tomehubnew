import unittest

from config import settings
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.strategies import ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy


def _row(item_id, title="R", source_type="HIGHLIGHT", score=90.0, match_type="exact_deaccented"):
    return {
        "id": item_id,
        "title": title,
        "content_chunk": "icerik metni",
        "source_type": source_type,
        "page_number": 1,
        "tags": "",
        "summary": "",
        "comment": "",
        "score": score,
        "match_type": match_type,
    }


class _DummyExpander:
    def expand_query(self, query, max_variations=0):
        return []


class _RecorderExact(ExactMatchStrategy):
    def __init__(self):
        self.last_limit = None

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        self.last_limit = int(limit)
        return [_row(1, title="Exact 1", score=95.0)]


class _RecorderLemma(LemmaMatchStrategy):
    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        return []


class _RecorderSemantic(SemanticMatchStrategy):
    def __init__(self):
        self.last_limit = None

    def search(self, query, firebase_uid, limit=100, offset=0, intent="SYNTHESIS", resource_type=None, book_id=None, **kwargs):
        self.last_limit = int(limit)
        return []


class TestSearchWidePoolPolicy(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_MODE_ROUTING_ENABLED": settings.SEARCH_MODE_ROUTING_ENABLED,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
            "SEARCH_WIDE_POOL_ENABLED": settings.SEARCH_WIDE_POOL_ENABLED,
            "SEARCH_WIDE_POOL_CANARY_UIDS": set(settings.SEARCH_WIDE_POOL_CANARY_UIDS),
            "SEARCH_WIDE_POOL_LIMIT_DIRECT": settings.SEARCH_WIDE_POOL_LIMIT_DIRECT,
            "SEARCH_WIDE_POOL_LIMIT_DEFAULT": settings.SEARCH_WIDE_POOL_LIMIT_DEFAULT,
            "SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT": settings.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT,
            "SEARCH_RERANK_ENABLED": settings.SEARCH_RERANK_ENABLED,
            "SEARCH_RERANK_SHADOW_ENABLED": settings.SEARCH_RERANK_SHADOW_ENABLED,
            "SEARCH_BM25PLUS_ENABLED": settings.SEARCH_BM25PLUS_ENABLED,
            "SEARCH_BM25PLUS_SHADOW_ENABLED": settings.SEARCH_BM25PLUS_SHADOW_ENABLED,
        }
        settings.SEARCH_MODE_ROUTING_ENABLED = False
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False
        settings.SEARCH_WIDE_POOL_ENABLED = False
        settings.SEARCH_WIDE_POOL_CANARY_UIDS = set()
        settings.SEARCH_WIDE_POOL_LIMIT_DIRECT = 910
        settings.SEARCH_WIDE_POOL_LIMIT_DEFAULT = 490
        settings.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT = 75
        settings.SEARCH_RERANK_ENABLED = False
        settings.SEARCH_RERANK_SHADOW_ENABLED = False
        settings.SEARCH_BM25PLUS_ENABLED = False
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = False

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def _make_orch(self):
        exact = _RecorderExact()
        lemma = _RecorderLemma()
        semantic = _RecorderSemantic()
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [exact, lemma, semantic]
        orch._log_search = lambda *args, **kwargs: None
        return orch, exact, semantic

    def test_wide_pool_disabled_uses_baseline_limits(self):
        orch, exact, semantic = self._make_orch()
        _results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=20,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(exact.last_limit, 320)
        self.assertEqual(semantic.last_limit, 36)
        self.assertFalse(meta["wide_pool_applied"])
        self.assertEqual(meta["wide_pool_mode"], "disabled")

    def test_wide_pool_enabled_canary_applies_limits(self):
        settings.SEARCH_WIDE_POOL_ENABLED = True
        orch, exact, semantic = self._make_orch()
        _results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=20,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(exact.last_limit, 490)
        self.assertEqual(semantic.last_limit, 75)
        self.assertTrue(meta["wide_pool_applied"])
        self.assertEqual(meta["wide_pool_status"], "ok")

    def test_wide_pool_canary_skip(self):
        settings.SEARCH_WIDE_POOL_ENABLED = True
        settings.SEARCH_WIDE_POOL_CANARY_UIDS = {"canary_uid"}
        orch, exact, semantic = self._make_orch()
        _results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=20,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(exact.last_limit, 320)
        self.assertEqual(semantic.last_limit, 36)
        self.assertFalse(meta["wide_pool_applied"])
        self.assertEqual(meta["wide_pool_status"], "skipped")
        self.assertEqual(meta["wide_pool_skip_reason"], "uid_not_in_canary")


if __name__ == "__main__":
    unittest.main()
