import unittest
from unittest.mock import patch

from services import ingestion_service


class _FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((str(sql), params))

    def var(self, _datatype):
        raise AssertionError("bookmark sync should not allocate RETURNING variables")


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class SyncPersonalNoteBookmarkTests(unittest.TestCase):
    @patch("services.ingestion_service._emit_change_event_best_effort")
    @patch("services.ingestion_service.maybe_trigger_epistemic_distribution_refresh_async")
    @patch("services.ingestion_service._invalidate_search_cache")
    @patch("services.ingestion_service.DataHealthService.validate_content", return_value=True)
    @patch("services.ingestion_service._delete_content_rows_for_item", return_value=2)
    @patch("services.ingestion_service._mirror_book_registry_rows")
    @patch("services.ingestion_service._ensure_serial_write_session")
    def test_bookmark_category_skips_reindex_after_cleanup(
        self,
        _mock_serial,
        _mock_registry,
        _mock_delete,
        _mock_validate,
        _mock_invalidate,
        _mock_epistemic,
        _mock_emit,
    ):
        fake_conn = _FakeConnection()

        with patch.object(ingestion_service.DatabaseManager, "get_write_connection", return_value=fake_conn):
            result = ingestion_service.sync_personal_note_for_item(
                firebase_uid="uid-1",
                book_id="note-1",
                title="Bookmark",
                author="Self",
                content="<p>saved link</p>",
                tags=["web"],
                category="BOOKMARK",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(fake_conn.commits, 1)
        self.assertFalse(any("INSERT INTO TOMEHUB_CONTENT_V2" in sql for sql, _ in fake_conn.cursor_obj.executed))


if __name__ == "__main__":
    unittest.main()
