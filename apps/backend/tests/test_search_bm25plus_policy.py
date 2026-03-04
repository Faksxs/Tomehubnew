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


class TestSearchBm25PlusPolicy(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_MODE_ROUTING_ENABLED": settings.SEARCH_MODE_ROUTING_ENABLED,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
            "SEARCH_BM25PLUS_ENABLED": settings.SEARCH_BM25PLUS_ENABLED,
            "SEARCH_BM25PLUS_SHADOW_ENABLED": settings.SEARCH_BM25PLUS_SHADOW_ENABLED,
            "SEARCH_BM25PLUS_CANARY_UIDS": set(settings.SEARCH_BM25PLUS_CANARY_UIDS),
            "SEARCH_BM25PLUS_MIN_CANDIDATES": settings.SEARCH_BM25PLUS_MIN_CANDIDATES,
            "SEARCH_BM25PLUS_MAX_CANDIDATES": settings.SEARCH_BM25PLUS_MAX_CANDIDATES,
            "SEARCH_BM25PLUS_BLEND_WEIGHT": settings.SEARCH_BM25PLUS_BLEND_WEIGHT,
            "SEARCH_RERANK_ENABLED": settings.SEARCH_RERANK_ENABLED,
            "SEARCH_RERANK_SHADOW_ENABLED": settings.SEARCH_RERANK_SHADOW_ENABLED,
        }
        settings.SEARCH_MODE_ROUTING_ENABLED = False
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False
        settings.SEARCH_BM25PLUS_ENABLED = False
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = False
        settings.SEARCH_BM25PLUS_CANARY_UIDS = set()
        settings.SEARCH_BM25PLUS_MIN_CANDIDATES = 2
        settings.SEARCH_BM25PLUS_MAX_CANDIDATES = 10
        settings.SEARCH_BM25PLUS_BLEND_WEIGHT = 0.5
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

    def test_bm25plus_disabled_keeps_order(self):
        rows = [
            _row(1, "First", "genel ifade", source_type="HIGHLIGHT", score=99.0),
            _row(2, "Better Lex", "ibadet ibadet ibadet acik icerik", source_type="HIGHLIGHT", score=90.0),
        ]
        orch = self._make_orch({"ibadet": rows})
        results, meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(results[0]["id"], 1)
        self.assertEqual(meta["bm25plus_mode"], "disabled")
        self.assertFalse(meta["bm25plus_applied"])

    def test_bm25plus_apply_changes_order(self):
        settings.SEARCH_BM25PLUS_ENABLED = True
        rows = [
            _row(1, "First", "genel ifade", source_type="HIGHLIGHT", score=99.0),
            _row(2, "Better Lex", "ibadet ibadet ibadet acik icerik", source_type="HIGHLIGHT", score=90.0),
            _row(3, "Noise", "farkli metin", source_type="HIGHLIGHT", score=88.0),
        ]
        orch = self._make_orch({"ibadet": rows})
        results, meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertTrue(meta["bm25plus_applied"])
        self.assertEqual(meta["bm25plus_mode"], "apply")
        self.assertEqual(results[0]["id"], 2)

    def test_bm25plus_shadow_no_output_change(self):
        settings.SEARCH_BM25PLUS_SHADOW_ENABLED = True
        rows = [
            _row(1, "First", "genel ifade", source_type="HIGHLIGHT", score=99.0),
            _row(2, "Better Lex", "ibadet ibadet ibadet acik icerik", source_type="HIGHLIGHT", score=90.0),
        ]
        orch = self._make_orch({"ibadet": rows})
        results, meta = orch.search(
            query="ibadet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        self.assertEqual(results[0]["id"], 1)
        self.assertFalse(meta["bm25plus_applied"])
        self.assertTrue(meta["bm25plus_shadow"])
        self.assertEqual(meta["bm25plus_mode"], "shadow")


if __name__ == "__main__":
    unittest.main()
