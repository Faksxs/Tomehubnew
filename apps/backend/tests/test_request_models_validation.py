import unittest
from pydantic import ValidationError

from models.request_models import SearchRequest, ChatRequest


class RequestModelValidationTests(unittest.TestCase):
    def test_search_rejects_negative_offset(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                question="test",
                firebase_uid="u1",
                limit=20,
                offset=-1,
            )

    def test_search_rejects_oversized_question(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                question="a" * 3000,
                firebase_uid="u1",
            )

    def test_search_rejects_whitespace_question(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                question="   ",
                firebase_uid="u1",
            )

    def test_chat_mode_validation(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="hello",
                firebase_uid="u1",
                mode="random",
            )


if __name__ == "__main__":
    unittest.main()
