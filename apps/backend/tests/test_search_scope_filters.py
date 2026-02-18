import unittest

from services.search_system.strategies import (
    _apply_book_id_filter,
    _apply_resource_type_filter,
    _should_exclude_pdf_in_first_pass,
)


class TestSearchScopeFilters(unittest.TestCase):
    def test_book_resource_type_maps_to_in_clause(self):
        sql, params = _apply_resource_type_filter("SELECT * FROM TOMEHUB_CONTENT WHERE 1=1", {}, "BOOK")
        self.assertIn("source_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT', 'NOTES')", sql)
        self.assertEqual(params, {})

    def test_all_notes_resource_type_maps_to_note_types(self):
        sql, params = _apply_resource_type_filter("SELECT * FROM TOMEHUB_CONTENT WHERE 1=1", {}, "ALL_NOTES")
        self.assertIn("source_type IN ('HIGHLIGHT', 'INSIGHT', 'NOTES')", sql)
        self.assertEqual(params, {})

    def test_book_id_filter_is_applied(self):
        sql, params = _apply_book_id_filter("SELECT * FROM TOMEHUB_CONTENT WHERE 1=1", {}, "book-123")
        self.assertIn("book_id = :p_book_id", sql)
        self.assertEqual(params.get("p_book_id"), "book-123")

    def test_pdf_exclusion_rules(self):
        self.assertFalse(_should_exclude_pdf_in_first_pass("BOOK", None))
        self.assertFalse(_should_exclude_pdf_in_first_pass(None, "book-123"))
        self.assertTrue(_should_exclude_pdf_in_first_pass(None, None))


if __name__ == "__main__":
    unittest.main()
