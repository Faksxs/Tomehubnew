import unittest

from config import settings
from services.odl_shadow_service import should_enable_odl_secondary_for_target


class TestOdlSecondaryFlags(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "ODL_SECONDARY_ENABLED": settings.ODL_SECONDARY_ENABLED,
            "ODL_SHADOW_INGEST_ENABLED": settings.ODL_SHADOW_INGEST_ENABLED,
            "ODL_RESCUE_ENABLED": settings.ODL_RESCUE_ENABLED,
            "ODL_SECONDARY_UID_ALLOWLIST": set(settings.ODL_SECONDARY_UID_ALLOWLIST),
            "ODL_SECONDARY_BOOK_ALLOWLIST": set(settings.ODL_SECONDARY_BOOK_ALLOWLIST),
        }

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(settings, k, v)

    def test_secondary_disabled_blocks_target(self):
        settings.ODL_SECONDARY_ENABLED = False
        settings.ODL_SECONDARY_UID_ALLOWLIST = set()
        settings.ODL_SECONDARY_BOOK_ALLOWLIST = set()
        self.assertFalse(should_enable_odl_secondary_for_target("u1", "b1"))

    def test_uid_allowlist_enforced(self):
        settings.ODL_SECONDARY_ENABLED = True
        settings.ODL_SECONDARY_UID_ALLOWLIST = {"u-canary"}
        settings.ODL_SECONDARY_BOOK_ALLOWLIST = set()
        self.assertTrue(should_enable_odl_secondary_for_target("u-canary", "b1"))
        self.assertFalse(should_enable_odl_secondary_for_target("u-other", "b1"))

    def test_book_allowlist_enforced(self):
        settings.ODL_SECONDARY_ENABLED = True
        settings.ODL_SECONDARY_UID_ALLOWLIST = set()
        settings.ODL_SECONDARY_BOOK_ALLOWLIST = {"book-1"}
        self.assertTrue(should_enable_odl_secondary_for_target("u1", "book-1"))
        self.assertFalse(should_enable_odl_secondary_for_target("u1", "book-2"))

    def test_enabled_without_allowlists_allows_target(self):
        settings.ODL_SECONDARY_ENABLED = True
        settings.ODL_SECONDARY_UID_ALLOWLIST = set()
        settings.ODL_SECONDARY_BOOK_ALLOWLIST = set()
        self.assertTrue(should_enable_odl_secondary_for_target("u1", "b1"))


if __name__ == "__main__":
    unittest.main()
