import unittest

from services.search_system.strategies import (
    _apply_active_library_item_filter,
    _apply_resource_type_filter,
)


class SearchStrategyGuardTests(unittest.TestCase):
    def test_active_library_item_filter_adds_not_deleted_exists_clause(self):
        sql, params = _apply_active_library_item_filter(
            """
            SELECT c.id
            FROM TOMEHUB_CONTENT_V2 c
            LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
            WHERE c.firebase_uid = :p_uid
            """,
            {"p_uid": "uid-1"},
        )

        self.assertIn("TOMEHUB_LIBRARY_ITEMS li_active", sql)
        self.assertIn("NVL(li_active.IS_DELETED, 0) = 0", sql)
        self.assertEqual(params["p_uid"], "uid-1")

    def test_active_library_item_filter_is_noop_for_legacy_sql(self):
        sql, _ = _apply_active_library_item_filter(
            "SELECT id FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid",
            {"p_uid": "uid-1"},
        )

        self.assertNotIn("li_active", sql)

    def test_movie_filter_checks_active_library_item_when_no_join_alias(self):
        sql, params = _apply_resource_type_filter(
            "SELECT c.id FROM TOMEHUB_CONTENT_V2 c WHERE c.firebase_uid = :p_uid",
            {"p_uid": "uid-1"},
            "MOVIE",
        )

        self.assertEqual(params["p_item_type"], "MOVIE")
        self.assertIn("NVL(li2.IS_DELETED, 0) = 0", sql)


if __name__ == "__main__":
    unittest.main()
