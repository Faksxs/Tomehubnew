
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

def get_database_connection():
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    return oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=password
    )

def extract_concepts_and_relations(text: str):
    """Uses Gemini to extract structured concepts and their connections."""
    if not text or len(text) < 50:
        return [], []
        
    prompt = f"""Analyze the following text fragment and extract the key concepts and their relationships.
    Format your response as a valid JSON object with two keys: 'concepts' (list of strings) and 'relations' (list of [source, type, target]).
    
    Text: "{text}"
    
    Rules:
    - Concepts should be specific (e.g., "Wittgenstein", "Linguistic Illusion").
    - Relations should describe the link (e.g., ["Wittgenstein", "CRITIQUED", "Metaphysics"]).
    - Output ONLY the JSON.
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
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
    conn = get_database_connection()
    cursor = conn.cursor()
    
    concept_map = {} # name -> id
    
    try:
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
            # Link to Chunk
            try:
                cursor.execute("""
                    INSERT INTO TOMEHUB_CONCEPT_CHUNKS (concept_id, content_id)
                    VALUES (:cid, :ch_id)
                """, {"cid": cid, "ch_id": content_id})
            except oracledb.IntegrityError:
                pass # Already linked
            
            # Optional: Generate Embedding for the concept itself if missing
            # (Skipping for now to save API costs, can do in background)
            
        # 2. Save Relations
        for rel in relations:
            if len(rel) == 3:
                src_name, rel_type, dst_name = rel
                sid = concept_map.get(src_name)
                did = concept_map.get(dst_name)
                
                if sid and did:
                    cursor.execute("""
                        INSERT INTO TOMEHUB_RELATIONS (src_id, dst_id, rel_type)
                        VALUES (:sid, :did, :rtype)
                    """, {"sid": sid, "did": did, "rtype": rel_type[:100]})
                    
        conn.commit()
    except Exception as e:
        print(f"[ERROR] DB Save failed: {e}")
    finally:
        conn.close()

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
    
    conn = get_database_connection()
    cursor = conn.cursor()
    candidates = []
    
    try:
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
                c_neighbor.name as related_concept
            FROM TOMEHUB_RELATIONS r
            JOIN TOMEHUB_CONCEPTS c_neighbor ON (r.dst_id = c_neighbor.id OR r.src_id = c_neighbor.id)
            JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c_neighbor.id = cc.concept_id
            JOIN TOMEHUB_CONTENT ct ON cc.content_id = ct.id
            WHERE (r.src_id IN ({SEQ}) OR r.dst_id IN ({SEQ}))
            AND ct.firebase_uid = :uid
            -- Avoid self-loops to entry node if needed, but here we want everything relevant
            AND c_neighbor.id NOT IN ({SEQ}) 
            FETCH FIRST 15 ROWS ONLY
        """
        
        # Format the IN clause params
        # Note: Oracle doesn't support list param for IN easily in python driver without loop, 
        # doing manual formatting strictly for integers is safe-ish.
        ids_str = ",".join(str(cid) for cid in concept_ids)
        safe_sql = sql.replace("{SEQ}", ids_str)
        
        cursor.execute(safe_sql, {"uid": firebase_uid})
        rows = cursor.fetchall()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(rows)} neighbor chunks via Graph.")
        
        for r in rows:
            content = r[0].read() if r[0] else ""
            candidates.append({
                'content': content,
                'page': r[1],
                'title': r[2],
                'type': r[3],
                'graph_score': 1.0, # High confidence for graph connection
                'reason': f"Linked via concept: {r[4]}"
            })
            
        return candidates

    except Exception as e:
        print(f"[ERROR] Graph Retrieval failed: {e}")
        return []
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Test
    sample = "Ludwig Wittgenstein's Tractatus Logico-Philosophicus discusses how language reflects the world's structure."
    # c, r = extract_concepts_and_relations(sample)
    # save_to_graph(123, c, r) # Mock
    print("Graph Service Loaded.")

