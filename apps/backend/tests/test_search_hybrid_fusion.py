import unittest

from config import settings
from services.search_system.mix_policy import resolve_result_mix_policy
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
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None, book_id=None, **kwargs):
        return [dict(x) for x in self.by_query.get(query, [])]


class _FakeSemantic(SemanticMatchStrategy):
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=100, offset=0, intent="SYNTHESIS", resource_type=None, book_id=None, **kwargs):
        return [dict(x) for x in self.by_query.get(query, [])][:limit]


def _row(item_id, title, match_type, score):
    return {
        "id": item_id,
        "title": title,
        "content_chunk": "x" * 180,
        "source_type": "HIGHLIGHT",
        "page_number": 1,
        "tags": "",
        "summary": "",
        "comment": "",
        "score": score,
        "match_type": match_type,
    }


class SearchHybridFusionTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "RETRIEVAL_FUSION_MODE": settings.RETRIEVAL_FUSION_MODE,
            "SEARCH_DEFAULT_RESULT_MIX_POLICY": settings.SEARCH_DEFAULT_RESULT_MIX_POLICY,
            "SEARCH_TYPO_RESCUE_ENABLED": settings.SEARCH_TYPO_RESCUE_ENABLED,
            "SEARCH_LEMMA_SEED_FALLBACK_ENABLED": settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
        }
        settings.RETRIEVAL_FUSION_MODE = "rrf"
        settings.SEARCH_DEFAULT_RESULT_MIX_POLICY = "auto"
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_auto_mix_policy_disables_semantic_tail_for_rrf(self):
        policy = resolve_result_mix_policy(
            None,
            fusion_mode="rrf",
            default_policy="auto",
        )
        self.assertIsNone(policy)

    def test_auto_mix_policy_keeps_semantic_tail_for_concat(self):
        policy = resolve_result_mix_policy(
            None,
            fusion_mode="concat",
            default_policy="auto",
        )
        self.assertEqual(policy, "lexical_then_semantic_tail")

    def test_rrf_promotes_semantic_hit_for_synthesis_queries(self):
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({"adalet nedir": [_row(1, "Exact Result", "exact_deaccented", 99.0)]}),
            _FakeLemma({}),
            _FakeSemantic({"adalet nedir": [_row(2, "Semantic Result", "semantic", 88.0)]}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, meta = orch.search(
            query="adalet nedir",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy=resolve_result_mix_policy(
                None,
                fusion_mode=settings.RETRIEVAL_FUSION_MODE,
                default_policy=settings.SEARCH_DEFAULT_RESULT_MIX_POLICY,
            ),
        )

        self.assertEqual(meta["retrieval_fusion_mode"], "rrf")
        self.assertIsNone(meta["result_mix_policy"])
        self.assertEqual(results[0]["id"], 2)
        self.assertEqual(results[1]["id"], 1)


if __name__ == "__main__":
    unittest.main()
