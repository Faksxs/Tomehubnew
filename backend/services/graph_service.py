
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
            cursor.execute("""
                INSERT INTO TOMEHUB_CONCEPT_CHUNKS (concept_id, content_id)
                SELECT :cid, :ch_id FROM dual
                WHERE NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_CONCEPT_CHUNKS 
                    WHERE concept_id = :cid AND content_id = :ch_id
                )
            """, {"cid": cid, "ch_id": content_id})
            
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

if __name__ == "__main__":
    # Test on a sample text
    sample = "Ludwig Wittgenstein's Tractatus Logico-Philosophicus discusses how language reflects the world's structure, but later he argued that metaphysical problems are often linguistic illusions."
    print("Testing extraction...")
    c, r = extract_concepts_and_relations(sample)
    print(f"Concepts: {c}")
    print(f"Relations: {r}")
