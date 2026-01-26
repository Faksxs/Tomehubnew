
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import array

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock google.generativeai BEFORE importing embedding_service
mock_genai = MagicMock()
sys.modules['google.generativeai'] = mock_genai

from services import embedding_service

class TestEmbeddingSafety(unittest.TestCase):
    def setUp(self):
        # Ensure API key check passes
        embedding_service.GEMINI_API_KEY = "TEST_KEY"
        # Reset mock
        mock_genai.reset_mock()
        mock_genai.embed_content.side_effect = None
        mock_genai.embed_content.return_value = None

    def test_get_embedding_valid_dict(self):
        print("\n[TEST] get_embedding with valid dict response")
        mock_genai.embed_content.return_value = {'embedding': [0.1] * 768}
        result = embedding_service.get_embedding("test")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 768)
        print("  - Passed")

    def test_get_embedding_valid_object(self):
        print("\n[TEST] get_embedding with valid object response")
        mock_response = MagicMock()
        mock_response.embedding = [0.1] * 768
        mock_genai.embed_content.return_value = mock_response
        
        result = embedding_service.get_embedding("test")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 768)
        print("  - Passed")

    def test_get_embedding_missing_key_dict(self):
        print("\n[TEST] get_embedding with missing key (dict)")
        mock_genai.embed_content.return_value = {'other_field': 'value'}
        result = embedding_service.get_embedding("test")
        self.assertIsNone(result)
        print("  - Passed (returned None gracefully)")

    def test_get_embedding_missing_attr_object(self):
        print("\n[TEST] get_embedding with missing attribute (object)")
        mock_response = MagicMock()
        del mock_response.embedding # Ensure it raises AttributeError on access if not carefully mocked, 
                                    # but MagicMock usually creates attributes on the fly. 
                                    # We need to make sure spec doesn't have it or we explicitly return None?
                                    # Actually MagicMock by default has everything. 
                                    # We need a plain object or restrict the mock.
        
        class PlainObject:
            pass
        
        mock_genai.embed_content.return_value = PlainObject()
        
        result = embedding_service.get_embedding("test")
        self.assertIsNone(result)
        print("  - Passed (returned None gracefully)")

    def test_batch_get_embeddings_fallback(self):
        print("\n[TEST] batch_get_embeddings fallback logic")
        # Simulate batch failure (missing key)
        mock_genai.embed_content.return_value = {'error': 'something'}
        
        # When falling back to sequential, we want it to succeed for this test
        # We need to patch get_embedding to succeed or fail.
        # But wait, the fallback calls get_embedding, which calls mock_genai.embed_content again.
        # So we have to control the side_effect to return failure first, then success.
        
        mock_genai.embed_content.side_effect = [
            {'error': 'batch_failed'}, # invalid batch response
            {'embedding': [0.1] * 768}, # first item sequential success
            {'embedding': [0.2] * 768}  # second item sequential success
        ]
        
        results = embedding_service.batch_get_embeddings(["t1", "t2"])
        
        self.assertEqual(len(results), 2)
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])
        print("  - Passed (fell back to sequential and succeeded)")

if __name__ == '__main__':
    unittest.main()
