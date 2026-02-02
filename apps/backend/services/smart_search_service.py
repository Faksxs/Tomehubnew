
import os
import sys
import oracledb
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
import json
import re

# Load environment variables - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

from services.embedding_service import get_embedding
from utils.text_utils import normalize_text, calculate_fuzzy_score, deaccent_text, get_lemmas, normalize_canonical
from utils.spell_checker import get_spell_checker
try:
    from services.query_service import intelligent_query_expansion
except ImportError:
    def intelligent_query_expansion(q): return {"corrected_query": q, "synonyms": [], "keywords": []}
from rank_bm25 import BM25Okapi


from infrastructure.db_manager import DatabaseManager

# --- CONSTANTS ---
STOP_WORDS = {
    've', 'veya', 'ile', 'ama', 'fakat', 'ancak', 'lakin', 'ki', 'de', 'da', 
    'mi', 'mu', 'mı', 'mü', 'bir', 'bu', 'şu', 'o', 'ben', 'sen', 'biz', 
    'siz', 'onlar', 'gibi', 'için', 'diye', 'en', 'daha', 'çok', 'her', 
    'hangi', 'ne', 'kim', 'bunu', 'şunu', 'böyle', 'şöyle'
}

DANGEROUS_LEMMAS = {
    'ol', 'et', 'yap', 'dur', 'ver', 'al', 'gel', 'git', 'kal', 
    'bulun', 'olmak', 'etmek', 'yapmak'
}

TIER_CEILINGS = {
    'exact_deaccented': 150, # Practically unlimited
    'lemma_exact': 110,      # Cap lemma matches
    'lemma_fuzzy': 100,      # Cap fuzzy matches
    'semantic': 85           # Cap semantic matches (strict)
}


def parse_and_clean_content(content):
    """
    Parses the content_chunk to extract metadata and clean the main text.
    Returns (clean_text, summary, tags, personal_comment)
    """
    if not content:
        return "", "", "", ""

    summary = ""
    tags = ""
    personal_comment = ""
    
    # 1. Extract Personal Comment (Arsiv Notu) - Check this FIRST because it's usually at the end
    # Match "Note: Arsiv Notu" or just "Arsiv Notu" and everything that follows
    comment_pattern = re.compile(r'(?:Note:\s*)?Arsiv Notu\s*[:\-\s]*(.*)', re.IGNORECASE | re.DOTALL)
    comment_match = comment_pattern.search(content)
    if comment_match:
        personal_comment = comment_match.group(1).strip()
        # Remove the comment part from the main content
        content = content[:comment_match.start()].strip()

    # 2. Extract Tags (case insensitive, multiline)
    tags_match = re.search(r'^Tags:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if tags_match:
        tags = tags_match.group(1).strip()
        content = re.sub(r'^Tags:\s*.+$', '', content, flags=re.MULTILINE | re.IGNORECASE)

    # 3. Extract Notes (which we'll call Summary)
    summary_match = re.search(r'^Notes:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if summary_match:
        summary = summary_match.group(1).strip()
        content = re.sub(r'^Notes:\s*.+$', '', content, flags=re.MULTILINE | re.IGNORECASE)

    # 4. Strip final prefixes (Title, Author, Highlight from...)
    patterns = [
        r'^Highlight from .+?:\s*',
        r'^Title:\s*.+?(\n|$)',
        r'^Author:\s*.+?(\n|$)',
        r'^Note:\s*',
    ]
    
    for pattern in patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE | re.IGNORECASE)

    clean_text = content.strip()
    return clean_text, summary, tags, personal_comment

def create_turkish_fuzzy_pattern(query):
    """Legacy compatibility: Returns normalized query as list."""
    return [normalize_text(query)]

def generate_query_variations(query: str) -> list[str]:
    """
    Generates 3 semantic variations of the user query using Gemini.
    """
    if not query:
        return []
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Generating query variations for: '{query}'")
    
    prompt = f"""You are an AI search optimizer.
    Generate 3 alternative versions of the following search query to improve retrieval recall.
    Focus on synonyms, related concepts, and removing ambiguity.
    
    Query: "{query}"
    
    Output Format: JSON list of strings ONLY.
    Example: ["variation 1", "variation 2", "variation 3"]
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Task 2.4: Add timeout
        response = model.generate_content(prompt, request_options={'timeout': 30})
        text = response.text.strip()
        
        # Clean markdown
        if "```json" in text:
            text = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL).group(1)
        elif "```" in text:
            text = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL).group(1)
            
        variations = json.loads(text)
        if isinstance(variations, list):
            return variations[:3]
        return [query]
        
    except Exception as e:
        print(f"[WARNING] Query expansion failed: {e}")
        return [query]

def score_with_bm25(documents: list[str], query: str) -> list[float]:
    """
    Scores a list of documents against a query using BM25.
    Uses Zeyrek lemmatization to handle Turkish morphology.
    Returns a list of scores corresponding to the documents.
    """
    if not documents or not query:
        return []
    
    def _lemmatize_tokens(text: str) -> list:
        """Tokenize with lemmatization for BM25."""
        lemmas = get_lemmas(text)
        if lemmas:
            return lemmas
        # Fallback: normalized split
        return normalize_text(text).split()
    
    tokenized_corpus = [_lemmatize_tokens(doc) for doc in documents]
    tokenized_query = _lemmatize_tokens(query)
    
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenized_query)
    return list(scores)


# Import Search System
from services.search_system.orchestrator import SearchOrchestrator
from services.search_system.search_utils import compute_rrf # Re-export for compatibility

def perform_smart_search(query, firebase_uid, book_id=None, intent='SYNTHESIS', search_depth='normal', resource_type=None, limit=None, offset=0):
    """
    Delegates to the new SearchOrchestrator (Phase 3 Architecture).
    search_depth: 'normal' (default, limit 50) or 'deep' (limit 100)
    """
    try:
        from services.cache_service import get_cache
        cache = get_cache()
        
        # Determine limit based on depth if not explicitly provided
        if limit is None:
            limit = 100 if search_depth == 'deep' else 50
        
        # Initialize Orchestrator with embedding function and cache
        orchestrator = SearchOrchestrator(embedding_fn=get_embedding, cache=cache)
        result = orchestrator.search(query, firebase_uid, limit=limit, offset=offset, book_id=book_id, intent=intent, resource_type=resource_type)
        
        if result is None:
            print("[ERROR] Orchestrator returned None")
            return [], {}
            
        return result
        
    except Exception as e:
        print(f"[ERROR] Smart Search Failed: {e}")
        import traceback
        traceback.print_exc()
        return [], {}

def parse_metadata_from_row(row):
    # Helper to clean content
    # row = (content_chunk, title, source_type, page_number, normalized_content, personal_comment)
    content_clob = row[0]
    content = content_clob if isinstance(content_clob, str) else (content_clob.read() if content_clob else "")
    
    # Parse existing cleaners
    clean_text, summary, tags, p_comment = parse_and_clean_content(content)
    # If personal_comment column exists and is not null, prefer it?
    # The SQL selects personal_comment from DB (if it exists separate).
    # Wait, TOMEHUB_CONTENT doesn't have personal_comment column?
    # Script debug earlier: "SELECT ... normalized_content" - no personal_comment.
    # I added personal_comment to SELECT in Stage 1/2. Does it exist?
    # Backfill script didn't add it.
    # Check debug_smart_search.py script output: 
    # "SELECT id, title, source_type, normalized_content, content_chunk"
    # It does NOT have personal_comment column explicitly. It's inside content_chunk.
    # Removing `personal_comment` from SQL to avoid error.
    return clean_text, summary, tags, p_comment

def format_results(results_map, query_tokens=None):
    """
    Advanced result formatting with Token Frequency Boost and Location-Aware Scoring.
    
    Scoring Formula:
    final_score = base_score + token_freq_boost + location_boost + multi_signal_bonus
    
    - token_freq_boost: +5 per unique query token found in content (max +25)
    - location_boost: +20 personal_comment, +15 tags, +10 title
    - multi_signal_bonus: +10 if found by multiple stages
    """
    if query_tokens is None:
        query_tokens = []
    
    final = []
    for key, item in results_map.items():
        row = item['data']
        content_val = item['content']
        base_score = item['score']
        match_type = item['type']
        
        # Parse content
        clean_text, summary, tags, p_comment_extracted = parse_and_clean_content(content_val)
        title = row[2] if len(row) > 2 else "" # row is (id, content, title, ...)
        
        # Determine ID safely
        # Strategies now return: id, content, title, source, page...
        # So row[0] is ID.
        content_id = row[0] if len(row) > 0 else None
        
        # --- TOKEN FREQUENCY BOOST ---
        token_freq_boost = 0
        if query_tokens:
            # Normalize content for token matching
            norm_content = normalize_text(content_val).lower()
            
            # Filter stopwords from query tokens for TF
            valid_tokens = [t for t in query_tokens if t.lower() not in STOP_WORDS]
            
            tokens_found = sum(1 for t in valid_tokens if t.lower() in norm_content)
            token_freq_boost = min(tokens_found * 5, 25)  # Cap at +25
        
        # --- LOCATION BOOST ---
        location_boost = 0
        norm_title = normalize_text(title).lower()
        norm_p_comment = normalize_text(p_comment_extracted).lower() if p_comment_extracted else ""
        norm_tags = normalize_text(tags).lower() if tags else ""
        
        for token in query_tokens:
            t_lower = token.lower()
            if t_lower in STOP_WORDS: continue # Skip stopwords for location boost too? Yes.
            
            if t_lower in norm_p_comment:
                location_boost = max(location_boost, 20)  # Personal comment is highest priority
            if t_lower in norm_tags:
                location_boost = max(location_boost, 15)
            if t_lower in norm_title:
                location_boost = max(location_boost, 10)
        
        # --- MULTI-SIGNAL BONUS ---
        # Check if this item was found by multiple match types (stored in item.get('signals', []))
        # For now, we just check if there was a correction involved
        multi_signal_bonus = 0
        if item.get('corrected_match'):
            multi_signal_bonus = 5
        
        # --- FINAL SCORE ---
        final_score = base_score + token_freq_boost + location_boost + multi_signal_bonus
        
        # --- TIER CEILINGS ---
        # Apply strict score caps based on match type
        ceiling = TIER_CEILINGS.get(match_type, 150)
        # Refined types (tag_match, etc) still fall under their base category for ceiling purposes
        # But wait, match_type is updated below for display. We need original match type.
        # item['type'] has the original type (exact_deaccented, lemma_exact, etc)
        original_type = item['type']
        ceiling = TIER_CEILINGS.get(original_type, 150)
        
        if final_score > ceiling:
            # print(f"[DEBUG] Score capped for {title[:20]}: {final_score} -> {ceiling} (Type: {original_type})")
            final_score = ceiling
        
        # Determine refined match type for badges
        refined_type = match_type
        if location_boost >= 20:
            refined_type = 'insight_match'
        elif location_boost >= 15:
            refined_type = 'tag_match'
        
        # Check if query appears in the main content (Highlight section)
        # This is used for secondary sorting only - not for scoring
        in_content = False
        if query_tokens:
            norm_clean = normalize_text(clean_text).lower()
            for token in query_tokens:
                if len(token) >= 3 and token.lower() in norm_clean:
                    in_content = True
                    break
        
        final.append({
            'id': content_id,
            'title': title,
            'content_chunk': clean_text,
            'source_type': row[3] if len(row) > 3 else "NOTE",
            'page_number': row[4] if len(row) > 4 and row[4] else 0,
            'score': final_score,
            'match_type': refined_type,
            'summary': summary,
            'tags': tags,
            'personal_comment': p_comment_extracted,
            'in_content': in_content,
            'debug_info': f"Base:{base_score:.0f} +TF:{token_freq_boost} +Loc:{location_boost} -> Final:{final_score:.0f} (Cap: {ceiling})"
        })
    
    # Sort by: 1) Content match (primary - highlight priority), 2) Score (secondary)
    final.sort(key=lambda x: (x.get('in_content', False), x['score']), reverse=True)
    return final[:50]

