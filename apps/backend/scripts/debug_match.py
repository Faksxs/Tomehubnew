
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.epistemic_service import contains_keyword, normalize_for_matching

def debug_matching():
    print("Debugging keyword matching...")
    
    # Real content from user screenshot (Source 12)
    chunk_text = "Yiğidi kılıç kesmez bir kötü söz öldürür... vicdan azabı..."
    
    keyword = "vicdan"
    
    print(f"Chunk: {chunk_text}")
    print(f"Keyword: {keyword}")
    
    norm_chunk = normalize_for_matching(chunk_text)
    norm_kw = normalize_for_matching(keyword)
    
    print(f"Norm Chunk: {norm_chunk}")
    print(f"Norm Keyword: {norm_kw}")
    
    match = contains_keyword(chunk_text, keyword)
    print(f"Wrapper Match Result: {match}")
    
    # Replicate calculate_answerability_score logic
    if keyword in norm_chunk:
        print("Simple substring match: YES")
    else:
        print("Simple substring match: NO")

if __name__ == "__main__":
    debug_matching()
