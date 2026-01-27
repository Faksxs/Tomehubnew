
import os
import json
import sys

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from prompts.graph_prompts import GRAPH_EXTRACTION_PROMPT

def test_prompt_format():
    print("=== Testing Graph Prompt Format ===")
    sample_text = "Sokrates'e göre erdem bilgidir. Bu yüzden kimse bilerek kötülük yapmaz."
    formatted = GRAPH_EXTRACTION_PROMPT.format(text=sample_text)
    
    # Check for critical keywords in prompt
    assert "confidence" in formatted.lower()
    assert "0.0 - 1.0" in formatted
    assert "[source, type, target, confidence]" in formatted
    
    print("[PASS] Prompt contains confidence scoring instructions.")
    print("\nPrompt Preview:")
    print("-" * 40)
    print(formatted[:300] + "...")
    print("-" * 40)

def test_weighting_logic():
    print("\n=== Testing Weighting Logic (Simulation) ===")
    
    TYPE_WEIGHTS = {
        'DIRECT_CITATION': 1.0, 
        'IS_A': 0.9, 
        'SEMANTIC_SIMILARITY': 0.7, 
        'CO_OCCURRENCE': 0.4
    }
    
    test_cases = [
        ("IS_A", 1.0, 0.9),      # Strong link, strong type
        ("IS_A", 0.5, 0.45),     # Weak link, strong type
        ("CO_OCCURRENCE", 0.8, 0.32), # Strong link, weak type
        ("UNKNOWN", 1.0, 0.5)    # Default fallback (0.5)
    ]
    
    for rel_type, link_weight, expected in test_cases:
        type_modifier = 0.5
        for k, v in TYPE_WEIGHTS.items():
            if k in rel_type:
                type_modifier = v
                break
        
        final_score = link_weight * type_modifier
        print(f"Type: {rel_type:15} | Link: {link_weight} | Final: {final_score:.2f} | Expected: {expected}")
        
        # Verify filtering logic
        if final_score < 0.5:
             print(f"   -> FLAGGED: Score {final_score:.2f} < 0.5 (Confidently Wrong Protection)")

if __name__ == "__main__":
    test_prompt_format()
    test_weighting_logic()
