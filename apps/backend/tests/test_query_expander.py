import unittest
from unittest.mock import patch

from services.query_expander import QueryExpander


class _FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value


class _FakeResult:
    def __init__(self, text):
        self.text = text


class QueryExpanderTests(unittest.TestCase):
    def test_expand_query_parses_json_variations(self):
        expander = QueryExpander(cache=_FakeCache())
        with patch("services.query_expander.generate_text", return_value=_FakeResult('["v1","v2"]')):
            results = expander.expand_query("yonetim iktidar", max_variations=2)
        self.assertEqual(results, ["v1", "v2"])

    def test_expand_query_fail_open_on_internal_error(self):
        expander = QueryExpander(cache=_FakeCache())
        with patch.object(QueryExpander, "_expand_query_impl", side_effect=RuntimeError("boom")):
            results = expander.expand_query("yonetim iktidar", max_variations=2)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
