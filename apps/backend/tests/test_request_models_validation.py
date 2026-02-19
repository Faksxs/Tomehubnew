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

    def test_search_scope_mode_validation(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                question="test",
                firebase_uid="u1",
                scope_mode="invalid_scope",
            )

    def test_search_scope_mode_default(self):
        req = SearchRequest(
            question="test",
            firebase_uid="u1",
        )
        self.assertEqual(req.scope_mode, "AUTO")

    def test_search_compare_mode_validation(self):
        with self.assertRaises(ValidationError):
            SearchRequest(
                question="test",
                firebase_uid="u1",
                compare_mode="invalid",
            )

    def test_search_compare_mode_default(self):
        req = SearchRequest(
            question="test",
            firebase_uid="u1",
        )
        self.assertEqual(req.compare_mode, "EXPLICIT_ONLY")

    def test_search_target_book_ids_normalization(self):
        req = SearchRequest(
            question="test",
            firebase_uid="u1",
            target_book_ids=[" b1 ", "b1", "b2", ""],
        )
        self.assertEqual(req.target_book_ids, ["b1", "b2"])

    def test_chat_mode_validation(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="hello",
                firebase_uid="u1",
                mode="random",
            )

    def test_chat_scope_mode_validation(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="hello",
                firebase_uid="u1",
                scope_mode="invalid_scope",
            )

    def test_chat_scope_mode_default(self):
        req = ChatRequest(
            message="hello",
            firebase_uid="u1",
        )
        self.assertEqual(req.scope_mode, "AUTO")

    def test_chat_compare_mode_validation(self):
        with self.assertRaises(ValidationError):
            ChatRequest(
                message="hello",
                firebase_uid="u1",
                compare_mode="invalid",
            )

    def test_chat_compare_mode_default(self):
        req = ChatRequest(
            message="hello",
            firebase_uid="u1",
        )
        self.assertEqual(req.compare_mode, "EXPLICIT_ONLY")

    def test_chat_target_book_ids_normalization(self):
        req = ChatRequest(
            message="hello",
            firebase_uid="u1",
            target_book_ids=[" b1 ", "b1", "b2", ""],
        )
        self.assertEqual(req.target_book_ids, ["b1", "b2"])


if __name__ == "__main__":
    unittest.main()
