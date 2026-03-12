import unittest
from unittest.mock import patch

from services import firestore_sync_service


class FirestoreSyncServiceTests(unittest.TestCase):
    @patch("services.firestore_sync_service.logger.warning")
    @patch(
        "services.firestore_sync_service.normalize_and_validate_item",
        side_effect=[RuntimeError("bad item"), object()],
    )
    def test_collect_expected_present_ids_logs_invalid_items(self, _mock_normalize, mock_warning):
        result = firestore_sync_service._collect_expected_present_ids(
            {
                "bad-1": {"title": "Broken"},
                "ok-1": {"title": "Valid"},
            },
            scope_uid="uid-1",
        )

        self.assertEqual(result, {"ok-1"})
        mock_warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
