import unittest
from unittest.mock import patch

from config import settings
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.strategies import ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy


class _DummyExpander:
    def expand_query(self, query, max_variations=0):
        return []


class _DummySpellChecker:
    def __init__(self, mapping):
        self.mapping = mapping

    def correct(self, text):
        return self.mapping.get(text, text)


class _FakeExact(ExactMatchStrategy):
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None):
        return [dict(x) for x in self.by_query.get(query, [])]


class _FakeLemma(LemmaMatchStrategy):
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None):
        return [dict(x) for x in self.by_query.get(query, [])]


class _FakeSemantic(SemanticMatchStrategy):
    def __init__(self, by_query):
        self.by_query = by_query

    def search(self, query, firebase_uid, limit=100, offset=0, intent='SYNTHESIS', resource_type=None):
        rows = [dict(x) for x in self.by_query.get(query, [])]
        return rows[:limit]


def _row(item_id, title, match_type, source_type='HIGHLIGHT', score=100.0):
    return {
        'id': item_id,
        'title': title,
        'content_chunk': 'x' * 120,
        'source_type': source_type,
        'page_number': 1,
        'tags': '',
        'summary': '',
        'comment': '',
        'score': score,
        'match_type': match_type,
    }


class TestSearchTypoRescue(unittest.TestCase):
    def setUp(self):
        self._saved = {
            'SEARCH_TYPO_RESCUE_ENABLED': settings.SEARCH_TYPO_RESCUE_ENABLED,
            'SEARCH_LEMMA_SEED_FALLBACK_ENABLED': settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            'SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED': settings.SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED,
            'SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS': settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            'SEARCH_NOISE_GUARD_ENABLED': settings.SEARCH_NOISE_GUARD_ENABLED,
        }
        settings.SEARCH_TYPO_RESCUE_ENABLED = True
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED = True
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def _make_orchestrator(self, exact_map, lemma_map, semantic_map):
        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact(exact_map),
            _FakeLemma(lemma_map),
            _FakeSemantic(semantic_map),
        ]
        orch._log_search = lambda *args, **kwargs: None
        return orch

    @patch('services.search_system.orchestrator.get_spell_checker')
    def test_typo_rescue_applies_for_yonetm(self, mock_spell):
        mock_spell.return_value = _DummySpellChecker({'yonetm': 'yonetim'})
        orch = self._make_orchestrator(
            exact_map={'yonetim': [_row(1, 'Yonetim Notu', 'exact_deaccented')]},
            lemma_map={},
            semantic_map={'yonetm': [_row(200, 'Semantic A', 'semantic', score=70.0)]},
        )

        results, meta = orch.search(
            query='yonetm',
            firebase_uid='u1',
            limit=10,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        self.assertTrue(meta['query_correction_applied'])
        self.assertTrue(meta['typo_rescue_applied'])
        self.assertEqual(meta['query_corrected'], 'yonetim')
        self.assertGreaterEqual(meta['retrieval_steps']['exact_raw_count'], 1)
        self.assertEqual(results[0]['match_type'], 'exact_deaccented')

    @patch('services.search_system.orchestrator.get_spell_checker')
    def test_typo_rescue_applies_for_onlarn(self, mock_spell):
        mock_spell.return_value = _DummySpellChecker({'onlarn': 'onlarin'})
        orch = self._make_orchestrator(
            exact_map={'onlarin': [_row(2, 'Onlarin Notu', 'exact_deaccented')]},
            lemma_map={},
            semantic_map={'onlarn': [_row(300, 'Semantic B', 'semantic', score=69.0)]},
        )

        results, meta = orch.search(
            query='onlarn',
            firebase_uid='u1',
            limit=10,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        self.assertTrue(meta['query_correction_applied'])
        self.assertEqual(meta['query_corrected'], 'onlarin')
        self.assertTrue(meta['typo_rescue_applied'])
        self.assertEqual(results[0]['match_type'], 'exact_deaccented')

    @patch('services.search_system.orchestrator.get_spell_checker')
    def test_typo_rescue_not_applied_when_lexical_is_strong(self, mock_spell):
        mock_spell.return_value = _DummySpellChecker({'hayatta': 'hayat'})
        orch = self._make_orchestrator(
            exact_map={'hayatta': [_row(10, 'Exact 1', 'exact_deaccented'), _row(11, 'Exact 2', 'exact_deaccented')]},
            lemma_map={'hayatta': [_row(20, 'Lemma 1', 'lemma_fuzzy'), _row(21, 'Lemma 2', 'lemma_fuzzy')]},
            semantic_map={'hayatta': [_row(400, 'Semantic C', 'semantic', score=68.0)]},
        )

        results, meta = orch.search(
            query='hayatta',
            firebase_uid='u1',
            limit=10,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        self.assertFalse(meta['query_correction_applied'])
        self.assertFalse(meta['typo_rescue_applied'])
        self.assertEqual(meta['query_corrected'], 'hayatta')
        self.assertIn(results[0]['match_type'], {'exact_deaccented', 'lemma_fuzzy'})


if __name__ == '__main__':
    unittest.main()
