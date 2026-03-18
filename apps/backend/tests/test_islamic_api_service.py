import unittest
from unittest.mock import patch

from config import settings
from services import islamic_api_service


class IslamicApiServiceTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "ISLAMIC_API_ENABLED": settings.ISLAMIC_API_ENABLED,
            "QURANENC_ENABLED": settings.QURANENC_ENABLED,
            "ISLAMHOUSE_ENABLED": settings.ISLAMHOUSE_ENABLED,
            "QURAN_FOUNDATION_ENABLED": settings.QURAN_FOUNDATION_ENABLED,
            "DIYANET_QURAN_ENABLED": settings.DIYANET_QURAN_ENABLED,
            "HADEETHENC_ENABLED": settings.HADEETHENC_ENABLED,
            "RELIGIOUS_DATASET_SEARCH_ENABLED": settings.RELIGIOUS_DATASET_SEARCH_ENABLED,
        }
        settings.ISLAMIC_API_ENABLED = True
        settings.QURANENC_ENABLED = True
        settings.ISLAMHOUSE_ENABLED = True
        settings.QURAN_FOUNDATION_ENABLED = True
        settings.DIYANET_QURAN_ENABLED = True
        settings.HADEETHENC_ENABLED = True
        settings.RELIGIOUS_DATASET_SEARCH_ENABLED = True

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(settings, key, value)

    def test_religious_query_detection_and_verse_key(self):
        self.assertTrue(islamic_api_service.is_religious_query("Bakara 2:255 ayeti ne diyor"))
        self.assertTrue(islamic_api_service._looks_hadith_query("Buhari hadis no 66"))
        self.assertEqual(islamic_api_service._extract_verse_key("Bakara 2:255 ayeti"), "2:255")

    @patch("services.islamic_api_service._get_hadeethenc_categories")
    def test_hadeethenc_category_picker_handles_turkish_normalization(self, mock_categories):
        mock_categories.return_value = [
            {"id": "100", "title": "Namazin Fazileti"},
            {"id": "200", "title": "Dua Etme Adabi"},
            {"id": "300", "title": "Kur'an Tefsiri"},
        ]

        out = islamic_api_service._pick_hadeethenc_category_ids("namaz ile ilgili hadis", limit=2)

        self.assertEqual(out, ["100"])

    @patch("services.islamic_api_service._diyanet_fetch_verse")
    @patch("services.islamic_api_service._quran_foundation_fetch_verse")
    @patch("services.islamic_api_service._quranenc_fetch_verse")
    @patch("services.islamic_api_service.get_religious_dataset_candidates")
    def test_exact_quran_candidates_merge_primary_and_secondary(
        self,
        mock_dataset_candidates,
        mock_quranenc_verse,
        mock_qf_verse,
        mock_diyanet_verse,
    ):
        mock_dataset_candidates.return_value = ([], {"used": False, "providers": {}, "reason": "skipped"})
        mock_quranenc_verse.return_value = {
            "sura": "1",
            "aya": "1",
            "arabic_text": "bismillahirrahmanirrahim",
            "translation": "Rahman ve Rahim olan Allah'in adiyla:",
            "_translation_key": "turkish_rwwad",
            "_source_url": "https://quranenc.com/api/v1/translation/aya/turkish_rwwad/1/1",
        }
        mock_qf_verse.return_value = {
            "verse_key": "1:1",
            "text_uthmani": "bismillah",
            "translations": [{"text": "Rahman ve Rahim olan Allah'in adiyla:", "resource_name": "Diyanet"}],
        }
        mock_diyanet_verse.return_value = {
            "title": "Diyanet - Ayet 1:1",
            "content_chunk": "Rahman ve Rahim olan Allah'in adiyla:\nbismillah",
            "page_number": 0,
            "source_type": "ISLAMIC_EXTERNAL",
            "score": 0.80,
            "external_weight": 0.22,
            "provider": "DIYANET_QURAN",
            "religious_source_kind": "QURAN",
            "reference": "1:1",
        }

        candidates, meta = islamic_api_service.get_islamic_external_candidates("1:1 ayeti", limit=4)

        self.assertEqual(len(candidates), 3)
        self.assertTrue(meta["used"])
        self.assertTrue(meta["quran_used"])
        self.assertEqual(candidates[0]["provider"], "QURANENC")
        self.assertIn("QURANENC", meta["providers"])
        self.assertIn("QURAN_FOUNDATION", meta["providers"])
        self.assertIn("DIYANET_QURAN", meta["providers"])
        mock_dataset_candidates.assert_not_called()

    @patch("services.islamic_api_service._islamhouse_fetch_category_items")
    @patch("services.islamic_api_service._islamhouse_category_tree")
    @patch("services.islamic_api_service._quran_foundation_search", return_value=[])
    @patch("services.islamic_api_service.get_religious_dataset_candidates")
    def test_topical_religious_query_adds_islamhouse_interpretive_context(
        self,
        mock_dataset_candidates,
        _mock_qf_search,
        mock_category_tree,
        mock_category_items,
    ):
        mock_dataset_candidates.return_value = (
            [
                {
                    "title": "Hadith API - bukhari 66",
                    "content_chunk": "Sabir ve merhamet hakkinda hadis",
                    "page_number": 0,
                    "source_type": "ISLAMIC_EXTERNAL",
                    "score": 0.63,
                    "external_weight": 0.13,
                    "provider": "HADITH_API_DATASET",
                    "religious_source_kind": "HADITH",
                    "reference": "bukhari:66",
                }
            ],
            {"used": True, "providers": {"HADITH_API_DATASET": 1}, "reason": "ok"},
        )
        mock_category_tree.return_value = [
            {
                "id": 728011,
                "title": "Tefsir",
                "description": "Kur'an tefsiri ve aciklamalari",
                "has_children": False,
            }
        ]
        mock_category_items.return_value = [
            {
                "id": 1001,
                "title": "Tefsir Usulu",
                "description": "Kur'an ayetlerinin yorumlanmasi ve baglami.",
                "api_url": "https://api3.islamhouse.com/v3/public/main/get-item/1001/tr/json",
            }
        ]

        candidates, meta = islamic_api_service.get_islamic_external_candidates("tefsir nedir", limit=3)

        self.assertTrue(meta["used"])
        self.assertIn("ISLAMHOUSE", meta["providers"])
        self.assertIn("HADITH_API_DATASET", meta["providers"])
        self.assertTrue(any(c["provider"] == "ISLAMHOUSE" for c in candidates))
        self.assertTrue(any(c["religious_source_kind"] == "INTERPRETATION" for c in candidates))
        self.assertTrue(any(c["provider"] == "HADITH_API_DATASET" for c in candidates))


if __name__ == "__main__":
    unittest.main()
