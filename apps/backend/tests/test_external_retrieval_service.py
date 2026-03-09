import unittest
from unittest.mock import patch

from models.external_api_models import ExternalSearchRequest
from services.external_retrieval_service import run_external_search


class ExternalRetrievalServiceTests(unittest.TestCase):
    @patch("services.external_retrieval_service.get_rag_context")
    def test_shapes_results_for_external_consumers(self, mock_get_rag_context):
        mock_get_rag_context.return_value = {
            "chunks": [
                {
                    "id": 42,
                    "book_id": "book-1",
                    "title": "Deep Work",
                    "content_chunk": "A" * 1600,
                    "page_number": 12,
                    "source_type": "HIGHLIGHT",
                    "score": 91.5,
                    "tags": '["focus", "attention"]',
                    "summary": "summary text",
                    "comment": "comment text",
                }
            ],
            "mode": "STANDARD",
            "intent": "SYNTHESIS",
            "confidence": 0.82,
            "search_log_id": 77,
            "retrieval_path": "vector_only",
        }

        payload = ExternalSearchRequest(query="focus")
        result = run_external_search(payload, "uid-1")

        self.assertEqual(result["metadata"]["result_count"], 1)
        self.assertEqual(result["results"][0]["chunk_id"], 42)
        self.assertEqual(result["results"][0]["item_id"], "book-1")
        self.assertEqual(result["results"][0]["source_type"], "HIGHLIGHT")
        self.assertEqual(result["results"][0]["tags"], ["focus", "attention"])
        self.assertTrue(result["results"][0]["snippet"].endswith("..."))

    @patch("services.external_retrieval_service.get_rag_context")
    def test_returns_empty_payload_when_no_context_found(self, mock_get_rag_context):
        mock_get_rag_context.return_value = None

        payload = ExternalSearchRequest(query="missing")
        result = run_external_search(payload, "uid-1")

        self.assertEqual(result["results"], [])
        self.assertEqual(result["metadata"]["status"], "empty")


if __name__ == "__main__":
    unittest.main()
