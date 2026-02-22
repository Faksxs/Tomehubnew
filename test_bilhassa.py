import sys
import os
import asyncio
from dotenv import load_dotenv

# Setup path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

os.environ["DEBUG_VERBOSE_PIPELINE"] = "True"

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.search_system.strategies import ExactMatchStrategy, _contains_exact_term_boundary, _normalize_match_text
from utils.text_utils import deaccent_text

def test():
    query = "bilhassa"
    
    # 1. Simulate ExactMatchStrategy
    q_deaccented = deaccent_text(query)
    safe_term = q_deaccented.replace("'", "''")
    params = {"p_candidate_limit": 2500}
    
    # removed firebase_uid filter to just find it overall
    sql = """
        SELECT id, content_chunk, title, source_type, page_number, 
               tags, summary, "COMMENT",
               book_id, normalized_content, text_deaccented, firebase_uid
        FROM TOMEHUB_CONTENT
        WHERE text_deaccented LIKE '%bilhassa%'
        ORDER BY id DESC FETCH FIRST :p_candidate_limit ROWS ONLY 
    """
    
    print(f"Executing SQL for term '{safe_term}'...")
    
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            print(f"Found {len(rows)} raw rows from DB.")
            for r in rows:
                content = safe_read_clob(r[1])
                normalized_content = safe_read_clob(r[9])
                title = r[2]
                text_deaccented_val = safe_read_clob(r[10])
                firebase_uid = r[11]
                
                haystack = normalized_content or content
                match = _contains_exact_term_boundary(haystack, q_deaccented)
                
                print(f"\n--- ID: {r[0]} | Title: {title} | UID: {firebase_uid[:5]}... | Match: {match}")
                
                if not match:
                    print(f"Norm hay snippet: {_normalize_match_text(haystack)[:150]}...")
                    print(f"Query: {_normalize_match_text(q_deaccented)}")
                    
                    # Where is bilhassa?
                    idx = haystack.lower().find("bilhassa")
                    if idx != -1:
                        start = max(0, idx - 10)
                        end = min(len(haystack), idx + 20)
                        print(f"Context in haystack: '{haystack[start:end]}'")
                        
if __name__ == "__main__":
    test()
