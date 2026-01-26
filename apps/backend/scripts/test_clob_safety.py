
import sys
import os
from unittest.mock import MagicMock

# Add 'backend' directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import safe_read_clob

def test_clob_safety():
    print("Testing CLOB Safety...")
    
    # Case 1: Valid Content
    mock_clob_valid = MagicMock()
    mock_clob_valid.read.return_value = "Valid Content"
    res1 = safe_read_clob(mock_clob_valid)
    assert res1 == "Valid Content", f"Expected 'Valid Content', got {res1}"
    print("[PASS] Valid CLOB read successful.")
    
    # Case 2: None input
    res2 = safe_read_clob(None)
    assert res2 == "", f"Expected '', got {res2}"
    print("[PASS] None input handled.")
    
    # Case 3: Corrupted CLOB (Raises Exception)
    mock_clob_corrupt = MagicMock()
    mock_clob_corrupt.read.side_effect = Exception("LOB Read Error: Connection Closed")
    res3 = safe_read_clob(mock_clob_corrupt)
    assert res3 == "", f"Expected '', got {res3}"
    print(f"[PASS] Corrupted CLOB handled gracefully (returned empty string).")
    
    print("\nSUCCESS: All CLOB safety checks passed.")

if __name__ == "__main__":
    test_clob_safety()
