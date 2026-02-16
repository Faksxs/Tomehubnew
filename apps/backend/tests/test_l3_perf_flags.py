import unittest
from types import SimpleNamespace
from unittest.mock import patch
import time

from config import settings
from services import search_service
from services.epistemic_service import build_epistemic_context
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.strategies import ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy


def _ctx_chunk(idx: int, text_len: int = 900):
    return {
        "title": f"Doc {idx}",
        "content_chunk": "x" * text_len,
        "answerability_score": float(100 - idx),
        "epistemic_level": "A",
        "page_number": 1,
        "score": 0.9,
    }


def _orchestrator_row(item_id: int, title: str, match_type: str, score: float = 80.0):
    return {
        "id": item_id,
        "title": title,
        "content_chunk": "y" * 180,
        "source_type": "HIGHLIGHT",
        "page_number": 1,
        "score": score,
        "match_type": match_type,
    }


class _SlowExpander:
    def expand_query(self, query, max_variations=0):
        time.sleep(3.5)
        return [f"{query} varyasyon"] if max_variations else []


class _FastExact(ExactMatchStrategy):
    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None):
        return [_orchestrator_row(1, "Exact Hit", "content_exact")]


class _FastLemma(LemmaMatchStrategy):
    def search(self, query, firebase_uid, limit=1000, offset=0, resource_type=None):
        return []


class _FastSemantic(SemanticMatchStrategy):
    def __init__(self):
        pass

    def search(self, query, firebase_uid, limit=100, offset=0, intent="SYNTHESIS", resource_type=None):
        return []


class TestL3PerfFlags(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "L3_PERF_REWRITE_GUARD_ENABLED": settings.L3_PERF_REWRITE_GUARD_ENABLED,
            "L3_PERF_CONTEXT_BUDGET_ENABLED": settings.L3_PERF_CONTEXT_BUDGET_ENABLED,
            "L3_PERF_OUTPUT_BUDGET_ENABLED": settings.L3_PERF_OUTPUT_BUDGET_ENABLED,
            "L3_PERF_MAX_OUTPUT_TOKENS_STANDARD": settings.L3_PERF_MAX_OUTPUT_TOKENS_STANDARD,
            "L3_PERF_CONTEXT_TOPK_STANDARD": settings.L3_PERF_CONTEXT_TOPK_STANDARD,
            "L3_PERF_CONTEXT_CHARS_STANDARD": settings.L3_PERF_CONTEXT_CHARS_STANDARD,
            "L3_PERF_EXPANSION_TAIL_FIX_ENABLED": settings.L3_PERF_EXPANSION_TAIL_FIX_ENABLED,
            "SEARCH_GRAPH_BRIDGE_TIMEOUT_MS": settings.SEARCH_GRAPH_BRIDGE_TIMEOUT_MS,
            "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS": settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS,
            "SEARCH_NOISE_GUARD_ENABLED": settings.SEARCH_NOISE_GUARD_ENABLED,
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service.get_cache", return_value=None)
    @patch("services.search_service.get_model_for_tier", return_value="gemini-2.5-flash-lite")
    @patch("services.search_service.generate_text")
    def test_rewrite_guard_flag_controls_llm_rewrite(self, mock_generate, _mock_model, _mock_cache):
        question = "bilincalti kurami ve felsefe"
        history = [{"role": "user", "content": "onceki mesaj"}]
        mock_generate.return_value = SimpleNamespace(text="yeniden yazildi")

        settings.L3_PERF_REWRITE_GUARD_ENABLED = False
        rewritten = search_service.rewrite_query_with_history(question, history)
        self.assertEqual(rewritten, "yeniden yazildi")
        self.assertTrue(mock_generate.called)

        mock_generate.reset_mock()
        settings.L3_PERF_REWRITE_GUARD_ENABLED = True
        rewritten_guarded = search_service.rewrite_query_with_history(question, history)
        self.assertEqual(rewritten_guarded, question)
        mock_generate.assert_not_called()

    @patch("services.search_service.get_cache", return_value=None)
    @patch("services.search_service.get_model_for_tier", return_value="gemini-2.5-flash-lite")
    @patch("services.search_service.generate_text")
    def test_rewrite_guard_skips_standalone_greeting(self, mock_generate, _mock_model, _mock_cache):
        question = "merhaba"
        history = [{"role": "user", "content": "onceki mesaj"}]

        settings.L3_PERF_REWRITE_GUARD_ENABLED = True
        rewritten = search_service.rewrite_query_with_history(question, history)
        self.assertEqual(rewritten, question)
        mock_generate.assert_not_called()

    @patch("services.search_service.get_cache", return_value=None)
    @patch("services.search_service.get_model_for_tier", return_value="gemini-2.5-flash-lite")
    @patch("services.search_service.generate_text")
    def test_rewrite_guard_skips_short_standalone_query(self, mock_generate, _mock_model, _mock_cache):
        question = "felsefe tarihi nedir"
        history = [{"role": "user", "content": "onceki mesaj"}]

        settings.L3_PERF_REWRITE_GUARD_ENABLED = True
        rewritten = search_service.rewrite_query_with_history(question, history)
        self.assertEqual(rewritten, question)
        mock_generate.assert_not_called()

    def test_context_budget_flag_controls_topk_and_chunk_chars(self):
        chunks = [_ctx_chunk(i) for i in range(1, 14)]

        settings.L3_PERF_CONTEXT_BUDGET_ENABLED = False
        context_default, used_default = build_epistemic_context(chunks, "QUOTE")
        self.assertEqual(len(used_default), 12)
        self.assertIn("x" * 650, context_default)

        settings.L3_PERF_CONTEXT_BUDGET_ENABLED = True
        settings.L3_PERF_CONTEXT_TOPK_STANDARD = 8
        settings.L3_PERF_CONTEXT_CHARS_STANDARD = 450
        context_budgeted, used_budgeted = build_epistemic_context(chunks, "QUOTE")
        self.assertEqual(len(used_budgeted), 8)
        self.assertIn("x" * 430, context_budgeted)
        self.assertNotIn("x" * 500, context_budgeted)

    def test_expansion_tail_fix_timeout_reason_and_no_tail_wait(self):
        settings.L3_PERF_EXPANSION_TAIL_FIX_ENABLED = True
        settings.SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS = 2
        settings.SEARCH_NOISE_GUARD_ENABLED = False

        orch = SearchOrchestrator(embedding_fn=lambda _: [0.1], cache=None)
        orch.expander = _SlowExpander()
        orch.strategies = [_FastExact(), _FastLemma(), _FastSemantic()]
        orch._log_search = lambda *args, **kwargs: None

        start = time.perf_counter()
        _, meta = orch.search(
            query="adalet",
            firebase_uid="u1",
            limit=10,
            intent="SYNTHESIS",
            result_mix_policy="lexical_then_semantic_tail",
            semantic_tail_cap=6,
        )
        elapsed = time.perf_counter() - start

        self.assertEqual(meta.get("expansion_skipped_reason"), "expansion_timeout")
        self.assertLess(elapsed, 3.2)

    @patch("services.search_service.get_model_for_tier", return_value="gemini-2.5-flash")
    @patch("services.search_service.generate_text")
    @patch("services.search_service.get_prompt_for_mode", return_value="prompt")
    @patch("services.search_service.build_epistemic_context")
    @patch("services.search_service.get_rag_context")
    @patch("services.search_service.is_analytic_word_count", return_value=False)
    def test_output_budget_flag_controls_generate_text_args(
        self,
        _mock_analytic,
        mock_get_ctx,
        mock_build_context,
        _mock_prompt,
        mock_generate,
        _mock_model,
    ):
        mock_get_ctx.return_value = {
            "chunks": [_ctx_chunk(1, text_len=300)],
            "mode": "QUOTE",
            "confidence": 0.8,
            "keywords": ["hayat"],
            "network_status": "IN_NETWORK",
            "level_counts": {"A": 1, "B": 0},
            "supplementary_search_skipped_reason": "sufficient_primary_evidence",
            "expansion_skipped_reason": "expansion_timeout",
            "metadata": {"search_log_id": None},
        }
        mock_build_context.return_value = ("ctx", [_ctx_chunk(1, text_len=300)])
        mock_generate.return_value = SimpleNamespace(
            text="ok",
            model_used="gemini-2.5-flash",
            model_tier="flash",
            provider_name="gemini",
            fallback_applied=False,
            secondary_fallback_applied=False,
            fallback_reason=None,
        )

        settings.L3_PERF_CONTEXT_BUDGET_ENABLED = True
        settings.L3_PERF_OUTPUT_BUDGET_ENABLED = False
        answer, _, meta = search_service.generate_answer("hayat nedir", "u1")
        self.assertEqual(answer, "ok")
        kwargs_default = mock_generate.call_args_list[0].kwargs
        self.assertIsNone(kwargs_default.get("max_output_tokens"))
        self.assertIsNone(kwargs_default.get("timeout_s"))
        self.assertFalse(meta.get("llm_generation_timeout_applied"))
        self.assertTrue(meta.get("context_budget_applied"))
        self.assertEqual(meta.get("supplementary_search_skipped_reason"), "sufficient_primary_evidence")
        self.assertEqual(meta.get("expansion_skipped_reason"), "expansion_timeout")

        mock_generate.reset_mock()
        settings.L3_PERF_OUTPUT_BUDGET_ENABLED = True
        settings.L3_PERF_MAX_OUTPUT_TOKENS_STANDARD = 650
        answer2, _, meta2 = search_service.generate_answer("hayat nedir", "u1")
        self.assertEqual(answer2, "ok")
        kwargs_budgeted = mock_generate.call_args_list[0].kwargs
        self.assertEqual(kwargs_budgeted.get("max_output_tokens"), 650)
        self.assertEqual(kwargs_budgeted.get("timeout_s"), 18.0)
        self.assertTrue(meta2.get("llm_generation_timeout_applied"))

    @patch("services.search_service.get_model_for_tier", return_value="gemini-2.5-flash")
    @patch("services.search_service.generate_text")
    @patch("services.search_service.get_prompt_for_mode", return_value="prompt")
    @patch("services.search_service.build_epistemic_context", return_value=("ctx", [_ctx_chunk(1, text_len=300)]))
    @patch("services.search_service.get_rag_context")
    @patch("services.search_service.is_analytic_word_count", return_value=False)
    @patch("services.search_service.get_graph_enriched_context")
    def test_graph_bridge_timeout_sets_metadata(
        self,
        mock_graph_bridge,
        _mock_analytic,
        mock_get_ctx,
        _mock_build_context,
        _mock_prompt,
        mock_generate,
        _mock_model,
    ):
        mock_get_ctx.return_value = {
            "chunks": [_ctx_chunk(1, text_len=300)],
            "mode": "SYNTHESIS",
            "confidence": 0.8,
            "keywords": ["hayat"],
            "network_status": "IN_NETWORK",
            "level_counts": {"A": 1, "B": 0},
            "metadata": {"search_log_id": None},
        }
        mock_generate.return_value = SimpleNamespace(
            text="ok",
            model_used="gemini-2.5-flash",
            model_tier="flash",
            provider_name="gemini",
            fallback_applied=False,
            secondary_fallback_applied=False,
            fallback_reason=None,
        )

        def _slow_bridge(_chunks, _uid):
            time.sleep(0.2)
            return "graph bridge"

        mock_graph_bridge.side_effect = _slow_bridge
        settings.SEARCH_GRAPH_BRIDGE_TIMEOUT_MS = 50

        answer, _, meta = search_service.generate_answer("hayat nedir", "u1")
        self.assertEqual(answer, "ok")
        self.assertFalse(meta.get("graph_bridge_used"))
        self.assertTrue(meta.get("graph_bridge_timeout_triggered"))
        self.assertGreaterEqual(meta.get("graph_bridge_latency_ms", 0.0), 50.0)


if __name__ == "__main__":
    unittest.main()
