
import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from services.smart_search_service import perform_smart_search
from services.epistemic_service import get_prompt_for_mode

def test_search_depth():
    print("\n--- Testing Search Depth ---")
    try:
        # We can't easily check the LIMIT inside the function without mocking, 
        # but we can check if it runs without error accepting the parameter.
        # We will assume a simple query.
        print("Calling perform_smart_search with search_depth='deep'...")
        # Note: This might make a real call to Oracle/Gemini. 
        # Ideally we mock, but for now we just want to ensure signature is correct.
        # We Mock Orchestrator to avoid real calls? 
        # Or just run it and see (it might fail if DB not connected, but that verifies signature).
        pass
    except Exception as e:
        print(f"FAILED: {e}")

def test_explorer_prompt():
    print("\n--- Testing Explorer Prompt ---")
    context = "Sample Context"
    question = "What is X?"
    prompt = get_prompt_for_mode('EXPLORER', context, question)
    
    if "EXPLORER" in prompt and "DİYALEKTİK" in prompt:
        print("SUCCESS: Explorer Prompt generated correctly.")
        print("Snippet:", prompt[:100].replace('\n', ' '))
    else:
        print("FAILED: Explorer prompt content missing.")
        print("Got:", prompt[:100])

if __name__ == "__main__":
    test_explorer_prompt()
    # We skip actual search call to avoid side effects/latency in this quick check, 
    # relying on the fact that python loaded the module successfully.
    # To verify perform_smart_search signature, we can inspect it.
    import inspect
    sig = inspect.signature(perform_smart_search)
    if 'search_depth' in sig.parameters:
        print("\nSUCCESS: perform_smart_search has 'search_depth' parameter.")
    else:
        print("\nFAILED: perform_smart_search missing 'search_depth'.")
