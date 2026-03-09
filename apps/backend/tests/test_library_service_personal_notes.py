import unittest
from unittest.mock import patch

from services import library_service


class _FakeCursor:
    def __init__(self, result_sets):
        self._result_sets = list(result_sets)
        self._active = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _sql, _binds=None):
        self._active = self._result_sets.pop(0) if self._result_sets else []

    def fetchall(self):
        return list(self._active)


class _FakeConnection:
    def __init__(self, result_sets):
        self._cursor = _FakeCursor(result_sets)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


class LibraryServicePersonalNotesTests(unittest.TestCase):
    @patch("services.library_service.resolve_active_content_table", return_value="TOMEHUB_CONTENT_V2")
    @patch(
        "services.library_service._content_table_shape",
        return_value={
            "item_col": "ITEM_ID",
            "type_col": "CONTENT_TYPE",
            "title_col": "TITLE",
            "content_col": "CONTENT_CHUNK",
            "comment_col": "COMMENT_TEXT",
            "tags_col": "TAGS_JSON",
            "page_col": "PAGE_NUMBER",
            "chunk_idx_col": "CHUNK_INDEX",
            "id_col": "ID",
            "created_at_col": "CREATED_AT",
        },
    )
    @patch("services.library_service._table_exists", return_value=False)
    @patch(
        "services.library_service._library_cols",
        return_value={
            "ITEM_ID",
            "ITEM_TYPE",
            "TITLE",
            "AUTHOR",
            "TRANSLATOR",
            "PUBLISHER",
            "PUBLICATION_YEAR",
            "ISBN",
            "URL",
            "STATUS",
            "READING_STATUS",
            "TAGS_JSON",
            "SUMMARY_TEXT",
            "CONTENT_LANGUAGE_MODE",
            "CONTENT_LANGUAGE_RESOLVED",
            "SOURCE_LANGUAGE_HINT",
            "LANGUAGE_DECISION_REASON",
            "LANGUAGE_DECISION_CONFIDENCE",
            "PERSONAL_NOTE_CATEGORY",
            "PERSONAL_FOLDER_ID",
            "FOLDER_PATH",
            "COVER_URL",
            "CAST_TOP",
            "ADDED_AT",
            "IS_FAVORITE",
            "PAGE_COUNT",
            "UPDATED_AT",
            "RATING",
            "ORIGINAL_TITLE",
        },
    )
    @patch("services.library_service.safe_read_clob", side_effect=lambda value: value)
    def test_ideas_notes_load_body_from_insight_rows(
        self,
        _mock_safe_read_clob,
        _mock_library_cols,
        _mock_table_exists,
        _mock_content_shape,
        _mock_content_table,
    ):
        library_row = (
            "note-1",
            "PERSONAL_NOTE",
            "Deneme",
            "Self",
            None,
            None,
            None,
            None,
            None,
            "On Shelf",
            "Finished",
            "[]",
            "",
            "AUTO",
            None,
            None,
            None,
            None,
            "IDEAS",
            None,
            None,
            None,
            "[]",
            1700000000000,
            0,
            None,
            1700000000000,
            None,
            None,
        )
        content_row = (
            "note-1",
            501,
            "INSIGHT",
            "<p>nbos gozukmek</p>",
            1,
            0,
            None,
            None,
            1700000000000,
        )
        fake_conn = _FakeConnection([[library_row], [content_row]])

        with patch.object(library_service.DatabaseManager, "get_read_connection", return_value=fake_conn):
            result = library_service.list_library_items("uid-1", limit=10, include_media=False)

        self.assertEqual(len(result["items"]), 1)
        note = result["items"][0]
        self.assertEqual(note["type"], "PERSONAL_NOTE")
        self.assertEqual(note["personalNoteCategory"], "IDEAS")
        self.assertEqual(note["generalNotes"], "<p>nbos gozukmek</p>")
        self.assertEqual(note["highlights"], [])


if __name__ == "__main__":
    unittest.main()
