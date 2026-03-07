import tempfile
import unittest
from pathlib import Path

from rag_eval.dataset import load_golden_cases
from rag_eval.judge import JudgeGrade, parse_judge_grade
from rag_eval.runner import (
    classify_case_result,
    evaluate_case_rules,
    render_markdown_report,
    run_eval_suite,
)


class _FakeJudge:
    def __init__(self, grades):
        self._grades = grades

    def evaluate(self, case, answer, sources, meta):
        return self._grades[case.case_id]


class RAGEvalRunnerTests(unittest.TestCase):
    def test_load_golden_cases_supports_list_and_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            list_path = tmp / "list.json"
            list_path.write_text(
                '[{"id":"q1","question":"What is X?","reference_answer":"X is Y"}]',
                encoding="utf-8",
            )
            mapping_path = tmp / "mapping.json"
            mapping_path.write_text(
                '{"case_a":{"query":"What is A?","must_quote":["A"],"expected_mode":"HYBRID"}}',
                encoding="utf-8",
            )

            list_cases = load_golden_cases(list_path)
            mapping_cases = load_golden_cases(mapping_path)

        self.assertEqual(list_cases[0].case_id, "q1")
        self.assertEqual(mapping_cases[0].case_id, "case_a")
        self.assertEqual(mapping_cases[0].question, "What is A?")
        self.assertEqual(mapping_cases[0].must_quote, ["A"])

    def test_parse_judge_grade_handles_invalid_json(self):
        grade = parse_judge_grade("not-json")
        self.assertEqual(grade.score, 0)
        self.assertEqual(grade.faithfulness, "Unknown")
        self.assertIn("not valid JSON", grade.reasoning)

    def test_classify_case_result_marks_retrieval_failure_without_sources(self):
        grade = JudgeGrade(score=2, reasoning="No evidence", faithfulness="Unknown")
        classification, evidence_gaps, passed = classify_case_result(
            answer="No idea",
            sources=[],
            meta={"status": "failed"},
            grade=grade,
            rule_failures=[],
        )
        self.assertEqual(classification, "retrieval")
        self.assertIn("no_sources", evidence_gaps)
        self.assertFalse(passed)

    def test_classify_case_result_marks_generation_failure_when_sources_exist(self):
        grade = JudgeGrade(score=2, reasoning="Used evidence poorly", faithfulness="Low")
        classification, evidence_gaps, passed = classify_case_result(
            answer="Wrong synthesis",
            sources=[{"title": "Book", "content": "evidence"}],
            meta={"status": "healthy", "vector_candidates_count": 3, "source_diversity_count": 1},
            grade=grade,
            rule_failures=[],
        )
        self.assertEqual(classification, "generation")
        self.assertIn("low_faithfulness", evidence_gaps)
        self.assertFalse(passed)

    def test_evaluate_case_rules_detects_mode_and_required_phrase_failures(self):
        cases = load_golden_cases(
            Path("apps/backend/data/golden_dataset.json")
            if Path("apps/backend/data/golden_dataset.json").exists()
            else Path("data/golden_dataset.json")
        )
        vicdan_case = next(case for case in cases if case.case_id == "q10")
        failures, actual_mode = evaluate_case_rules(
            vicdan_case,
            "## Karşıt Görüşler\nEksik cevap\n\n## Bağlamsal Kanıtlar\nGenel ifade\n\n## Sonuç\nKısa sonuç",
        )
        self.assertEqual(actual_mode, "HYBRID")
        self.assertTrue(any(item.startswith("missing_required_phrase:") for item in failures))

    def test_run_eval_suite_builds_summary_and_report(self):
        cases = load_golden_cases(
            Path("apps/backend/data/golden_dataset.json")
            if Path("apps/backend/data/golden_dataset.json").exists()
            else Path("data/golden_dataset.json")
        )[:2]

        answers = {
            cases[0].case_id: (
                "## Doğrudan Tanımlar\nTüccarların ibadeti karşılık beklentisiyle yapılan ibadettir.\n\n## Bağlamsal Analiz\nBu cevap ödül ve çıkar beklentisini açıklar.\n\n## Sonuç\nKarşılık beklentisi temeldir.",
                [{"title": "Book A", "content": "evidence", "page_number": 1}],
                {"status": "healthy", "vector_candidates_count": 2, "source_diversity_count": 1},
            ),
            cases[1].case_id: (
                "## Doğrudan Tanımlar\nZayıf cevap\n\n## Bağlamsal Analiz\nEksik.\n\n## Sonuç\nYetersiz.",
                [{"title": "Book B", "content": "evidence", "page_number": 2}],
                {"status": "healthy", "vector_candidates_count": 2, "source_diversity_count": 1},
            ),
        }
        judge = _FakeJudge(
            {
                cases[0].case_id: JudgeGrade(score=5, reasoning="Good", faithfulness="High"),
                cases[1].case_id: JudgeGrade(score=2, reasoning="Bad", faithfulness="Low"),
            }
        )

        def _answer_fn(case, firebase_uid):
            return answers[case.case_id]

        results, summary = run_eval_suite(cases, "u1", judge, answer_fn=_answer_fn)
        report = render_markdown_report(results, summary, dataset_name="golden_dataset")

        self.assertEqual(summary.total_cases, 2)
        self.assertEqual(summary.passed_cases, 1)
        self.assertAlmostEqual(summary.pass_rate, 0.5)
        self.assertIn("generation", summary.classifications)
        self.assertIn("| ID | Score | Faithfulness | Mode | Class | Sources | Notes |", report)


if __name__ == "__main__":
    unittest.main()
