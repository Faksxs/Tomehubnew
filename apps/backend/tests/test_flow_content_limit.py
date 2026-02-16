import unittest
from unittest.mock import patch

from services.flow_service import _limit_flow_content, _prepare_flow_card_content


class TestFlowContentLimit(unittest.TestCase):
    def test_limit_flow_content_returns_same_for_short_text(self):
        text = "Bu kısa bir metin."
        self.assertEqual(_limit_flow_content(text, limit=650), text)

    def test_limit_flow_content_cuts_at_sentence_end_within_limit(self):
        text = ("Bu bir cumledir. " * 80).strip()
        limited = _limit_flow_content(text, limit=650)

        self.assertLessEqual(len(limited), 650)
        self.assertTrue(limited.endswith((".", "!", "?", "\u2026")))

    def test_limit_flow_content_uses_forward_sentence_window(self):
        text = ("a" * 700) + ". Devam metni."
        limited = _limit_flow_content(text, limit=650)

        self.assertTrue(limited.endswith("."))
        self.assertLessEqual(len(limited), 770)

    def test_limit_flow_content_falls_back_to_whitespace_with_ellipsis(self):
        text = ("kelime " * 200).strip()
        limited = _limit_flow_content(text, limit=650)

        self.assertTrue(limited.endswith("..."))
        self.assertLessEqual(len(limited), 653)

    def test_prepare_flow_card_content_limits_only_external_sources(self):
        long_text = ("Bu metin cok uzun " * 80).strip()

        limited = _prepare_flow_card_content(long_text, "PDF")
        untouched = _prepare_flow_card_content(long_text, "HIGHLIGHT")

        self.assertLessEqual(len(limited), 653)
        self.assertEqual(untouched, long_text)

    def test_prepare_flow_card_content_calls_repair_before_limit(self):
        raw_text = "kelime-\nler bazen kirilir."
        repaired_text = ("duzeltilmis " * 120).strip()

        with patch("services.flow_service.repair_for_flow_card", return_value=repaired_text) as mocked_repair:
            limited = _prepare_flow_card_content(raw_text, "PDF")

        mocked_repair.assert_called_once_with(raw_text, "PDF")
        self.assertLessEqual(len(limited), 653)
        self.assertNotEqual(limited, raw_text)


if __name__ == "__main__":
    unittest.main()
