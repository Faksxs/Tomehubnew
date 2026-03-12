import unittest
from unittest.mock import patch

from services.pdf_async_ingestion_service import AsyncPdfIngestionManager


class AsyncPdfIngestionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_recover_stale_parse_jobs_requeues_recoverable_rows(self):
        manager = AsyncPdfIngestionManager()
        recovered_calls = []

        with patch("services.pdf_async_ingestion_service.list_stale_parse_jobs", return_value=[
            {
                "book_id": "book-1",
                "firebase_uid": "uid-1",
                "bucket_name": "bucket",
                "object_key": "object.pdf",
                "file_name": "source.pdf",
            }
        ]):
            with patch("services.pdf_async_ingestion_service._resolve_book_metadata", return_value={"title": "Kitap", "author": "Yazar"}):
                with patch("services.pdf_async_ingestion_service.upsert_ingestion_status") as upsert_mock:
                    with patch.object(manager, "_ensure_processing_task", side_effect=lambda **kwargs: recovered_calls.append(kwargs)):
                        await manager.recover_stale_parse_jobs_once()

        self.assertEqual(len(recovered_calls), 1)
        self.assertEqual(recovered_calls[0]["book_id"], "book-1")
        self.assertEqual(recovered_calls[0]["title"], "Kitap")
        upsert_mock.assert_called_once()
        _, kwargs = upsert_mock.call_args
        self.assertEqual(kwargs["parse_status"], "QUEUED")

    async def test_recover_stale_parse_jobs_marks_missing_storage_as_failed(self):
        manager = AsyncPdfIngestionManager()

        with patch("services.pdf_async_ingestion_service.list_stale_parse_jobs", return_value=[
            {
                "book_id": "book-2",
                "firebase_uid": "uid-2",
                "bucket_name": "",
                "object_key": "",
                "file_name": "missing.pdf",
            }
        ]):
            with patch("services.pdf_async_ingestion_service._resolve_book_metadata", return_value={"title": "", "author": ""}):
                with patch("services.pdf_async_ingestion_service.upsert_ingestion_status") as upsert_mock:
                    with patch.object(manager, "_ensure_processing_task") as ensure_mock:
                        await manager.recover_stale_parse_jobs_once()

        ensure_mock.assert_not_called()
        upsert_mock.assert_called_once()
        _, kwargs = upsert_mock.call_args
        self.assertEqual(kwargs["status"], "FAILED")
        self.assertEqual(kwargs["parse_status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
