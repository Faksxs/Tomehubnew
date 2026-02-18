import unittest

from services.query_plan_service import (
    PLAN_COMPARE,
    PLAN_SYNTHESIS,
    build_query_plan,
)


class QueryPlanServiceTests(unittest.TestCase):
    def test_compare_plan_with_auto_resolved_targets(self):
        plan = build_query_plan(
            question="ahlak felsefesi ve mahur beste kitaplarini karsilastir",
            intent="COMPARATIVE",
            is_analytic=False,
            compare_mode="EXPLICIT_ONLY",
            target_book_ids=[],
            context_book_id=None,
            auto_resolved_compare_book_ids=["b1", "b2"],
        )
        self.assertEqual(plan.plan_type, PLAN_COMPARE)
        self.assertTrue(plan.compare_requested)
        self.assertEqual(plan.scope_override, "GLOBAL")
        self.assertEqual(plan.target_book_ids, ["b1", "b2"])

    def test_notes_vs_book_compare_plan(self):
        plan = build_query_plan(
            question="notlarimdaki adaleti bu kitaptaki adaletle karsilastir",
            intent="SYNTHESIS",
            is_analytic=False,
            compare_mode="EXPLICIT_ONLY",
            target_book_ids=[],
            context_book_id="b1",
            auto_resolved_compare_book_ids=[],
        )
        self.assertEqual(plan.plan_type, PLAN_COMPARE)
        self.assertTrue(plan.notes_vs_book_compare_requested)
        self.assertEqual(plan.scope_override, "GLOBAL")

    def test_non_compare_synthesis_plan(self):
        plan = build_query_plan(
            question="bu kavrami analiz et ve sentezle",
            intent="SYNTHESIS",
            is_analytic=False,
            compare_mode="EXPLICIT_ONLY",
            target_book_ids=[],
            context_book_id=None,
            auto_resolved_compare_book_ids=[],
        )
        self.assertEqual(plan.plan_type, PLAN_SYNTHESIS)
        self.assertFalse(plan.compare_requested)

    def test_single_target_produces_degrade_reason(self):
        plan = build_query_plan(
            question="karsilastir",
            intent="COMPARATIVE",
            is_analytic=False,
            compare_mode="EXPLICIT_ONLY",
            target_book_ids=["b1"],
            context_book_id=None,
            auto_resolved_compare_book_ids=[],
        )
        self.assertEqual(plan.degrade_reason, "insufficient_target_books")
        self.assertFalse(plan.compare_requested)


if __name__ == "__main__":
    unittest.main()
