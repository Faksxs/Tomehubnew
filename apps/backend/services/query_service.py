
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load env variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def intelligent_query_expansion(user_query: str) -> dict:
    """
    Uses a fast LLM (Gemini Flash) to pre-process the user query.
    1. Fixes typos contextually.
    2. Expands with domain-specific synonyms.
    3. Extracts core keywords.
    """
    if not user_query or len(user_query) < 3:
        return {"corrected": user_query, "keywords": [], "expanded": []}
        
    prompt = f"""
    Act as a Search Query Optimizer.
    Input Query: "{user_query}"
    
    Tasks:
    1. Correct any typos (context-aware). "Enemia" -> "Enema".
    2. Suggest 2-3 synonyms or related terms for the core concept (in Turkish or English depending on input).
    3. Extract list of core keywords (lemmatized).
    
    Output JSON ONLY:
    {{
        "corrected_query": "string",
        "synonyms": ["str", "str"],
        "keywords": ["str", "str"]
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Task 2.4: Add timeout
        response = model.generate_content(prompt, request_options={'timeout': 20})
        text = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(text)
        return data
    except Exception as e:
        print(f"[QueryService] Error: {e}")
        # Fallback to simple
        return {
            "corrected_query": user_query,
            "synonyms": [],
            "keywords": user_query.split()
        }

if __name__ == "__main__":
    # Test
    q = "Kant'ın ahlak yasası ve imperatif"
    print(intelligent_query_expansion(q))
