import unittest
from unittest.mock import patch

from config import settings
from services import religious_dataset_search_service as service


class ReligiousDatasetSearchServiceTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "RELIGIOUS_DATASET_SEARCH_ENABLED": settings.RELIGIOUS_DATASET_SEARCH_ENABLED,
            "RELIGIOUS_DATASET_TYPESENSE_URL": settings.RELIGIOUS_DATASET_TYPESENSE_URL,
            "ISLAMIC_API_MIN_CONFIDENCE": settings.ISLAMIC_API_MIN_CONFIDENCE,
        }
        settings.RELIGIOUS_DATASET_SEARCH_ENABLED = True
        settings.RELIGIOUS_DATASET_TYPESENSE_URL = "http://typesense:8108"
        settings.ISLAMIC_API_MIN_CONFIDENCE = 0.45

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_expand_quran_query_adds_english_terms_for_turkish_topics(self):
        expanded = service._expand_quran_query("rahmet ve sabir ayetleri")

        self.assertIn("mercy", expanded)
        self.assertIn("compassion", expanded)
        self.assertIn("patience", expanded)

    @patch("services.religious_dataset_search_service._search_collection", return_value=[])
    def test_topical_hadith_query_filters_inferred_collection(self, mock_search):
        candidates, meta = service.get_religious_dataset_candidates(
            "Buhari sabir hadisi",
            query_kind="TOPICAL_HADITH",
            limit=3,
        )

        self.assertEqual(candidates, [])
        self.assertFalse(meta["used"])
        payload = mock_search.call_args[0][0]
        self.assertEqual(payload["searches"][0]["filter_by"], "collection:=bukhari")

    @patch("services.religious_dataset_search_service._search_collection")
    def test_prefers_turkish_hadith_and_dedupes_same_reference(self, mock_search):
        mock_search.return_value = [
            {
                "document": {
                    "id": "eng-bukhari:1",
                    "language": "eng",
                    "collection": "bukhari",
                    "hadith_no": "1",
                    "canonical_ref": "bukhari:1",
                    "text": "Intentions are what deeds depend on.",
                    "grade": "",
                    "chapter": "Revelation",
                }
            },
            {
                "document": {
                    "id": "tur-bukhari:1",
                    "language": "tur",
                    "collection": "bukhari",
                    "hadith_no": "1",
                    "canonical_ref": "bukhari:1",
                    "text": "Ameller niyetlere gore deger kazanir.",
                    "grade": "",
                    "chapter": "Vahiy",
                }
            },
        ]

        candidates, meta = service.get_religious_dataset_candidates(
            "Buhari niyet hadisi",
            query_kind="TOPICAL_HADITH",
            limit=3,
        )

        self.assertTrue(meta["used"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["canonical_reference"], "bukhari:1")
        self.assertEqual(candidates[0]["source_language"], "tur")
        self.assertIn("Ameller niyetlere gore", candidates[0]["content_chunk"])

    @patch("services.religious_dataset_search_service._search_collection", return_value=[])
    def test_general_quran_search_uses_expanded_query_terms(self, mock_search):
        service.get_religious_dataset_candidates(
            "rahmet ayetleri",
            query_kind="GENERAL_RELIGIOUS",
            limit=3,
        )

        self.assertEqual(len(mock_search.call_args_list), 1)
        first_payload = mock_search.call_args_list[0][0][0]
        self.assertIn("mercy", first_payload["searches"][0]["q"])


if __name__ == "__main__":
    unittest.main()
