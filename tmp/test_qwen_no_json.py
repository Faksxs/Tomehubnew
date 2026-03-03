import asyncio
import sys
import os
import json

# Add apps/backend to sys.path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from config import settings
from services.llm_client import generate_text, PROVIDER_QWEN, MODEL_TIER_FLASH

async def test_minimal_qwen():
    model = settings.LLM_EXPLORER_PRIMARY_MODEL
    print(f"Using model: {model}")
    
    prompt = "Tell me a joke. Format the response as JSON: {\"joke\": \"...\"}"
    
    print("Asking Qwen (without JSON mode)...")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, 
            generate_text,
            model,
            prompt,
            "test_task",
            MODEL_TIER_FLASH,
            0.7,
            100,
            None, # response_mime_type
            30.0,
            False,
            None,
            PROVIDER_QWEN
        )
        print("Success!")
        print(f"Full Result Object: {result}")
        print(f"Text: '{result.text}'")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_minimal_qwen())
