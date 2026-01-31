
import os
import json
import re
import oracledb
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# Load environment - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

from services.embedding_service import get_embedding


from infrastructure.db_manager import DatabaseManager, safe_read_clob

def extract_concepts_and_relations(text: str):
    """Uses Gemini to extract structured concepts and their connections."""
    if not text or len(text) < 50:
        return [], []
        
    from prompts.graph_prompts import GRAPH_EXTRACTION_PROMPT
    prompt = GRAPH_EXTRACTION_PROMPT.format(text=text)
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Task 2.4: Add timeout
        response = model.generate_content(prompt, request_options={'timeout': 45})
        text_resp = response.text.strip()
        
        print(f"[DEBUG] Raw Response: {text_resp[:100]}...")
        
        # Clean potential markdown
        if "```json" in text_resp:
            text_resp = re.search(r'```json\s*(.*?)\s*```', text_resp, re.DOTALL).group(1)
        elif "```" in text_resp:
            text_resp = re.search(r'```\s*(.*?)\s*```', text_resp, re.DOTALL).group(1)
            
        data = json.loads(text_resp)
        return data.get('concepts', []), data.get('relations', [])
    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}")
        return [], []

def save_to_graph(content_id: int, concepts: list, relations: list):
    """Saves extracted data to Oracle Graph tables."""
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                concept_map = {} # name -> id
                
                # 1. Save Concepts & Link to Chunk
                for name in concepts:
                    name_clean = name.strip()[:255]
                    if not name_clean: continue
                    
                    # Upsert Concept (Use a simpler MERGE or separate check)
                    try:
                        # First try to insert
                        cursor.execute("""
                            INSERT INTO TOMEHUB_CONCEPTS (name, concept_type)
                            VALUES (:name, 'AUTOMATIC')
                        """, {"name": name_clean})
                    except oracledb.IntegrityError:
                        # Already exists, just continue
                        pass
                    
                    # Get ID
                    cursor.execute("SELECT id FROM TOMEHUB_CONCEPTS WHERE name = :name", {"name": name_clean})
                    row = cursor.fetchone()
                    if not row: continue
                    cid = row[0]
                    concept_map[name_clean] = cid
                    
                    # Link to Chunk
                    try:
                        cursor.execute("""
                            INSERT INTO TOMEHUB_CONCEPT_CHUNKS (concept_id, content_id)
                            VALUES (:cid, :ch_id)
                        """, {"cid": cid, "ch_id": content_id})
                    except oracledb.IntegrityError:
                        pass # Already linked
                    
                # 2. Save Relations
                for rel in relations:
                    # Expecting [src, type, dst, confidence]
                    if len(rel) >= 3:
                        src_name = rel[0]
                        rel_type = rel[1]
                        dst_name = rel[2]
                        weight = float(rel[3]) if len(rel) > 3 else 1.0
                        
                        sid = concept_map.get(src_name)
                        did = concept_map.get(dst_name)
                        
                        if sid and did:
                            cursor.execute("""
                                INSERT INTO TOMEHUB_RELATIONS (src_id, dst_id, rel_type, weight)
                                VALUES (:sid, :did, :rtype, :wght)
                            """, {"sid": sid, "did": did, "rtype": rel_type[:100], "wght": weight})
                            
                conn.commit()
    except Exception as e:
        print(f"[ERROR] DB Save failed: {e}")

def find_concepts_by_text(text: str, cursor) -> list[int]:
    """
    Finds concept IDs that match the query text (case-insensitive fuzzy-ish).
    """
    # 1. Exact/Like Match
    clean_text = text.lower().strip()
    cursor.execute("""
        SELECT id FROM TOMEHUB_CONCEPTS 
        WHERE LOWER(name) LIKE :term
        FETCH FIRST 5 ROWS ONLY
    """, {"term": f"%{clean_text}%"})
    
    ids = [row[0] for row in cursor.fetchall()]
    return ids

def get_graph_candidates(query_text: str, firebase_uid: str) -> list[dict]:
    """
    GraphRAG Retrieval:
    1. Identify concepts in Query.
    2. Traverse interactions (Query -> Concept A -> Related Concept B).
    3. Fetch chunks linked to Concept B.
    
    Returns list of chunks formatted for search_service.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- GRAPHRAG RETRIEVAL: '{query_text}' ---")
    
    candidates = []
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Step 1: Map Query to Entry Concepts
                # Strategy A: Use LLM to extract clean concepts (Costly but accurate)
                # Strategy B: Simple keyword match against Concept Table (Fast) -> Using B for now + LLM fallback if empty
                
                # Try simple match first
                concept_ids = find_concepts_by_text(query_text, cursor)
                
                # If no direct match, maybe use the expanded query terms from search_service?
                # For this function, let's keep it self-contained.
                
                if not concept_ids:
                     # Fallback: Extract via Gemini if simple match fails
                     concepts, _ = extract_concepts_and_relations(query_text)
                     for c in concepts:
                         concept_ids.extend(find_concepts_by_text(c, cursor))
                
                concept_ids = list(set(concept_ids)) # Dedupe
                
                if not concept_ids:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No concepts found for graph traversal.")
                    return []
                    
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found Entry Concepts IDs: {concept_ids}")

                # Step 2: Traversal (1-Hop or 2-Hop)
                # Find concepts directly related to the entry concepts
                # Query -> [Concept A] --(relation)--> [Concept B] -> [Chunks for B]
                
                # We want chunks linked to A (direct) AND B (related)
                # Weight linked chunks: Direct (1.0), Related (0.5)
                
                # SQL to get both neighbors and their chunks
                # This joins: ENTRY_IDS -> RELATIONS -> NEIGHBOR_CONCEPTS -> CHUNK_LINKS -> CHUNKS
                
                sql = """
                    SELECT DISTINCT 
                        ct.content_chunk, ct.page_number, ct.title, ct.source_type,
                        c_neighbor.name as related_concept,
                        r.rel_type,
                        r.weight
                    FROM TOMEHUB_RELATIONS r
                    JOIN TOMEHUB_CONCEPTS c_neighbor ON (r.dst_id = c_neighbor.id OR r.src_id = c_neighbor.id)
                    JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c_neighbor.id = cc.concept_id
                    JOIN TOMEHUB_CONTENT ct ON cc.content_id = ct.id
                    WHERE (r.src_id IN ({SEQ}) OR r.dst_id IN ({SEQ}))
                    AND ct.firebase_uid = :p_uid
                    AND c_neighbor.id NOT IN ({SEQ}) 
                    FETCH FIRST 15 ROWS ONLY
                """
                
                # Format the IN clause params SAFE WAY
                bind_names = [f":id_{i}" for i in range(len(concept_ids))]
                bind_clause = ",".join(bind_names)
                
                safe_sql = sql.replace("{SEQ}", bind_clause)
                
                params = {"p_uid": firebase_uid}
                for i, cid in enumerate(concept_ids):
                    params[f"id_{i}"] = cid
                
                cursor.execute(safe_sql, params)
                rows = cursor.fetchall()
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(rows)} neighbor chunks via Graph.")
                
                # Relation Type Weighting Table
                TYPE_WEIGHTS = {
                    'DIRECT_CITATION': 1.0, 'QUOTES': 1.0,
                    'IS_A': 0.9, 'DEFINES': 0.9, 'PART_OF': 0.9,
                    'SEMANTIC_SIMILARITY': 0.7, 'SYNONYM': 0.7,
                    'RELATED_TO': 0.6, 'ASSOCIATED_WITH': 0.6,
                    'CO_OCCURRENCE': 0.4
                }

                for r in rows:
                    chunk_text = safe_read_clob(r[0])
                    page_num = r[1]
                    title = r[2]
                    source_type = r[3]
                    neighbor_name = r[4]
                    rel_type = r[5]
                    link_weight = float(r[6]) if r[6] is not None else 1.0
                    
                    # Calculate Composite Score
                    # Use substring match for types (e.g., "IS_A_TYPE" matches "IS_A")
                    type_modifier = 0.5 # Default fallback
                    
                    # Exact or partial match
                    r_upper = rel_type.upper()
                    for k, v in TYPE_WEIGHTS.items():
                        if k in r_upper:
                            type_modifier = v
                            break
                            
                    final_graph_score = link_weight * type_modifier
                    
                    # Filtering: "Confident but wrong" check
                    if final_graph_score < 0.5:
                        continue
                        
                    candidates.append({
                        'content': chunk_text,
                        'page': page_num,
                        'title': title,
                        'type': source_type,
                        'graph_score': final_graph_score,
                        'reason': f"Linked via {neighbor_name} ({rel_type}, w={final_graph_score:.2f})"
                    })
            
    except Exception as e:
        print(f"[ERROR] Graph Retrieval failed: {e}")
        # Metrics are handled by Prometheus (API error rate)
        # Logs are handled by Loki (via stdout)
        import traceback
        traceback.print_exc()
        return []
        
    return candidates

if __name__ == "__main__":
    # Test
    sample = "Ludwig Wittgenstein's Tractatus Logico-Philosophicus discusses how language reflects the world's structure."
    # c, r = extract_concepts_and_relations(sample)
    # save_to_graph(123, c, r) # Mock
    print("Graph Service Loaded.")

