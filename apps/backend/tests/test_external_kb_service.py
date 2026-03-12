import unittest
from unittest.mock import patch

from config import settings
from services import external_kb_service


class ExternalKBServiceTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
            "EXTERNAL_KB_OPENALEX_EXPLORER_ONLY": settings.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY,
            "EXTERNAL_KB_HTTP_MAX_RETRY": settings.EXTERNAL_KB_HTTP_MAX_RETRY,
            "OPENALEX_API_KEY": getattr(settings, "OPENALEX_API_KEY", ""),
            "OPENALEX_EMAIL": getattr(settings, "OPENALEX_EMAIL", ""),
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_compute_academic_scope_matches_source_of_truth(self):
        self.assertTrue(external_kb_service.compute_academic_scope(["felsefe", "roman"]))
        self.assertTrue(external_kb_service.compute_academic_scope([" modernite "]))
        self.assertFalse(external_kb_service.compute_academic_scope(["roman", "edebiyat"]))

    def test_item_scope_promotes_articles_and_doi_urls(self):
        self.assertTrue(
            external_kb_service._compute_academic_scope_for_item(
                [],
                item_type="ARTICLE",
                source_url="",
            )
        )
        self.assertTrue(
            external_kb_service._compute_academic_scope_for_item(
                [],
                item_type="BOOK",
                source_url="https://doi.org/10.1000/xyz123",
            )
        )
        self.assertFalse(
            external_kb_service._compute_academic_scope_for_item(
                [],
                item_type="BOOK",
                source_url="https://example.com/post",
            )
        )

    @patch("services.external_kb_service.upsert_external_graph")
    @patch("services.external_kb_service._fetch_openalex")
    def test_openalex_skips_when_not_academic(self, mock_fetch_openalex, mock_upsert):
        settings.EXTERNAL_KB_ENABLED = True
        settings.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY = True

        out = external_kb_service.enrich_book_with_openalex(
            book_id="b1",
            firebase_uid="u1",
            title="Roman",
            author="Yazar",
            tags=["edebiyat"],
            mode_hint="EXPLORER",
        )
        self.assertEqual(out.get("status"), "skipped_non_academic")
        mock_fetch_openalex.assert_not_called()
        mock_upsert.assert_called_once()

    @patch("services.external_kb_service.upsert_external_graph")
    @patch("services.external_kb_service._fetch_openalex")
    def test_openalex_respects_explorer_only_gate(self, mock_fetch_openalex, mock_upsert):
        settings.EXTERNAL_KB_ENABLED = True
        settings.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY = True

        out = external_kb_service.enrich_book_with_openalex(
            book_id="b1",
            firebase_uid="u1",
            title="Sosyoloji",
            author="Yazar",
            tags=["sosyoloji"],
            mode_hint="INGEST",
        )
        self.assertEqual(out.get("status"), "skipped_by_mode")
        mock_fetch_openalex.assert_not_called()
        mock_upsert.assert_called_once()

    @patch("services.external_kb_service.upsert_external_graph", return_value={"updated": True})
    @patch("services.external_kb_service._fetch_openalex")
    def test_openalex_allows_article_ingest_and_prefers_doi(self, mock_fetch_openalex, mock_upsert):
        settings.EXTERNAL_KB_ENABLED = True
        settings.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY = True
        mock_fetch_openalex.return_value = {"id": "W1", "display_name": "Paper", "doi": "10.1000/xyz"}

        out = external_kb_service.enrich_book_with_openalex(
            book_id="b1",
            firebase_uid="u1",
            title="Paper Title",
            author="Author",
            tags=[],
            mode_hint="INGEST",
            item_type="ARTICLE",
            source_url="https://doi.org/10.1000/xyz",
        )

        self.assertEqual(out.get("status"), "ok")
        mock_fetch_openalex.assert_called_once_with("Paper Title", "Author", doi="10.1000/xyz")
        mock_upsert.assert_called_once()

    @patch("services.external_kb_service._http_get_json", return_value={"results": []})
    def test_fetch_openalex_includes_api_key_and_email(self, mock_http):
        settings.OPENALEX_API_KEY = "test-key"
        settings.OPENALEX_EMAIL = "reader@example.com"

        external_kb_service._fetch_openalex("Paper", "Author", doi="10.1000/xyz")

        args, kwargs = mock_http.call_args
        self.assertIn("api_key=test-key", args[0])
        self.assertIn("mailto=reader%40example.com", args[0])
        self.assertEqual(kwargs.get("headers", {}).get("Authorization"), "Bearer test-key")

    @patch("services.external_kb_service.logger.warning")
    @patch("services.external_kb_service.urllib_request.urlopen", side_effect=RuntimeError("boom"))
    def test_http_get_json_logs_unexpected_failure(self, _mock_urlopen, mock_warning):
        settings.EXTERNAL_KB_HTTP_MAX_RETRY = 0

        result = external_kb_service._http_get_json("https://example.com/test", timeout_sec=0.01)

        self.assertIsNone(result)
        mock_warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
