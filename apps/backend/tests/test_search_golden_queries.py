import json
import unittest
from pathlib import Path

from services.search_system.semantic_router import SemanticRouter


class SearchGoldenQueryRoutingTests(unittest.TestCase):
    @staticmethod
    def _dataset_path() -> Path:
        candidates = [
            Path("apps/backend/data/search_golden_queries.json"),
            Path("data/search_golden_queries.json"),
        ]
        for path in candidates:
            if path.exists():
                return path
        raise AssertionError("search_golden_queries.json not found")

    @classmethod
    def setUpClass(cls):
        cls.router = SemanticRouter()
        cls.dataset = json.loads(cls._dataset_path().read_text(encoding="utf-8-sig"))

    def test_bundled_search_golden_queries_are_loadable(self):
        self.assertGreaterEqual(len(self.dataset), 10)
        modes = {case["expected_retrieval_mode"] for case in self.dataset}
        self.assertTrue({"fast_exact", "semantic_focus", "balanced"}.issubset(modes))
        for case in self.dataset:
            self.assertTrue(case["id"])
            self.assertTrue(case["question"])
            self.assertTrue(case["intent"])
            self.assertTrue(case["expected_buckets"])

    def test_router_matches_bundled_search_golden_queries(self):
        for case in self.dataset:
            with self.subTest(case_id=case["id"]):
                decision = self.router.route(case["question"], intent=case["intent"])
                self.assertEqual(decision.retrieval_mode, case["expected_retrieval_mode"])
                self.assertEqual(decision.selected_buckets, case["expected_buckets"])

    def test_router_is_accent_robust_for_ascii_variants(self):
        for case in self.dataset:
            ascii_variant = case.get("ascii_variant")
            if not ascii_variant:
                continue
            with self.subTest(case_id=case["id"]):
                original = self.router.route(case["question"], intent=case["intent"])
                ascii_decision = self.router.route(ascii_variant, intent=case["intent"])
                self.assertEqual(ascii_decision.retrieval_mode, original.retrieval_mode)
                self.assertEqual(ascii_decision.selected_buckets, original.selected_buckets)


if __name__ == "__main__":
    unittest.main()
