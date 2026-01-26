
import sys
import os

# Add parent directory to path (script is in apps/backend/scripts)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.epistemic_service import classify_chunk, extract_core_concepts

def verify_fix():
    print("Verifying classify_chunk fix...")
    
    # Test Keyword Extraction
    q = "vicdan degisen bir sey midir"
    real_keywords = extract_core_concepts(q)
    print(f"Query: {q}")
    print(f"Extracted Keywords: {real_keywords}")
    
    if "vicdan" in real_keywords:
        print("✅ SUCCESS: 'vicdan' extracted correctly")
    else:
        print("❌ FAILURE: 'vicdan' NOT extracted!")
        
    # Mock data
    chunk = {
        "title": "Test Note",
        "content_chunk": "Vicdan, iyiyi kötüden ayırma yeteneğidir.",
        "epistemic_features": []
    }
    keywords = real_keywords # Use real keywords
    
    # Run classification
    print(f"Before: {chunk.get('epistemic_level', 'MISSING')}")
    
    returned_level = classify_chunk(keywords, chunk)
    
    print(f"Returned: {returned_level}")
    print(f"After: {chunk.get('epistemic_level', 'MISSING')}")
    
    if chunk.get('epistemic_level') == returned_level:
        print("✅ SUCCESS: Level is stored on chunk!")
    else:
        print("❌ FAILURE: Level is NOT stored on chunk!")

if __name__ == "__main__":
    verify_fix()
