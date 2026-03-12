import unittest
from unittest.mock import patch

from services import library_service


class LibraryServiceHelpersTests(unittest.TestCase):
    @patch("services.library_service.logger.warning")
    def test_safe_json_list_logs_malformed_payload(self, mock_warning):
        result = library_service._safe_json_list("{bad json", field_name="item_tags")

        self.assertEqual(result, [])
        mock_warning.assert_called_once()

    @patch("services.library_service.logger.warning")
    def test_decode_cursor_logs_invalid_cursor(self, mock_warning):
        result = library_service._decode_cursor("not-base64")

        self.assertIsNone(result)
        mock_warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
