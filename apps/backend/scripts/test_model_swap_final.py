
import sys
import os
sys.path.append(os.getcwd())

from config import settings
from services.llm_client import get_provider, get_model_for_tier, MODEL_TIER_FLASH, ROUTE_MODE_EXPLORER_QWEN_PILOT, PROVIDER_NVIDIA, PROVIDER_QWEN

def test_config():
    print(f"--- Configuration Test ---")
    print(f"LLM_EXPLORER_QWEN_PILOT_ENABLED: {settings.LLM_EXPLORER_QWEN_PILOT_ENABLED}")
    print(f"LLM_EXPLORER_PRIMARY_PROVIDER: {settings.LLM_EXPLORER_PRIMARY_PROVIDER}")
    print(f"LLM_EXPLORER_PRIMARY_MODEL: {settings.LLM_EXPLORER_PRIMARY_MODEL}")
    
    # Test Provider Resolution
    provider = get_provider(settings.LLM_EXPLORER_PRIMARY_PROVIDER)
    print(f"Resolved Provider Name: {provider.name}")
    
    # Test Model resolution for Flash tier
    model = get_model_for_tier(MODEL_TIER_FLASH)
    print(f"Default (Flash Tier) Model: {model}")
    
    # Verify if secondary (Explorer) mode would use Qwen3.5
    from services.llm_client import _resolve_primary_provider_hint
    hint = _resolve_primary_provider_hint(None, ROUTE_MODE_EXPLORER_QWEN_PILOT)
    print(f"Explorer Mode Provider Hint: {hint}")
    
    if settings.LLM_EXPLORER_QWEN_PILOT_ENABLED and hint in {PROVIDER_NVIDIA, PROVIDER_QWEN}:
        print("✓ SUCCESS: Explorer mode is configured to use NVIDIA/Qwen.")
        print(f"✓ Target Model: {settings.LLM_EXPLORER_PRIMARY_MODEL}")
    else:
        print("✗ FAILURE: Explorer mode or NVIDIA provider is not correctly enabled.")

if __name__ == "__main__":
    test_config()
