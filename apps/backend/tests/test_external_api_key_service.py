import unittest
from unittest.mock import patch

from services import external_api_key_service as key_service


class _FakeReadCursor:
    def __init__(self, row, counter):
        self._row = row
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self._counter["execute"] += 1

    def fetchone(self):
        return self._row


class _FakeReadConnection:
    def __init__(self, row, counter):
        self._row = row
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeReadCursor(self._row, self._counter)


class _FakeWriteCursor:
    def __init__(self, counter):
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self._counter["execute"] += 1


class _FakeWriteConnection:
    def __init__(self, counter):
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeWriteCursor(self._counter)

    def commit(self):
        self._counter["commit"] += 1


class ExternalApiKeyServiceTests(unittest.TestCase):
    def setUp(self):
        key_service.invalidate_external_api_key_cache()
        key_service._last_key_touch_by_id.clear()

    def tearDown(self):
        key_service.invalidate_external_api_key_cache()
        key_service._last_key_touch_by_id.clear()

    def test_resolve_external_api_key_uses_ttl_cache(self):
        raw_key = "th_live_test_key"
        counter = {"execute": 0}

        with patch.object(key_service.settings, "EXTERNAL_API_ENABLED", True), \
             patch.object(key_service.settings, "EXTERNAL_API_KEY_PEPPER", "pepper"), \
             patch.object(key_service.settings, "EXTERNAL_API_KEY_CACHE_TTL_SEC", 300), \
             patch.object(key_service.settings, "EXTERNAL_API_KEY_CACHE_MAXSIZE", 128), \
             patch.object(key_service.DatabaseManager, "get_read_connection") as mock_get_read_connection:
            key_hash = key_service.hash_external_api_key(raw_key)
            row = (
                11,
                "owner-1",
                key_service.get_key_prefix(raw_key),
                "Main key",
                '["search:read"]',
                "ACTIVE",
                None,
                key_hash,
            )
            mock_get_read_connection.return_value = _FakeReadConnection(row, counter)
            record1 = key_service.resolve_external_api_key(raw_key)
            record2 = key_service.resolve_external_api_key(raw_key)

        self.assertIsNotNone(record1)
        self.assertEqual(record1.key_id, 11)
        self.assertEqual(record2.key_id, 11)
        self.assertEqual(counter["execute"], 1)

    def test_touch_external_api_key_debounces_repeated_writes(self):
        counter = {"execute": 0, "commit": 0}

        with patch.object(key_service.settings, "EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC", 300), \
             patch.object(key_service.DatabaseManager, "get_write_connection", return_value=_FakeWriteConnection(counter)):
            key_service.touch_external_api_key(7, "127.0.0.1")
            key_service.touch_external_api_key(7, "127.0.0.1")

        self.assertEqual(counter["execute"], 1)
        self.assertEqual(counter["commit"], 1)

    def test_touch_external_api_key_writes_when_ip_changes(self):
        counter = {"execute": 0, "commit": 0}

        with patch.object(key_service.settings, "EXTERNAL_API_KEY_TOUCH_DEBOUNCE_SEC", 300), \
             patch.object(key_service.DatabaseManager, "get_write_connection", return_value=_FakeWriteConnection(counter)):
            key_service.touch_external_api_key(7, "127.0.0.1")
            key_service.touch_external_api_key(7, "127.0.0.2")

        self.assertEqual(counter["execute"], 2)
        self.assertEqual(counter["commit"], 2)


if __name__ == "__main__":
    unittest.main()
