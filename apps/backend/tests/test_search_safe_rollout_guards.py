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
        self.call_count = 0

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        self.call_count += 1
        return [dict(x) for x in self.by_query.get(query, [])]


class _FakeLemma(LemmaMatchStrategy):
    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        return []


class _FakeSemantic(SemanticMatchStrategy):
    def search(self, query, firebase_uid, limit=100, offset=0, intent="SYNTHESIS", resource_type=None, book_id=None, **kwargs):
        return []


class _FakeCache:
    def __init__(self):
        self.store = {}
        self.get_keys = []
        self.set_keys = []

    def get(self, key):
        self.get_keys.append(key)
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.set_keys.append(key)
        self.store[key] = value


def _row(item_id, title, content_chunk, source_type="HIGHLIGHT", score=90.0, match_type="exact_deaccented"):
    return {
        "id": item_id,
        "title": title,
        "content_chunk": content_chunk,
        "source_type": source_type,
        "page_number": 1,
        "tags": "",
        "summary": "",
        "comment": "",
        "score": score,
        "match_type": match_type,
    }


class TestSearchSafeRolloutGuards(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_MODE_ROUTING_ENABLED": settings.SEARCH_MODE_ROUTING_ENABLED,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
            "SEARCH_WIDE_POOL_ENABLED": settings.SEARCH_WIDE_POOL_ENABLED,
            "SEARCH_WIDE_POOL_CANARY_UIDS": set(settings.SEARCH_WIDE_POOL_CANARY_UIDS),
            "SEARCH_WIDE_POOL_LIMIT_DEFAULT": settings.SEARCH_WIDE_POOL_LIMIT_DEFAULT,
            "SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT": settings.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT,
            "SEARCH_BM25PLUS_ENABLED": settings.SEARCH_BM25PLUS_ENABLED,
            "SEARCH_BM25PLUS_SHADOW_ENABLED": settings.SEARCH_BM25PLUS_SHADOW_ENABLED,
            "SEARCH_BM25PLUS_CANARY_UIDS": set(settings.SEARCH_BM25PLUS_CANARY_UIDS),
            "SEARCH_BM25PLUS_MIN_CANDIDATES": settings.SEARCH_BM25PLUS_MIN_CANDIDATES,
            "SEARCH_BM25PLUS_MAX_CANDIDATES": settings.SEARCH_BM25PLUS_MAX_CANDIDATES,
            "SEARCH_BM25PLUS_BLEND_WEIGHT": settings.SEARCH_BM25PLUS_BLEND_WEIGHT,
            "SEARCH_MMR_ENABLED": settings.SEARCH_MMR_ENABLED,
            "SEARCH_MMR_SHADOW_ENABLED": settings.SEARCH_MMR_SHADOW_ENABLED,
            "SEARCH_MMR_CANARY_UIDS": set(settings.SEARCH_MMR_CANARY_UIDS),
            "SEARCH_MMR_MIN_CANDIDATES": settings.SEARCH_MMR_MIN_CANDIDATES,
            "SEARCH_MMR_MAX_CANDIDATES": settings.SEARCH_MMR_MAX_CANDIDATES,
            "SEARCH_MMR_TOP_N": settings.SEARCH_MMR_TOP_N,
            "SEARCH_MMR_LAMBDA": settings.SEARCH_MMR_LAMBDA,
            "SEARCH_RERANK_ENABLED": settings.SEARCH_RERANK_ENABLED,
            "SEARCH_RERANK_SHADOW_ENABLED": settings.SEARCH_RERANK_SHADOW_ENABLED,
            "SEARCH_RERANK_CANARY_UIDS": set(settings.SEARCH_RERANK_CANARY_UIDS),
            "SEARCH_RERANK_MIN_CANDIDATES": settings.SEARCH_RERANK_MIN_CANDIDATES,
            "SEARCH_RERANK_MAX_CANDIDATES": settings.SEARCH_RERANK_MAX_CANDIDATES,
            "SEARCH_RERANK_TOP_N": settings.SEARCH_RERANK_TOP_N,
        }
        settings.SEARCH_MODE_ROUTING_ENABLED = False
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False
        settings.SEARCH_WIDE_POOL_ENABLED = False
        settings.SEARCH_WIDE_POOL_CANARY_UIDS = set()
        settings.SEARCH_WIDE_POOL_LIMIT_DEFAULT = 480
        settings.SEARCH_WIDE_POOL_SEMANTIC_FETCH_LIMIT = 72
        settings.SEARCH_BM25PLUS_ENABLED = False
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = False
        settings.SEARCH_BM25PLUS_CANARY_UIDS = set()
        settings.SEARCH_BM25PLUS_MIN_CANDIDATES = 2
        settings.SEARCH_BM25PLUS_MAX_CANDIDATES = 12
        settings.SEARCH_BM25PLUS_BLEND_WEIGHT = 0.5
        settings.SEARCH_MMR_ENABLED = False
        settings.SEARCH_MMR_SHADOW_ENABLED = False
        settings.SEARCH_MMR_CANARY_UIDS = set()
        settings.SEARCH_MMR_MIN_CANDIDATES = 2
        settings.SEARCH_MMR_MAX_CANDIDATES = 12
        settings.SEARCH_MMR_TOP_N = 3
        settings.SEARCH_MMR_LAMBDA = 0.35
        settings.SEARCH_RERANK_ENABLED = False
        settings.SEARCH_RERANK_SHADOW_ENABLED = False
        settings.SEARCH_RERANK_CANARY_UIDS = set()
        settings.SEARCH_RERANK_MIN_CANDIDATES = 2
        settings.SEARCH_RERANK_MAX_CANDIDATES = 12
        settings.SEARCH_RERANK_TOP_N = 3

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def _make_orch(self, exact_map, cache=None):
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=cache)
        orch.expander = _DummyExpander()
        orch.strategies = [_FakeExact(exact_map), _FakeLemma(), _FakeSemantic(None)]  # type: ignore[arg-type]
        orch._log_search = lambda *args, **kwargs: None
        return orch

    def _search_rows(self):
        return [
            _row(1, "First", "genel ifade", score=99.0),
            _row(2, "Lexical Hit", "ibadet ibadet ibadet acik icerik", score=90.0),
            _row(3, "Diverse Hit", "ibadet ile farkli baglam yeni metin", source_type="INSIGHT", score=89.0),
        ]

    def test_shadow_rollout_flags_preserve_current_order(self):
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = True
        settings.SEARCH_MMR_SHADOW_ENABLED = True
        settings.SEARCH_RERANK_SHADOW_ENABLED = True

        orch = self._make_orch({"ibadet": self._search_rows()})
        results, meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )

        self.assertEqual([row["id"] for row in results[:3]], [1, 2, 3])
        self.assertEqual(meta["bm25plus_mode"], "shadow")
        self.assertEqual(meta["mmr_mode"], "shadow")
        self.assertEqual(meta["rerank_mode"], "shadow")
        self.assertTrue(meta["bm25plus_shadow"])
        self.assertTrue(meta["mmr_shadow"])
        self.assertTrue(meta["rerank_shadow"])
        self.assertFalse(meta["bm25plus_applied"])
        self.assertFalse(meta["mmr_applied"])
        self.assertFalse(meta["rerank_applied"])
        self.assertEqual(meta["bm25plus_status"], "ok")
        self.assertEqual(meta["mmr_status"], "ok")
        self.assertEqual(meta["rerank_status"], "ok")
        self.assertEqual(meta["search_path_summary"]["wide_pool"], "disabled:disabled")
        self.assertEqual(meta["search_path_summary"]["bm25plus"], "shadow:ok")
        self.assertEqual(meta["search_path_summary"]["mmr"], "shadow:ok")
        self.assertEqual(meta["search_path_summary"]["rerank"], "shadow:ok")
        self.assertIn("rerank", meta["latency_trace_ms"])

    def test_canary_rollout_guards_skip_non_canary_uid_without_output_change(self):
        settings.SEARCH_WIDE_POOL_ENABLED = True
        settings.SEARCH_WIDE_POOL_CANARY_UIDS = {"canary-only"}
        settings.SEARCH_BM25PLUS_ENABLED = True
        settings.SEARCH_BM25PLUS_CANARY_UIDS = {"canary-only"}
        settings.SEARCH_MMR_ENABLED = True
        settings.SEARCH_MMR_CANARY_UIDS = {"canary-only"}
        settings.SEARCH_RERANK_ENABLED = True
        settings.SEARCH_RERANK_CANARY_UIDS = {"canary-only"}

        orch = self._make_orch({"ibadet": self._search_rows()})
        results, meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )

        self.assertEqual([row["id"] for row in results[:3]], [1, 2, 3])
        self.assertEqual(meta["wide_pool_mode"], "apply")
        self.assertEqual(meta["wide_pool_status"], "skipped")
        self.assertEqual(meta["wide_pool_skip_reason"], "uid_not_in_canary")
        self.assertFalse(meta["wide_pool_applied"])
        self.assertEqual(meta["bm25plus_mode"], "apply")
        self.assertEqual(meta["bm25plus_status"], "skipped")
        self.assertEqual(meta["bm25plus_skip_reason"], "uid_not_in_canary")
        self.assertFalse(meta["bm25plus_applied"])
        self.assertEqual(meta["mmr_mode"], "apply")
        self.assertEqual(meta["mmr_status"], "skipped")
        self.assertEqual(meta["mmr_skip_reason"], "uid_not_in_canary")
        self.assertFalse(meta["mmr_applied"])
        self.assertEqual(meta["rerank_mode"], "apply")
        self.assertEqual(meta["rerank_status"], "skipped")
        self.assertEqual(meta["rerank_skip_reason"], "uid_not_in_canary")
        self.assertFalse(meta["rerank_applied"])
        self.assertEqual(meta["search_path_summary"]["wide_pool"], "apply:skipped")
        self.assertEqual(meta["search_path_summary"]["bm25plus"], "apply:skipped")
        self.assertEqual(meta["search_path_summary"]["mmr"], "apply:skipped")
        self.assertEqual(meta["search_path_summary"]["rerank"], "apply:skipped")

    def test_cache_key_isolates_shadow_and_apply_rollouts(self):
        cache = _FakeCache()
        orch = self._make_orch({"ibadet": self._search_rows()}, cache=cache)
        exact = orch.strategies[0]

        baseline_results, baseline_meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        baseline_key = cache.set_keys[-1]

        settings.SEARCH_RERANK_SHADOW_ENABLED = True
        shadow_results, shadow_meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        shadow_key = cache.set_keys[-1]

        cached_results, cached_meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )

        self.assertEqual(exact.call_count, 2)
        self.assertNotEqual(baseline_key, shadow_key)
        self.assertEqual(len(cache.set_keys), 2)
        self.assertEqual([row["id"] for row in baseline_results[:3]], [1, 2, 3])
        self.assertEqual([row["id"] for row in shadow_results[:3]], [1, 2, 3])
        self.assertEqual([row["id"] for row in cached_results[:3]], [1, 2, 3])
        self.assertFalse(baseline_meta["CACHE_HIT"])
        self.assertFalse(shadow_meta["CACHE_HIT"])
        self.assertTrue(cached_meta["CACHE_HIT"])
        self.assertEqual(cached_meta["CACHE_LAYER"], "L1_OR_L2")
        self.assertEqual(cached_meta["rerank_mode"], "shadow")
        self.assertTrue(cached_meta["rerank_shadow"])
        self.assertFalse(cached_meta["rerank_applied"])
        self.assertEqual(cached_meta["search_path_summary"]["rerank"], "shadow:ok")


if __name__ == "__main__":
    unittest.main()
