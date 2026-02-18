import unittest
from unittest.mock import MagicMock, patch

from services.analytics_service import resolve_multiple_book_ids_from_question
from services.epistemic_service import build_epistemic_context


class TestCompareResolutionAndContext(unittest.TestCase):
    @patch("services.analytics_service.DatabaseManager.get_read_connection")
    def test_resolve_multiple_book_ids_handles_highlight_suffix_titles(self, mock_get_conn):
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [
                ("Ahlak felsefesi (Highlight)", "book_1"),
                ("Mahur beste (Highlight)", "book_2"),
            ],
            [],
        ]

        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_get_conn.return_value.__enter__.return_value = conn

        result = resolve_multiple_book_ids_from_question(
            "test_user_001",
            "ahlak felsefesi ve mahur beste kitaplarindaki adalet kavramini karsilastir",
        )

        self.assertEqual(result, ["book_1", "book_2"])

    def test_compare_context_selection_keeps_each_target_book(self):
        chunks = []
        for i in range(10):
            chunks.append(
                {
                    "id": f"a{i}",
                    "book_id": "book_a",
                    "title": "Book A",
                    "content_chunk": f"a-content-{i}",
                    "answerability_score": 10 - i,
                    "_compare_target": True,
                    "_compare_book_id": "book_a",
                    "epistemic_level": "A",
                }
            )
        for i in range(2):
            chunks.append(
                {
                    "id": f"b{i}",
                    "book_id": "book_b",
                    "title": "Book B",
                    "content_chunk": f"b-content-{i}",
                    "answerability_score": 1 - (i * 0.1),
                    "_compare_target": True,
                    "_compare_book_id": "book_b",
                    "epistemic_level": "B",
                }
            )

        _, used_chunks = build_epistemic_context(chunks, "EXPLORER")
        used_book_ids = {str(c.get("book_id")) for c in used_chunks}

        self.assertIn("book_a", used_book_ids)
        self.assertIn("book_b", used_book_ids)


if __name__ == "__main__":
    unittest.main()

