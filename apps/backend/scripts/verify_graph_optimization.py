
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock modules
sys.modules['oracledb'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()
sys.modules['fastapi'] = MagicMock()
sys.modules['pydantic'] = MagicMock()

from services import search_service

class TestGraphOptimization(unittest.TestCase):
    
    @patch('infrastructure.db_manager.DatabaseManager.get_connection')
    def test_batched_graph_query(self, mock_conn):
        print("\n[TEST] Verifying Graph Batch Query (Task 4.1)")
        
        # Setup Mock DB
        mock_cursor = MagicMock()
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock Inputs (Layer 2 Results with IDs)
        base_results = [
            {'id': 101, 'title': 'Book A'},
            {'id': 102, 'title': 'Book B'}
        ]
        
        # Mock DB Responses
        # 1. Concept Query Response (content_id, concept_name, concept_id)
        mock_cursor.fetchall.side_effect = [
            [
                (101, 'Justice', 1),
                (102, 'Liberty', 2)
            ],
            # 2. Neighbor Query Response (concept_A, rel_type, concept_B)
            [
                ('Justice', 'REQUIRES', 'Liberty'),
                ('Liberty', 'ENABLES', 'Creativity')
            ]
        ]
        
        # Run Function
        context = search_service.get_graph_enriched_context(base_results, "user1")
        
        # Verification
        print(f"Generated Context:\n{context}")
        
        self.assertIn("Justice is connected to Liberty", context)
        self.assertIn("Liberty is connected to Creativity", context)
        
        # Verify SQL calls were batched (only 2 executes)
        self.assertEqual(mock_cursor.execute.call_count, 2)
        
        # Verify Bind Variables used IDs
        args_1 = mock_cursor.execute.call_args_list[0][0]
        sql_1 = args_1[0]
        params_1 = args_1[1]
        
        print(f"\n[DEBUG] SQL 1: {sql_1}")
        print(f"[DEBUG] Params 1: {params_1}")
        
        self.assertIn("IN(:id0,:id1)", sql_1.replace(" ", "")) 
        self.assertEqual(params_1['id0'], 101)
        self.assertEqual(params_1['id1'], 102)

        print("[SUCCESS] Batched query logic verified.")

if __name__ == '__main__':
    unittest.main()
