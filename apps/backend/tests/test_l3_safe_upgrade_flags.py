import unittest
from types import SimpleNamespace
from unittest.mock import patch

from config import settings
from services import search_service
from services.dual_ai_orchestrator import should_trigger_audit
from services.work_ai_service import generate_work_ai_answer


class TestL3SafeUpgradeFlags(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "L3_QUOTE_DYNAMIC_COUNT_ENABLED": settings.L3_QUOTE_DYNAMIC_COUNT_ENABLED,
            "L3_QUOTE_DYNAMIC_MIN": settings.L3_QUOTE_DYNAMIC_MIN,
            "L3_QUOTE_DYNAMIC_MAX": settings.L3_QUOTE_DYNAMIC_MAX,
            "L3_JUDGE_DIVERSITY_AUDIT_ENABLED": settings.L3_JUDGE_DIVERSITY_AUDIT_ENABLED,
            "L3_JUDGE_DIVERSITY_THRESHOLD": settings.L3_JUDGE_DIVERSITY_THRESHOLD,
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_quote_target_count_dynamic_2_to_5(self):
        settings.L3_QUOTE_DYNAMIC_COUNT_ENABLED = True
        settings.L3_QUOTE_DYNAMIC_MIN = 2
        settings.L3_QUOTE_DYNAMIC_MAX = 5

        self.assertEqual(search_service._compute_quote_target_count(3.1, 10), 2)
        self.assertEqual(search_service._compute_quote_target_count(4.2, 10), 4)
        self.assertEqual(search_service._compute_quote_target_count(4.8, 10), 5)
        self.assertEqual(search_service._compute_quote_target_count(4.8, 3), 3)

    def test_judge_diversity_trigger(self):
        settings.L3_JUDGE_DIVERSITY_AUDIT_ENABLED = True
        settings.L3_JUDGE_DIVERSITY_THRESHOLD = 2

        should_audit, reason = should_trigger_audit(
            confidence=4.8,
            intent="DIRECT",
            network_status="IN_NETWORK",
            source_diversity_count=1,
        )
        self.assertTrue(should_audit)
        self.assertEqual(reason, "Low Source Diversity")

        should_audit_2, reason_2 = should_trigger_audit(
            confidence=4.8,
            intent="DIRECT",
            network_status="IN_NETWORK",
            source_diversity_count=3,
        )
        self.assertFalse(should_audit_2)
        self.assertEqual(reason_2, "High Confidence Direct Answer")


class TestExplorerGraphBridgeAttempt(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = {
            "SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT": settings.SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT,
            "SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS": settings.SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS,
            "LLM_EXPLORER_QWEN_PILOT_ENABLED": settings.LLM_EXPLORER_QWEN_PILOT_ENABLED,
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    @patch("services.search_service.get_graph_enriched_context", return_value="bridge context")
    @patch("services.work_ai_service.generate_text")
    @patch("services.work_ai_service.build_epistemic_context", return_value=("base ctx", [{"id": 1}]))
    async def test_explorer_always_attempt_graph_bridge(
        self,
        _mock_build_ctx,
        mock_generate_text,
        _mock_bridge,
    ):
        settings.SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT = True
        settings.SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS = 900
        settings.LLM_EXPLORER_QWEN_PILOT_ENABLED = False

        mock_generate_text.return_value = SimpleNamespace(
            text="answer",
            model_used="gemini-2.5-flash",
            model_tier="flash",
            provider_name="gemini",
            fallback_applied=False,
            secondary_fallback_applied=False,
            fallback_reason=None,
        )

        result = await generate_work_ai_answer(
            question="Soru",
            chunks=[{"id": 1, "content_chunk": "x"}],
            answer_mode="EXPLORER",
            confidence_score=4.5,
        )

        self.assertEqual(result["answer"], "answer")
        self.assertTrue(result["metadata"].get("graph_bridge_attempted"))


if __name__ == "__main__":
    unittest.main()
