import unittest

from services.ingestion_status_service import _decode_json_if_needed


class IngestionStatusServiceTests(unittest.TestCase):
    def test_decode_json_preserves_plain_strings(self):
        self.assertEqual(_decode_json_if_needed("TEXT_NATIVE"), "TEXT_NATIVE")
        self.assertEqual(_decode_json_if_needed("PYMUPDF"), "PYMUPDF")

    def test_decode_json_parses_json_payloads(self):
        self.assertEqual(_decode_json_if_needed('{"retry_as_ocr": false}'), {"retry_as_ocr": False})
        self.assertEqual(_decode_json_if_needed("[1, 2, 3]"), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
