import unittest
from unittest.mock import patch

from config import settings
from services import islamic_api_service


class IslamicApiServiceTests(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "ISLAMIC_API_ENABLED": settings.ISLAMIC_API_ENABLED,
            "QURAN_FOUNDATION_ENABLED": settings.QURAN_FOUNDATION_ENABLED,
            "DIYANET_QURAN_ENABLED": settings.DIYANET_QURAN_ENABLED,
            "HADEETHENC_ENABLED": settings.HADEETHENC_ENABLED,
            "HADITH_API_ENABLED": settings.HADITH_API_ENABLED,
        }
        settings.ISLAMIC_API_ENABLED = True
        settings.QURAN_FOUNDATION_ENABLED = True
        settings.DIYANET_QURAN_ENABLED = True
        settings.HADEETHENC_ENABLED = True
        settings.HADITH_API_ENABLED = True

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
            {"id": "100", "title": "Namazın Fazileti"},
            {"id": "200", "title": "Dua Etme Adabı"},
            {"id": "300", "title": "Kur'an Tefsiri"},
        ]

        out = islamic_api_service._pick_hadeethenc_category_ids("namaz ile ilgili hadis", limit=2)

        self.assertEqual(out, ["100"])

    @patch("services.islamic_api_service._diyanet_fetch_verse")
    @patch("services.islamic_api_service._quran_foundation_fetch_verse")
    def test_exact_quran_candidates_merge_primary_and_secondary(self, mock_qf_verse, mock_diyanet_verse):
        mock_qf_verse.return_value = {
            "verse_key": "1:1",
            "text_uthmani": "بِسْمِ ٱللَّهِ",
            "translations": [{"text": "Rahman ve Rahim olan Allah'ın adıyla:", "resource_name": "Diyanet"}],
        }
        mock_diyanet_verse.return_value = {
            "title": "Diyanet - Ayet 1:1",
            "content_chunk": "Rahman ve Rahim olan Allah'ın adıyla:\nبِسْمِ ٱللَّهِ",
            "page_number": 0,
            "source_type": "ISLAMIC_EXTERNAL",
            "score": 0.80,
            "external_weight": 0.22,
            "provider": "DIYANET_QURAN",
            "religious_source_kind": "QURAN",
            "reference": "1:1",
        }

        candidates, meta = islamic_api_service.get_islamic_external_candidates("1:1 ayeti", limit=4)

        self.assertEqual(len(candidates), 2)
        self.assertTrue(meta["used"])
        self.assertTrue(meta["quran_used"])
        self.assertIn("QURAN_FOUNDATION", meta["providers"])
        self.assertIn("DIYANET_QURAN", meta["providers"])


if __name__ == "__main__":
    unittest.main()
