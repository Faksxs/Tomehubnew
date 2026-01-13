import os
import json
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def rerank_candidates(query: str, candidates: list[dict], top_n: int = 10) -> list[dict]:
    """
    Re-ranks a list of candidates using a Flash LLM as a Cross-Encoder.
    Returns the top_n most relevant candidates.
    """
    if not candidates:
        return []

    # Limit input to avoid token context overflow (rerank top 20-30 max)
    input_candidates = candidates[:30]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Re-ranking {len(input_candidates)} candidates...")

    # Prepare prompt
    candidates_text = ""
    for idx, c in enumerate(input_candidates):
        snippet = c['content'][:300].replace("\n", " ") # Truncate for prompt efficiency
        candidates_text += f"[{idx}] {c['title']} (p.{c['page']}): {snippet}\n"

    prompt = f"""
    You are an expert Search Relevance Ranker.
    
    Query: "{query}"
    
    Task: Rank the following candidates based on their relevance to the query.
    - Rate each candidate from 0.0 (irrelevant) to 1.0 (highly relevant).
    - Consider semantic meaning, not just keyword overlap.
    - Return ONLY a JSON list of objects: {{"index": <int>, "score": <float>}}.
    
    Candidates:
    {candidates_text}
    """

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # JSON mode forced via response_mime_type if supported, or just instruction
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        
        scores_list = json.loads(response.text)
        
        # Map back to original objects
        reranked_pool = []
        for item in scores_list:
            idx = item.get('index')
            score = item.get('score', 0.0)
            
            if idx is not None and 0 <= idx < len(input_candidates):
                cand = input_candidates[idx]
                cand['rerank_score'] = score
                reranked_pool.append(cand)
        
        # Sort by new score
        reranked_pool.sort(key=lambda x: x['rerank_score'], reverse=True)
        
        # Fallback: if some candidates weren't returned by LLM, append them with 0 score (or drop them)
        # Here we'll just return the re-ranked ones.
        
        return reranked_pool[:top_n]

    except Exception as e:
        print(f"[ERROR] Re-ranking failed: {e}")
        # Fallback: Return original order
        return input_candidates[:top_n]
