import unittest

from services.search_system.strategies import _contains_like_pattern, _escape_like_literal


class TestSearchSqlSafety(unittest.TestCase):
    def test_escape_like_literal_escapes_wildcards(self):
        self.assertEqual(_escape_like_literal("100%_safe"), "100\\%\\_safe")

    def test_escape_like_literal_escapes_backslash_first(self):
        self.assertEqual(_escape_like_literal(r"a\b%c_d"), r"a\\b\%c\_d")

    def test_contains_like_pattern_wraps_with_percent(self):
        self.assertEqual(_contains_like_pattern("niyet"), "%niyet%")


if __name__ == "__main__":
    unittest.main()

