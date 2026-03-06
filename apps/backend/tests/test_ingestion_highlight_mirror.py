import unittest
from unittest.mock import patch

from services import ingestion_service


class _CursorContext:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, exc_type, exc, tb):
        return False


class _ConnectionContext:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = 0

    def cursor(self):
        return _CursorContext(self._cursor)

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class HighlightMirrorTests(unittest.TestCase):
    def test_exact_matches_are_mirrored_best_effort(self):
        source_conn = _ConnectionContext(object())
        mirror_conn_1 = _ConnectionContext(object())
        mirror_conn_2 = _ConnectionContext(object())

        with patch("services.ingestion_service.DatabaseManager.get_write_connection", side_effect=[source_conn, mirror_conn_1, mirror_conn_2]):
            with patch("services.ingestion_service._ensure_serial_write_session"):
                with patch("services.ingestion_service._mirror_book_registry_rows"):
                    with patch(
                        "services.ingestion_service._resolve_exact_highlight_mirror_targets",
                        return_value=("Same Title", "Same Author", ["book-2", "book-3"]),
                    ):
                        with patch(
                            "services.ingestion_service._replace_highlight_rows_for_item",
                            side_effect=[
                                (2, 1, [0.11]),  # source
                                (1, 1, [0.11]),  # mirror-1
                                (1, 1, [0.11]),  # mirror-2
                            ],
                        ) as replace_patch:
                            with patch("services.ingestion_service._invalidate_search_cache") as invalidate_patch:
                                with patch("services.ingestion_service.maybe_trigger_epistemic_distribution_refresh_async"):
                                    with patch("services.ingestion_service._emit_change_event_best_effort"):
                                        result = ingestion_service.sync_highlights_for_item(
                                            firebase_uid="u1",
                                            book_id="book-1",
                                            title="Same Title",
                                            author="Same Author",
                                            highlights=[{"text": "alpha", "type": "highlight"}],
                                        )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["mirrored_attempted"], 2)
        self.assertEqual(result["mirrored_succeeded"], 2)
        self.assertEqual(result["mirrored_failed"], [])

        self.assertEqual(replace_patch.call_count, 3)
        source_call = replace_patch.call_args_list[0].kwargs
        mirror_call_1 = replace_patch.call_args_list[1].kwargs
        mirror_call_2 = replace_patch.call_args_list[2].kwargs
        self.assertEqual(source_call["book_id"], "book-1")
        self.assertEqual(mirror_call_1["book_id"], "book-2")
        self.assertEqual(mirror_call_2["book_id"], "book-3")
        self.assertEqual(mirror_call_1["precomputed_embeddings"], [0.11])
        self.assertEqual(mirror_call_2["precomputed_embeddings"], [0.11])

        invalidated_book_ids = [c.kwargs["book_id"] for c in invalidate_patch.call_args_list]
        self.assertEqual(invalidated_book_ids, ["book-1", "book-2", "book-3"])

    def test_mirror_failures_do_not_fail_source_sync(self):
        source_conn = _ConnectionContext(object())
        mirror_conn_1 = _ConnectionContext(object())
        mirror_conn_2 = _ConnectionContext(object())

        with patch("services.ingestion_service.DatabaseManager.get_write_connection", side_effect=[source_conn, mirror_conn_1, mirror_conn_2]):
            with patch("services.ingestion_service._ensure_serial_write_session"):
                with patch("services.ingestion_service._mirror_book_registry_rows"):
                    with patch(
                        "services.ingestion_service._resolve_exact_highlight_mirror_targets",
                        return_value=("Same Title", "Same Author", ["book-2", "book-3"]),
                    ):
                        with patch(
                            "services.ingestion_service._replace_highlight_rows_for_item",
                            side_effect=[
                                (3, 2, [0.22]),  # source
                                RuntimeError("mirror failed"),
                                (1, 2, [0.22]),
                            ],
                        ):
                            with patch("services.ingestion_service._invalidate_search_cache"):
                                with patch("services.ingestion_service.maybe_trigger_epistemic_distribution_refresh_async"):
                                    with patch("services.ingestion_service._emit_change_event_best_effort"):
                                        result = ingestion_service.sync_highlights_for_item(
                                            firebase_uid="u1",
                                            book_id="book-1",
                                            title="Same Title",
                                            author="Same Author",
                                            highlights=[{"text": "alpha", "type": "highlight"}],
                                        )

        self.assertTrue(result["success"])
        self.assertEqual(result["deleted"], 3)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(result["mirrored_attempted"], 2)
        self.assertEqual(result["mirrored_succeeded"], 1)
        self.assertEqual(result["mirrored_failed"], ["book-2"])


if __name__ == "__main__":
    unittest.main()
