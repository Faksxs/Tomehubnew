import unittest
from unittest.mock import patch

from config import settings
from services import external_kb_service


class ExternalKBServiceTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "EXTERNAL_KB_ENABLED": settings.EXTERNAL_KB_ENABLED,
            "EXTERNAL_KB_OPENALEX_EXPLORER_ONLY": settings.EXTERNAL_KB_OPENALEX_EXPLORER_ONLY,
        }

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_compute_academic_scope_matches_source_of_truth(self):
        self.assertTrue(external_kb_service.compute_academic_scope(["felsefe", "roman"]))
        self.assertTrue(external_kb_service.compute_academic_scope([" modernite "]))
        self.assertFalse(external_kb_service.compute_academic_scope(["roman", "edebiyat"]))

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


if __name__ == "__main__":
    unittest.main()
