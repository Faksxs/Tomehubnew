
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from io import StringIO

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
sys.modules['oracledb'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()

# Import service
from services import search_service

class TestSearchFailure(unittest.TestCase):
    
    @patch('services.search_service.perform_smart_search')
    @patch('services.search_service.get_graph_candidates')
    def test_total_failure(self, mock_graph, mock_vector):
        print("\n[TEST] Verifying Parallel Search Exception Handling (Task 2.5)")
        print(f"Testing file: {search_service.__file__}")
        
        # Simulate FAILURES
        mock_vector.side_effect = RuntimeError("Simulated Vector DB Crash")
        mock_graph.side_effect = RuntimeError("Simulated Graph DB Crash")
        
        # Mock other dependencies that run before/after
        # Return empty list to SKIP the synchronous keyword search block (which would also crash)
        with patch('services.search_service.extract_core_concepts', return_value=[]):
            with patch('services.search_service.time.time', return_value=0):
                
                print("Calling generate_answer...")
                try:
                    answer, sources = search_service.generate_answer("test question", "test_uid")
                except Exception as e:
                    print(f"CAUGHT EXCEPTION IN TEST: {e}")
                    raise e
                    
                print(f"Result: {answer}, {sources}")
                
                # Assertions
                self.assertIsNone(answer, "Answer should be None on total failure")
                self.assertIsNone(sources, "Sources should be None on total failure")
                
                print("  - Returned safe None/None fallback")

if __name__ == '__main__':
    unittest.main()
