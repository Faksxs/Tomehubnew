import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from services import dual_ai_orchestrator, judge_ai_service


class JudgeAIServiceTests(unittest.TestCase):
    def test_find_chunk_by_title_matches_near_normalized_titles(self):
        target_chunk = {"title": "Stoacılık & Erdem", "content_chunk": "x"}
        chunks = [
            {"title": "Başka Kaynak", "content_chunk": "y"},
            target_chunk,
        ]

        match = judge_ai_service.find_chunk_by_title(chunks, "Stoacilik ve Erdemler")

        self.assertIs(match, target_chunk)

    def test_evaluate_answer_records_metric_with_network_status(self):
        chunks = [{"title": "Kaynak", "content_chunk": "icerik", "answerability_score": 0.8}]
        labels_observer = Mock()

        with patch.object(judge_ai_service, "get_rubric_for_question", return_value={}), patch.object(
            judge_ai_service, "verify_source_accuracy", return_value=(1.0, [])
        ), patch.object(
            judge_ai_service, "verify_relevance", return_value=(0.9, [])
        ), patch.object(
            judge_ai_service, "verify_ocr_quality", return_value=(1.0, [])
        ), patch.object(
            judge_ai_service, "verify_format", return_value=(1.0, [])
        ), patch.object(
            judge_ai_service, "verify_synthesis_depth", return_value=(0.8, [])
        ), patch.object(
            judge_ai_service, "calculate_overall_score", return_value=0.91
        ), patch.object(
            judge_ai_service, "get_verdict", return_value="PASS"
        ), patch.object(
            judge_ai_service, "identify_failures", return_value=[]
        ), patch.object(
            judge_ai_service, "generate_hints_from_failures", return_value=[]
        ), patch.object(
            judge_ai_service, "JUDGE_SCORE"
        ) as mock_metric:
            mock_metric.labels.return_value = labels_observer

            result = asyncio.run(
                judge_ai_service.evaluate_answer(
                    question="Soru",
                    answer="Yanıt [Kaynak: Kaynak]",
                    chunks=chunks,
                    answer_mode="SYNTHESIS",
                    intent="DIRECT",
                    network_status="hybrid",
                )
            )

        mock_metric.labels.assert_called_once_with(
            intent="DIRECT",
            network_status="HYBRID",
            verdict="PASS",
        )
        labels_observer.observe.assert_called_once_with(0.91)
        self.assertEqual(result["verdict"], "PASS")


class DualAIOrchestratorTests(unittest.TestCase):
    def test_generate_evaluated_answer_passes_network_status_to_judge(self):
        work_result = {"answer": "Yanıt", "metadata": {}}
        eval_result = {
            "verdict": "PASS",
            "overall_score": 0.93,
            "criterion_scores": {},
            "failures": [],
            "hints_for_retry": [],
        }

        with patch("services.cache_service.get_cache", return_value=None), patch.object(
            dual_ai_orchestrator, "classify_question_intent", return_value=("SYNTHESIS", "LOW")
        ), patch.object(
            dual_ai_orchestrator, "should_trigger_audit", return_value=(True, "Audit")
        ), patch.object(
            dual_ai_orchestrator, "generate_work_ai_answer", new=AsyncMock(return_value=work_result)
        ), patch.object(
            dual_ai_orchestrator, "evaluate_answer", new=AsyncMock(return_value=eval_result)
        ) as mock_evaluate:
            result = asyncio.run(
                dual_ai_orchestrator.generate_evaluated_answer(
                    question="Soru",
                    chunks=[{"content_chunk": "icerik"}],
                    answer_mode="SYNTHESIS",
                    confidence_score=3.0,
                    network_status="HYBRID",
                )
            )

        self.assertEqual(mock_evaluate.await_args.kwargs["network_status"], "HYBRID")
        self.assertEqual(result["metadata"]["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
