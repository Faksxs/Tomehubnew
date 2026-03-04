import unittest

from config import settings
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.strategies import (
    ExactMatchStrategy,
    LemmaMatchStrategy,
    SemanticMatchStrategy,
    _should_exclude_pdf_in_first_pass,
)


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

    def search(self, query, firebase_uid, limit=100, offset=0, intent='SYNTHESIS', resource_type=None, book_id=None, **kwargs):
        rows = [dict(x) for x in self.by_query.get(query, [])]
        return rows[:limit]


def _row(item_id, title, match_type, source_type='HIGHLIGHT', score=100.0):
    return {
        'id': item_id,
        'title': title,
        'content_chunk': 'x' * 180,
        'source_type': source_type,
        'page_number': 1,
        'tags': '',
        'summary': '',
        'comment': '',
        'score': score,
        'match_type': match_type,
    }


class TestSearchSemanticTailPolicy(unittest.TestCase):
    def setUp(self):
        self._saved = {
            'SEARCH_TYPO_RESCUE_ENABLED': settings.SEARCH_TYPO_RESCUE_ENABLED,
            'SEARCH_LEMMA_SEED_FALLBACK_ENABLED': settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED,
            'SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED': settings.SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED,
            'SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS': settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            'SEARCH_NOISE_GUARD_ENABLED': settings.SEARCH_NOISE_GUARD_ENABLED,
        }
        settings.SEARCH_TYPO_RESCUE_ENABLED = False
        settings.SEARCH_LEMMA_SEED_FALLBACK_ENABLED = False
        settings.SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED = True
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 0
        settings.SEARCH_NOISE_GUARD_ENABLED = False

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def test_dynamic_cap_bands(self):
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(31), 2)
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(30), 3)
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(20), 3)
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(19), 4)
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(10), 4)
        self.assertEqual(SearchOrchestrator._dynamic_single_token_semantic_cap(9), 5)

    def test_surface_controls_first_pass_pdf_exclusion(self):
        self.assertTrue(_should_exclude_pdf_in_first_pass(resource_type=None, book_id=None, search_surface='CORE'))
        self.assertFalse(_should_exclude_pdf_in_first_pass(resource_type=None, book_id=None, search_surface='PDF_ONLY'))

    def test_dynamic_policy_applies_for_single_token(self):
        exact_rows = [_row(i, f'Lex {i}', 'exact_deaccented') for i in range(1, 26)]
        semantic_rows = [_row(1000 + i, f'Sem {i}', 'semantic', score=70 - i) for i in range(1, 11)]

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({'hayat': exact_rows}),
            _FakeLemma({}),
            _FakeSemantic({'hayat': semantic_rows}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, meta = orch.search(
            query='hayat',
            firebase_uid='u1',
            limit=40,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        self.assertEqual(meta['semantic_tail_policy'], 'dynamic_single_token')
        self.assertEqual(meta['semantic_tail_cap_effective'], 3)
        self.assertEqual(meta['semantic_tail_added'], 3)
        self.assertEqual(meta['lexical_total'], 25)
        self.assertEqual(len(results), 28)

    def test_default_policy_for_multi_token_query(self):
        exact_rows = [_row(i, f'Lex {i}', 'exact_deaccented') for i in range(1, 26)]
        semantic_rows = [_row(2000 + i, f'Sem {i}', 'semantic', score=70 - i) for i in range(1, 11)]

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({'hayat nedir': exact_rows}),
            _FakeLemma({}),
            _FakeSemantic({'hayat nedir': semantic_rows}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, meta = orch.search(
            query='hayat nedir',
            firebase_uid='u1',
            limit=40,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        self.assertEqual(meta['semantic_tail_policy'], 'default')
        self.assertEqual(meta['semantic_tail_cap_effective'], 6)
        self.assertEqual(meta['semantic_tail_added'], 6)
        self.assertEqual(len(results), 31)

    def test_default_scope_suppresses_pdf_when_non_pdf_lexical_exists(self):
        exact_rows = [
            _row(1, 'Kader Note 1', 'exact_deaccented', source_type='HIGHLIGHT', score=99.0),
            _row(2, 'Kader Note 2', 'exact_deaccented', source_type='INSIGHT', score=97.0),
        ]
        lemma_rows = [
            _row(101, 'Kader PDF 1', 'lemma_fuzzy', source_type='PDF_CHUNK', score=92.0),
            _row(102, 'Kader PDF 2', 'lemma_fuzzy', source_type='PDF', score=91.0),
        ]

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({'kader': exact_rows}),
            _FakeLemma({'kader': lemma_rows}),
            _FakeSemantic({}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, meta = orch.search(
            query='kader',
            firebase_uid='u1',
            limit=20,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
        )

        source_types = {str(r.get('source_type', '')).upper() for r in results}
        self.assertNotIn('PDF', source_types)
        self.assertNotIn('PDF_CHUNK', source_types)
        self.assertEqual(meta.get('pdf_like_suppressed_count'), 2)
        self.assertEqual(len(results), 2)

    def test_core_surface_drops_pdf_even_when_only_pdf_exists(self):
        exact_rows = [
            _row(1, 'PDF Match', 'exact_deaccented', source_type='BOOK_CHUNK', score=95.0),
        ]

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({'kader': exact_rows}),
            _FakeLemma({}),
            _FakeSemantic({}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, meta = orch.search(
            query='kader',
            firebase_uid='u1',
            limit=20,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
            search_surface='CORE',
        )

        self.assertEqual(results, [])
        self.assertEqual(meta.get('pdf_like_suppressed_count'), 1)

    def test_pdf_only_surface_keeps_only_pdf_like_sources(self):
        exact_rows = [
            _row(1, 'Kader Note 1', 'exact_deaccented', source_type='HIGHLIGHT', score=99.0),
            _row(2, 'Kader PDF', 'exact_deaccented', source_type='PDF', score=98.0),
        ]
        lemma_rows = [
            _row(3, 'Kader PDF Chunk', 'lemma_fuzzy', source_type='PDF_CHUNK', score=92.0),
            _row(4, 'Kader EPUB', 'lemma_fuzzy', source_type='EPUB', score=91.0),
        ]

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _DummyExpander()
        orch.strategies = [
            _FakeExact({'kader': exact_rows}),
            _FakeLemma({'kader': lemma_rows}),
            _FakeSemantic({}),
        ]
        orch._log_search = lambda *args, **kwargs: None

        results, _meta = orch.search(
            query='kader',
            firebase_uid='u1',
            limit=20,
            intent='SYNTHESIS',
            result_mix_policy='lexical_then_semantic_tail',
            semantic_tail_cap=6,
            search_surface='PDF_ONLY',
        )

        source_types = {str(r.get('source_type', '')).upper() for r in results}
        self.assertTrue(source_types.issubset({'PDF', 'PDF_CHUNK', 'BOOK_CHUNK', 'EPUB', 'ODL_SHADOW'}))
        self.assertNotIn('HIGHLIGHT', source_types)


if __name__ == '__main__':
    unittest.main()
