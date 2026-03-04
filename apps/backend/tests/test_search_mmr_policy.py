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


class TestSearchMmrPolicy(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_MODE_ROUTING_ENABLED": settings.SEARCH_MODE_ROUTING_ENABLED,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
            "SEARCH_MMR_ENABLED": settings.SEARCH_MMR_ENABLED,
            "SEARCH_MMR_SHADOW_ENABLED": settings.SEARCH_MMR_SHADOW_ENABLED,
            "SEARCH_MMR_CANARY_UIDS": set(settings.SEARCH_MMR_CANARY_UIDS),
            "SEARCH_MMR_MIN_CANDIDATES": settings.SEARCH_MMR_MIN_CANDIDATES,
            "SEARCH_MMR_MAX_CANDIDATES": settings.SEARCH_MMR_MAX_CANDIDATES,
            "SEARCH_MMR_TOP_N": settings.SEARCH_MMR_TOP_N,
            "SEARCH_MMR_LAMBDA": settings.SEARCH_MMR_LAMBDA,
            "SEARCH_BM25PLUS_ENABLED": settings.SEARCH_BM25PLUS_ENABLED,
            "SEARCH_BM25PLUS_SHADOW_ENABLED": settings.SEARCH_BM25PLUS_SHADOW_ENABLED,
            "SEARCH_RERANK_ENABLED": settings.SEARCH_RERANK_ENABLED,
            "SEARCH_RERANK_SHADOW_ENABLED": settings.SEARCH_RERANK_SHADOW_ENABLED,
        }
        settings.SEARCH_MODE_ROUTING_ENABLED = False
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False
        settings.SEARCH_MMR_ENABLED = False
        settings.SEARCH_MMR_SHADOW_ENABLED = False
        settings.SEARCH_MMR_CANARY_UIDS = set()
        settings.SEARCH_MMR_MIN_CANDIDATES = 2
        settings.SEARCH_MMR_MAX_CANDIDATES = 12
        settings.SEARCH_MMR_TOP_N = 3
        settings.SEARCH_MMR_LAMBDA = 0.35
        settings.SEARCH_BM25PLUS_ENABLED = False
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = False
        settings.SEARCH_RERANK_ENABLED = False
        settings.SEARCH_RERANK_SHADOW_ENABLED = False

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def _make_orch(self, exact_map):
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [_FakeExact(exact_map), _FakeLemma(), _FakeSemantic(None)]  # type: ignore[arg-type]
        orch._log_search = lambda *args, **kwargs: None
        return orch

    def test_mmr_disabled_keeps_order(self):
        rows = [
            _row(1, "A1", "kader kader kader ayni cumle", score=99.0),
            _row(2, "A2", "kader kader kader ayni cumle", score=98.0),
            _row(3, "B", "kader ile farkli baglam yeni metin", score=97.0),
        ]
        orch = self._make_orch({"kader": rows})
        results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[1]["id"], 2)
        self.assertEqual(meta["mmr_mode"], "disabled")
        self.assertFalse(meta["mmr_applied"])

    def test_mmr_apply_promotes_diversity(self):
        settings.SEARCH_MMR_ENABLED = True
        rows = [
            _row(1, "A1", "kader kader kader ayni cumle", score=99.0),
            _row(2, "A2", "kader kader kader ayni cumle", score=98.0),
            _row(3, "B", "kader ile farkli baglam yeni metin", score=97.0),
        ]
        orch = self._make_orch({"kader": rows})
        results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertTrue(meta["mmr_applied"])
        self.assertEqual(meta["mmr_mode"], "apply")
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[1]["id"], 3)

    def test_mmr_shadow_no_output_change(self):
        settings.SEARCH_MMR_SHADOW_ENABLED = True
        rows = [
            _row(1, "A1", "kader kader kader ayni cumle", score=99.0),
            _row(2, "A2", "kader kader kader ayni cumle", score=98.0),
            _row(3, "B", "kader ile farkli baglam yeni metin", score=97.0),
        ]
        orch = self._make_orch({"kader": rows})
        results, meta = orch.search(
            query="kader",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(results[1]["id"], 2)
        self.assertFalse(meta["mmr_applied"])
        self.assertTrue(meta["mmr_shadow"])
        self.assertEqual(meta["mmr_mode"], "shadow")


if __name__ == "__main__":
    unittest.main()
