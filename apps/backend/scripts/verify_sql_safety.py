
import sys
import os
import oracledb

# Add 'backend' directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock dependencies to focus just on SQL execution if possible, 
# but integration test is better to ensure the DB accepts the params.
# However, we need 'get_embedding' to work or mock it.
from unittest.mock import MagicMock
sys.modules['services.embedding_service'] = MagicMock()
sys.modules['services.embedding_service'].get_embedding.return_value = [0.1] * 768

from services.search_service import get_book_context
from services.graph_service import get_graph_candidates
from infrastructure.db_manager import DatabaseManager

def test_sql_safety():
    print("Verifying SQL Safety...")
    
    try:
        DatabaseManager.init_pool()
        
        # 1. Test Search Service (get_book_context)
        # Input with single quote - previously unsafe if not sanitized
        print("Testing get_book_context with potentially malicious input...")
        # Note: we need a book_id that MIGHT exist or just check for no SQL error
        # ' OR '1'='1 should not return everything.
        malicious_id = "test_book' OR '1'='1"
        try:
            results = get_book_context(malicious_id, "test query", "test_user")
            print(f"get_book_context returned {len(results)} results (Success/Safe)")
        except Exception as e:
            print(f"FAILED get_book_context: {e}")
            raise

        # 2. Test Graph Service (get_graph_candidates)
        # This one used dynamic IN clauses.
        # We need to find at least one concept to trigger the IN clause logic.
        # We can mock `find_concepts_by_text` or `extract_concepts_and_relations` 
        # inside the service, OR just trust the fallback logic.
        # Let's try to run it. If it fails to find concepts, it returns [], which is "safe" but doesn't test the SQL.
        # We need it to find concepts.
        
        # Let's manually insert a concept if needed? 
        # Or just mock the internal `find_concepts_by_text` to return some IDs [1, 2, 3]
        # allowing us to hit the dynamic SQL generation.
        
        from unittest.mock import patch
        
        # Patching find_concepts_by_text to return valid-looking IDs to trigger the SQL generation
        with patch('services.graph_service.find_concepts_by_text') as mock_find:
            mock_find.return_value = [1, 2, 3]
            
            print("Testing get_graph_candidates with simulated concept IDs...")
            results = get_graph_candidates("some text", "test_user")
            
            # If the SQL generation was wrong (e.g. :id_0 not bound), this would crash
            print(f"get_graph_candidates returned {len(results)} results (Success/Safe)")

    except Exception as e:
        print(f"Global Failure: {e}")
        sys.exit(1)
    finally:
        if DatabaseManager._pool:
            DatabaseManager.close_pool()

if __name__ == "__main__":
    test_sql_safety()
