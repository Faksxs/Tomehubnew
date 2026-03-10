import unittest

from services.flow_service import FlowService


class TestFlowPersonalNoteVisibility(unittest.TestCase):
    def test_personal_note_filter_requires_ideas_category(self):
        sql, params = FlowService._apply_personal_note_visibility_guard(
            "SELECT * FROM TOMEHUB_CONTENT_V2 t WHERE 1=1",
            {},
            "PERSONAL_NOTE",
        )

        self.assertIn("EXISTS", sql)
        self.assertIn("PERSONAL_NOTE_CATEGORY", sql)
        self.assertIn("= 'IDEAS'", sql)
        self.assertEqual(params, {})

    def test_non_personal_filters_exclude_private_daily_and_bookmark_notes(self):
        sql, params = FlowService._apply_personal_note_visibility_guard(
            "SELECT * FROM TOMEHUB_CONTENT_V2 t WHERE 1=1",
            {},
            "ALL_NOTES",
        )

        self.assertIn("NOT EXISTS", sql)
        self.assertIn("'PRIVATE'", sql)
        self.assertIn("'DAILY'", sql)
        self.assertIn("'BOOKMARK'", sql)
        self.assertEqual(params, {})


if __name__ == "__main__":
    unittest.main()
