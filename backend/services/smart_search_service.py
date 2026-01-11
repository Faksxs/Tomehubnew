
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
from utils.text_utils import normalize_text, calculate_fuzzy_score

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

def perform_smart_search(query, firebase_uid):
    """
    Unified search with 3-Stage Pipeline:
    1. Exact Match (100 pts)
    2. Fuzzy Match (80-90 pts)
    3. Semantic Match (60-80 pts)
    
    Filtered: Excludes PDF, BOOK, EPUB (Layer 2 specific)
    """
    question = query.strip()
    if not question:
        return []

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Smart Search: '{question}'")
    
    # Get embedding for semantic search
    query_embedding = None
    try:
        query_embedding = get_embedding(question)
    except Exception as e:
        print(f"[WARNING] Embedding generation failed: {e}")
    
    try:
        conn = get_database_connection()
        cursor = conn.cursor()

        # 1. Normalize Query
        normalized_query = normalize_text(question)

        # 2. Vector Search (Semantic Candidates)
        # We fetch more candidates (top 50) to allow re-ranking
        # REFINED FILTER: Exclude raw PDF/BOOK/EPUB, BUT include them if they are annotated (contain 'Arsiv Notu', 'Tags', etc.)
        vector_sql = """
            SELECT content_chunk, title, source_type, normalized_content, page_number,
                   VECTOR_DISTANCE(vec_embedding, :bv_vec, COSINE) as dist
            FROM TOMEHUB_CONTENT
            WHERE firebase_uid = :bv_uid
            AND (
                source_type NOT IN ('PDF', 'BOOK', 'EPUB')
                OR normalized_content LIKE '%arsiv notu%'
                OR normalized_content LIKE '%tags:%'
                OR normalized_content LIKE '%highlight from%'
            )
            ORDER BY dist ASC
            FETCH FIRST 50 ROWS ONLY
        """
        
        # 3. Exact/Text Search (Keyword Candidates)
        # We look for exact normalized matches
        text_sql = """
            SELECT content_chunk, title, source_type, normalized_content, page_number, 0 as dist
            FROM TOMEHUB_CONTENT
            WHERE firebase_uid = :bv_uid
            AND (
                source_type NOT IN ('PDF', 'BOOK', 'EPUB')
                OR normalized_content LIKE '%arsiv notu%'
                OR normalized_content LIKE '%tags:%'
                OR normalized_content LIKE '%highlight from%'
            )
            AND normalized_content LIKE '%' || :bv_norm_query || '%'
            FETCH FIRST 20 ROWS ONLY
        """

        combined_candidates = {} # unique_key -> {row_data, scores}

        # Execute Vector Search
        if query_embedding:
            cursor.execute(vector_sql, {"bv_vec": query_embedding, "bv_uid": firebase_uid})
            for row in cursor.fetchall():
                content_clob, title, stype, norm_clob, pnum, dist = row
                content = content_clob.read() if content_clob else ""
                norm_content = norm_clob.read() if norm_clob else normalize_text(content)
                
                key = f"{title}_{content[:50]}"
                
                semantic_score = max(0, (1 - dist) * 100)
                
                combined_candidates[key] = {
                    'data': (content, title, stype, pnum),
                    'norm_content': norm_content,
                    'semantic_score': semantic_score,
                    'exact_score': 0,
                    'fuzzy_score': 0
                }

        # Execute Text Search
        cursor.execute(text_sql, {"bv_uid": firebase_uid, "bv_norm_query": normalized_query})
        for row in cursor.fetchall():
            content_clob, title, stype, norm_clob, pnum, _ = row
            content = content_clob.read() if content_clob else ""
            norm_content = norm_clob.read() if norm_clob else normalize_text(content)
            
            key = f"{title}_{content[:50]}"
            
            if key not in combined_candidates:
                combined_candidates[key] = {
                    'data': (content, title, stype, pnum),
                    'norm_content': norm_content,
                    'semantic_score': 0, # Was not found in vector top 50
                    'exact_score': 100,
                    'fuzzy_score': 0
                }
            else:
                combined_candidates[key]['exact_score'] = 100

        # --- STAGE 3: FUZZY RE-RANKING & SCORING ---
        final_results = []
        
        for key, item in combined_candidates.items():
            # Calculate Fuzzy Score
            fuzzy_score = calculate_fuzzy_score(normalized_query, item['norm_content'])
            item['fuzzy_score'] = fuzzy_score
            
            # Parsing for frontend display (needed for content-aware boosting)
            content, title, stype, pnum = item['data']
            clean_text, summary, tags, personal_comment = parse_and_clean_content(content)
            
            # --- CONTENT-AWARE SCORING LOGIC ---
            base_score = max(item['exact_score'], item['fuzzy_score'], item['semantic_score'])
            
            norm_title = normalize_text(title)
            norm_clean_text = normalize_text(clean_text)
            norm_personal_comment = normalize_text(personal_comment)
            norm_tags = normalize_text(tags)
            
            match_in_title = normalized_query in norm_title
            match_in_content = normalized_query in norm_clean_text
            match_in_personal_comment = normalized_query in norm_personal_comment
            match_in_tags = normalized_query in norm_tags
            
            content_boost = 0
            if match_in_personal_comment:
                content_boost += 50
            if match_in_content:
                content_boost += 30
            if match_in_tags:
                content_boost += 20
            
            # GENTLER PENALTY: Title-only match is just slightly lower (preferred content)
            if match_in_title and not (match_in_content or match_in_personal_comment):
                content_boost -= 15
            
            # Multi-signal bonus
            signal_count = sum([
                item['exact_score'] > 0,
                item['fuzzy_score'] > 70,
                item['semantic_score'] > 75
            ])
            if signal_count >= 2:
                content_boost += 10
            
            final_score = base_score + content_boost
            
            # Filter low quality results
            if final_score < 40:
                continue
                
            # Determine match type for frontend badges
            mtype = 'semantic'
            if item['exact_score'] == 100 or match_in_content or match_in_personal_comment:
                mtype = 'content_exact'
            elif item['fuzzy_score'] > 85:
                mtype = 'fuzzy'

            final_results.append({
                'content_chunk': clean_text if clean_text else content, # Fallback to raw if logic stripped everything
                'title': title,
                'source_type': stype,
                'page_number': pnum if pnum else 0,
                'score': final_score,
                'match_type': mtype,
                'summary': summary,
                'tags': tags,
                'personal_comment': personal_comment,
                'debug_info': f"E:{item['exact_score']} F:{item['fuzzy_score']} S:{int(item['semantic_score'])}"
            })
            
        # Sort by Final Score
        final_results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(final_results)} matches")
        
        # Return top 30
        return final_results[:30]

    except Exception as e:
        print(f"[ERROR] Smart Search failed: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        if 'conn' in locals():
            conn.close()
