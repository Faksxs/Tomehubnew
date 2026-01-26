
import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from services.ai_service import PROMPT_ENRICH_BOOK
    print("Successfully imported PROMPT_ENRICH_BOOK")
    
    print("-" * 20)
    print(PROMPT_ENRICH_BOOK)
    print("-" * 20)
    
    # Test formatting
    try:
        print("Testing format...")
        formatted = PROMPT_ENRICH_BOOK.format(json_data="{}")
        print("Format SUCCESS")
    except KeyError as e:
        print(f"Format FAILED: KeyError: {repr(e)}")
    except Exception as e:
        print(f"Format FAILED: {type(e).__name__}: {e}")
        
except ImportError as e:
    print(f"Import failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
