import unittest
from pathlib import Path

from rag_eval.dataset import load_golden_cases


class RAGEvalDatasetTests(unittest.TestCase):
    def test_bundled_golden_datasets_are_loadable(self):
        dataset_paths = [
            Path("apps/backend/data/golden_dataset.json"),
            Path("apps/backend/data/golden_test_set.json"),
            Path("data/golden_dataset.json"),
            Path("data/golden_test_set.json"),
        ]
        loaded = 0
        for path in dataset_paths:
            if not path.exists():
                continue
            cases = load_golden_cases(path)
            self.assertTrue(cases, f"Expected at least one case in {path}")
            if path.name == "golden_dataset.json":
                self.assertGreaterEqual(len(cases), 20)
            for case in cases:
                self.assertTrue(case.case_id)
                self.assertTrue(case.question)
            loaded += 1
        self.assertGreaterEqual(loaded, 2)


if __name__ == "__main__":
    unittest.main()
