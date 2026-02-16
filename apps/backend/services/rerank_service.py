import os
import json
from datetime import datetime
from dotenv import load_dotenv
from services.llm_client import MODEL_TIER_LITE, generate_text, get_model_for_tier

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

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

    from prompts.rerank_prompts import RERANK_PROMPT_TEMPLATE
    prompt = RERANK_PROMPT_TEMPLATE.format(query=query, candidates_text=candidates_text)

    try:
        model = get_model_for_tier(MODEL_TIER_LITE)
        result = generate_text(
            model=model,
            prompt=prompt,
            task="rerank",
            model_tier=MODEL_TIER_LITE,
            response_mime_type="application/json",
            timeout_s=30.0,
        )

        scores_list = json.loads(result.text)
        
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
