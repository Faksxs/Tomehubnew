
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

def get_database_connection():
    """Get Oracle database connection with health check."""
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN", "tomehubdb_high")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    try:
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet_location,
            wallet_location=wallet_location,
            wallet_password=password
        )
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        raise

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
        response = model.generate_content(prompt)
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
    Returns a list of scores corresponding to the documents.
    """
    if not documents or not query:
        return []
        
    tokenized_corpus = [normalize_text(doc).split() for doc in documents]
    tokenized_query = normalize_text(query).split()
    
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(tokenized_query)
    return list(scores)

def compute_rrf(rankings: list[list[str]], k=60) -> dict:
    """
    Computes Reciprocal Rank Fusion scores.
    Args:
        rankings: List of ranked lists (each list contains item IDs/Keys)
        k: Constant to dampen high ranks (default 60)
    Returns:
        Dictionary {item_key: rrf_score}
    """
    rrf_map = {}
    
    for rank_list in rankings:
        for rank, item_key in enumerate(rank_list):
            if item_key not in rrf_map:
                rrf_map[item_key] = 0.0
            rrf_map[item_key] += 1 / (k + rank + 1)
            
    return rrf_map


def perform_smart_search(query, firebase_uid):
    """
    New Waterfall Search Architecture (Phase 1):
    1. Prep: De-accent & Lemmatize.
    2. Stage 1: Fast De-accented Match (Exact-ish). IF hits > 5 -> Return.
    3. Stage 2: Lemma Match (High Recall). IF hits > 10 -> Return.
    4. Stage 3: Semantic Vector Search (Fallback).
    5. Fusion: RRF + Re-rank.
    """
    question = query.strip()
    if not question:
        return []

    t_start = datetime.now()
    print(f"[{t_start.strftime('%H:%M:%S')}] Smart Search: '{question}'")
    
    # --- 0. PREP NLP ---
    # --- 0. PREP NLP ---
    
    # AI Query Expansion (LLM)
    # This adds ~500ms but provides context-aware correction & synonyms
    ai_prep = intelligent_query_expansion(question)
    corrected = ai_prep.get("corrected_query", question)
    synonyms = ai_prep.get("synonyms", [])
    
    # Fallback to local spell checker if LLM didn't change anything (double check)
    if corrected == question:
        checker = get_spell_checker()
        corrected_local = checker.correct(question)
        if corrected_local != question and len(corrected_local) > 2:
            corrected = corrected_local

    has_correction = corrected != question and len(corrected) > 2
    
    if has_correction:
        print(f"[SMART SEARCH] AI/Typo Correction: '{question}' -> '{corrected}'")
    
    if synonyms:
        print(f"[SMART SEARCH] AI Synonyms: {synonyms}")
    
    # De-accent (Both original and corrected)
    q_deaccented = deaccent_text(question)
    q_deaccented_corr = deaccent_text(corrected) if has_correction else None
    
    # Lemmas (Both)
    q_lemmas = get_lemmas(question)
    if has_correction:
        q_lemmas.extend(get_lemmas(corrected))
    
    # Add Synonyms to Lemmas bucket for broader matching
    if synonyms:
        for syn in synonyms:
            q_lemmas.extend(get_lemmas(syn))
            
    q_lemmas = list(set(q_lemmas))
        
    print(f"[DEBUG] De-accented: '{q_deaccented}', Corrected: '{q_deaccented_corr}', Lemmas: {q_lemmas}")
    
    # Extract query tokens for Token Frequency Boost
    query_tokens = q_deaccented.split() if q_deaccented else []
    if q_deaccented_corr:
        query_tokens.extend(q_deaccented_corr.split())
    query_tokens = list(set(query_tokens))  # Unique tokens
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Common Filter Logic
    # Note: filters check normalized_content for tags, which is fine (it's clob)
    FILTER_SQL = """
        AND (
            source_type NOT IN ('PDF', 'BOOK', 'EPUB')
            OR normalized_content LIKE '%arsiv notu%'
            OR normalized_content LIKE '%tags:%'
            OR normalized_content LIKE '%highlight from%'
        )
    """

    results_map = {} # key -> {data:..., score:...}

    try:
        # --- STAGE 1: DE-ACCENTED EXACT MATCH (Fast) ---
        # Matches "kufur" against "text_deaccented" column
        # ALSO check corrected version if it exists
        
        search_terms = [q_deaccented]
        if q_deaccented_corr and q_deaccented_corr != q_deaccented:
            search_terms.append(q_deaccented_corr)
            
        for term in search_terms:
            sql_stage1 = f"""
                SELECT content_chunk, title, source_type, page_number, normalized_content
                FROM TOMEHUB_CONTENT
                WHERE firebase_uid = :bv_uid
                {FILTER_SQL}
                AND text_deaccented LIKE '%' || :bv_q || '%'
                FETCH FIRST 20 ROWS ONLY
            """
            cursor.execute(sql_stage1, {"bv_uid": firebase_uid, "bv_q": term})
            rows_s1 = cursor.fetchall()
            
            print(f"[DEBUG] Stage 1 (Term: {term}) found {len(rows_s1)} hits.")
            
            for r in rows_s1:
                content = r[0].read() if r[0] else ""
                key = f"{r[1]}_{content[:50]}"
                if key not in results_map:
                    results_map[key] = {
                        'data': r,
                        'content': content,
                        'score': 100 if term == q_deaccented else 90, # Slight penalty for correction
                        'type': 'exact_deaccented'
                    }
            
            
            # Smart Waterfall: Check Quality + Quantity
            # Only return if we have definitive matches (Score > 115)
            # This requires formatting them first to see boosts
            current_results = format_results(results_map, query_tokens)
            high_quality_hits = sum(1 for r in current_results if r['score'] > 115)
            
            if high_quality_hits >= 3:
                print(f"[DEBUG] Stage 1 sufficient (Found {high_quality_hits} High-Quality matches). Returning.")
                return current_results

        # --- STAGE 2: LEMMA MATCH (Exact + Fuzzy Bridge) ---
        # Gate: Only use lemma matching for queries >= 4 chars (avoid short query flooding)
        if q_lemmas and len(question) >= 4:
            # Filter Dangerous Lemmas (e.g. 'ol', 'et')
            safe_lemmas = [L for L in q_lemmas if L.lower() not in DANGEROUS_LEMMAS]
            
            if not safe_lemmas:
                print("[DEBUG] All lemmas filtered as dangerous (stop words/verbs). Skipping Stage 2.")
            else:
                # 2A: Exact Lemma Match (Score: 95)
                for lemma in safe_lemmas:
                    sql_stage2 = f"""
                    SELECT content_chunk, title, source_type, page_number, normalized_content, lemma_tokens
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :bv_uid
                    {FILTER_SQL}
                    AND lemma_tokens LIKE '%' || :bv_lemma || '%'
                    FETCH FIRST 20 ROWS ONLY
                """
                cursor.execute(sql_stage2, {"bv_uid": firebase_uid, "bv_lemma": f'"{lemma}"'})
                rows_s2 = cursor.fetchall()
                print(f"[DEBUG] Stage 2A (Exact Lemma: {lemma}) found {len(rows_s2)} hits.")
                
                for r in rows_s2:
                    content = r[0].read() if r[0] else ""
                    key = f"{r[1]}_{content[:50]}"
                    if key not in results_map:
                         results_map[key] = {
                            'data': r[:-1],  # Exclude lemma_tokens from data
                            'content': content,
                            'score': 95,  # Exact lemma match
                            'type': 'lemma_exact'
                        }
            
            # 2B: Fuzzy Lemma Bridge (Score: 85)
            # Find content where stored lemmas are SIMILAR to query lemmas (e.g., kısıtla ↔ kısıtlan)
            # Only if Stage 2A didn't find much
            if len(results_map) < 5:
                # Fetch a broader set of candidates for fuzzy matching
                sql_fuzzy_candidates = f"""
                    SELECT content_chunk, title, source_type, page_number, normalized_content, lemma_tokens
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :bv_uid
                    {FILTER_SQL}
                    AND lemma_tokens IS NOT NULL
                    FETCH FIRST 50 ROWS ONLY
                """
                cursor.execute(sql_fuzzy_candidates, {"bv_uid": firebase_uid})
                fuzzy_rows = cursor.fetchall()
                
                from rapidfuzz import fuzz
                import json
                
                for r in fuzzy_rows:
                    content = r[0].read() if r[0] else ""
                    key = f"{r[1]}_{content[:50]}"
                    
                    if key in results_map:
                        continue  # Already matched
                    
                    # Parse stored lemmas
                    stored_lemmas_raw = r[5].read() if r[5] else "[]"
                    try:
                        stored_lemmas = json.loads(stored_lemmas_raw)
                    except:
                        stored_lemmas = []
                    
                    # Check fuzzy similarity between query lemmas and stored lemmas
                    best_similarity = 0
                    for q_lemma in safe_lemmas: # Use safe_lemmas here too
                        for s_lemma in stored_lemmas:
                            if len(q_lemma) >= 4 and len(s_lemma) >= 4:  # Min length gate
                                sim = fuzz.ratio(q_lemma, s_lemma)
                                if sim > best_similarity:
                                    best_similarity = sim
                    
                    # Conservative threshold: 85% similarity, score 85 points
                    if best_similarity >= 85:
                        results_map[key] = {
                            'data': r[:-1],
                            'content': content,
                            'score': 85,  # Fuzzy lemma bridge (below exact)
                            'type': 'lemma_fuzzy'
                        }
                        print(f"[DEBUG] Stage 2B (Fuzzy Lemma) matched: {r[1][:30]}... (sim: {best_similarity}%)")
        
        # Smart Waterfall Stage 2
        # If we have gathered enough high-quality matches by now
        current_results = format_results(results_map, query_tokens) # Re-calc with new additions
        high_quality_hits = sum(1 for r in current_results if r['score'] >= 105) # Lower threshold for Stage 2
        
        if high_quality_hits >= 5: # Need more count if score is lower
             print(f"[DEBUG] Stage 2 sufficient ({high_quality_hits} HQ hits). Returning.")
             return current_results

        # --- STAGE 3: VECTOR / SEMANTIC (Fallback) ---
        print("[DEBUG] Fallback to Vector Search...")
        try:
            q_emb = get_embedding(question)
            if q_emb:
                 sql_vec = f"""
                    SELECT content_chunk, title, source_type, page_number, normalized_content,
                           VECTOR_DISTANCE(vec_embedding, :bv_vec, COSINE) as dist
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :bv_uid
                    {FILTER_SQL}
                    ORDER BY dist ASC
                    FETCH FIRST 30 ROWS ONLY
                """
                 cursor.execute(sql_vec, {"bv_uid": firebase_uid, "bv_vec": q_emb})
                 rows_vec = cursor.fetchall()
                 for r in rows_vec:
                     # r has 6 items (removed comment), last is dist
                     content = r[0].read() if r[0] else ""
                     key = f"{r[1]}_{content[:50]}"
                     dist = r[5]
                     sem_score = max(0, (1 - dist) * 100)
                     
                     if key not in results_map:
                         results_map[key] = {
                             'data': r[:-1], 
                             'content': content,
                             'score': sem_score,
                             'type': 'semantic'
                         }
        except Exception as e:
            print(f"[WARNING] Vector search error: {e}")

        # Final Return (Mixed)
        return format_results(results_map, query_tokens)

    except Exception as e:
        print(f"[ERROR] Smart Search Failed: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        conn.close()

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
        title = row[1] if len(row) > 1 else ""
        
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
            'title': title,
            'content_chunk': clean_text,
            'source_type': row[2] if len(row) > 2 else "NOTE",
            'page_number': row[3] if len(row) > 3 and row[3] else 0,
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

