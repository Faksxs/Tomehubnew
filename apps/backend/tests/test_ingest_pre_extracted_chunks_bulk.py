import array
import unittest
from unittest.mock import patch

from services import ingestion_service


class _FakeCursor:
    def __init__(self):
        self.execute_calls = []
        self.executemany_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.execute_calls.append((str(sql), params))

    def executemany(self, sql, params, batcherrors=False, arraydmlrowcounts=False):
        self.executemany_calls.append(
            {
                "sql": str(sql),
                "params": list(params),
                "batcherrors": batcherrors,
                "arraydmlrowcounts": arraydmlrowcounts,
            }
        )

    def getbatcherrors(self):
        return []

    def getarraydmlrowcounts(self):
        if not self.executemany_calls:
            return []
        return [1] * len(self.executemany_calls[-1]["params"])

    def var(self, _datatype):
        raise AssertionError("bulk pre-extracted ingest should not allocate RETURNING variables")


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class IngestPreExtractedChunksBulkTests(unittest.TestCase):
    @patch("services.ingestion_service._emit_change_event_best_effort")
    @patch("services.ingestion_service.maybe_trigger_epistemic_distribution_refresh_async")
    @patch("services.ingestion_service._invalidate_search_cache")
    @patch("services.ingestion_service._mirror_book_registry_rows")
    @patch("services.ingestion_service.check_book_exists", return_value=False)
    @patch("services.ingestion_service.acquire_lock")
    @patch("services.ingestion_service.batch_get_embeddings")
    @patch("services.ingestion_service.classify_passage_fast", return_value={"type": "BODY"})
    @patch("services.ingestion_service.get_lemma_frequencies", return_value={"metin": 1})
    @patch("services.ingestion_service.get_lemmas", return_value=["metin"])
    @patch("services.ingestion_service.normalize_text", side_effect=lambda text: text.lower())
    @patch("services.ingestion_service.should_skip_for_ingestion", return_value=(False, {}))
    @patch("services.ingestion_service.DataCleanerService.assess_noise", return_value={"score": 0, "signals": {}})
    @patch("services.ingestion_service.DataCleanerService.strip_basic_patterns", side_effect=lambda text: text)
    @patch("services.ingestion_service.corrector_service.fix_text", side_effect=lambda text: text)
    @patch("services.ingestion_service.DataHealthService.validate_content", return_value=True)
    def test_uses_executemany_for_pre_extracted_chunk_batch(
        self,
        _mock_validate,
        _mock_fix_text,
        _mock_strip_patterns,
        _mock_assess_noise,
        _mock_skip_audit,
        _mock_normalize,
        _mock_lemmas,
        _mock_lemma_freqs,
        _mock_classify,
        mock_embeddings,
        _mock_lock,
        _mock_exists,
        _mock_registry,
        _mock_invalidate,
        _mock_epistemic,
        _mock_emit,
    ):
        fake_conn = _FakeConnection()
        mock_embeddings.return_value = [
            array.array("f", [0.1, 0.2]),
            array.array("f", [0.3, 0.4]),
        ]
        chunks = [
            {"text": "Ilk chunk metni", "page_num": 1},
            {"text": "Ikinci chunk metni", "page_num": 2},
        ]

        with patch.object(ingestion_service.DatabaseManager, "get_write_connection", return_value=fake_conn):
            result = ingestion_service.ingest_pre_extracted_chunks(
                chunks=chunks,
                title="Kitap",
                author="Yazar",
                firebase_uid="uid-1",
                book_id="book-1",
                source_type="PDF",
            )

        self.assertTrue(result)
        self.assertEqual(fake_conn.commits, 1)
        self.assertEqual(fake_conn.rollbacks, 0)
        self.assertEqual(len(fake_conn.cursor_obj.executemany_calls), 1)
        call = fake_conn.cursor_obj.executemany_calls[0]
        self.assertIn("INSERT INTO TOMEHUB_CONTENT_V2", call["sql"])
        self.assertEqual(len(call["params"]), 2)
        self.assertTrue(call["batcherrors"])
        self.assertTrue(call["arraydmlrowcounts"])
        self.assertFalse(any("INSERT INTO TOMEHUB_CONTENT_V2" in sql for sql, _ in fake_conn.cursor_obj.execute_calls))


if __name__ == "__main__":
    unittest.main()
