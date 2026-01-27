
import sys
import os
import inspect
import flask # Not used, but just to check venv
import asyncio

# Add backend directory to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def verify_phase2():
    print("--- Verifying Phase 2 Changes ---")
    
    # 1. Verify get_rag_context signature
    try:
        from services.search_service import get_rag_context
        sig = inspect.signature(get_rag_context)
        if 'mode' in sig.parameters:
            print("PASS: get_rag_context has 'mode' parameter.")
        else:
            print("FAIL: get_rag_context MISSING 'mode' parameter.")
    except Exception as e:
        print(f"FAIL: Could not import search_service: {e}")

    # 2. Verify dual_ai_orchestrator syntax (by import)
    try:
        from services.dual_ai_orchestrator import generate_evaluated_answer
        print("PASS: dual_ai_orchestrator imported successfully (Syntax OK).")
    except Exception as e:
        print(f"FAIL: dual_ai_orchestrator syntax error: {e}")

    # 3. Verify Work AI Temperature Logic (implied by file presence)
    # Hard to test internal logic without running, but import checks syntax.
    try:
        from services.work_ai_service import generate_work_ai_answer
        print("PASS: work_ai_service imported successfully.")
    except Exception as e:
        print(f"FAIL: work_ai_service syntax error: {e}")

    # 4. Verify ChatRequest model
    try:
        from models.request_models import ChatRequest
        fields = ChatRequest.model_fields
        if 'mode' in fields:
             print("PASS: ChatRequest model has 'mode' field.")
        else:
             print("FAIL: ChatRequest model MISSING 'mode' field.")
    except Exception as e:
         print(f"FAIL: request_models import failed: {e}")

if __name__ == "__main__":
    verify_phase2()
