
import sys
import os
import time
import shutil

# Add 'backend' directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mocking missing dependency 'tenacity' by mocking the whole module
# We need to do this BEFORE importing ingestion_service
from unittest.mock import MagicMock
sys.modules['services.ai_service'] = MagicMock()
# Also mock 'services.semantic_classifier' if needed
sys.modules['services.semantic_classifier'] = MagicMock()

# Mock things to simulate failure
from unittest.mock import patch
from services.ingestion_service import ingest_book

def test_file_preservation():
    print("Testing File Preservation Logic...")
    
    # Create a dummy file
    dummy_file = "test_preservation.pdf"
    with open(dummy_file, "w") as f:
        f.write("dummy content")
    
    print(f"Created dummy file: {dummy_file}")
    
    # Patch internals to force 0 inserts (failure) without crashing DB
    # We mock 'extract_pdf_content' to return chunks, but 'check_book_exists' etc.
    # Actually simpler: Mock 'extract_pdf_content' to raise exception? 
    # No, we want to test the 'successful_inserts == 0' path.
    # So we let it extract valid chunks? But force DB insert to fail?
    # Or just mock the whole flow?
    # Let's mock 'extract_pdf_content' to return empty list? No, that returns False early.
    # Let's mock 'extract_pdf_content' to return valid chunks, but mock 'batch_get_embeddings' to return None?
    
    with patch('services.ingestion_service.extract_pdf_content') as mock_extract:
        mock_extract.return_value = [{'text': 'valid chunk', 'page_num': 1}]
        
        with patch('services.ingestion_service.batch_get_embeddings') as mock_embed:
            mock_embed.return_value = [None] # Force embedding failure -> 0 inserts
            
            # Also mock DB to avoid actual connection, or let it connect?
            # Let's mock DB context manager to avoid needing DB running for this logic test
            with patch('services.ingestion_service.DatabaseManager') as mock_db:
                mock_conn = MagicMock()
                mock_cursor = MagicMock()
                mock_db.get_connection.return_value.__enter__.return_value = mock_conn
                mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
                
                # Run ingest
                print("Running ingestion (expecting failure)...")
                result = ingest_book(dummy_file, "Test Title", "Test Author", "test_user")
                
                print(f"Ingestion result: {result}")
                
                if os.path.exists(dummy_file):
                    print("SUCCESS: File preserved after failure.")
                    os.remove(dummy_file) # Cleanup
                else:
                    print("FAIL: File was deleted despite failure!")
                    sys.exit(1)

if __name__ == "__main__":
    test_file_preservation()
