
import os
import json
import re
import oracledb
import logging
from datetime import datetime
from dotenv import load_dotenv
from services.llm_client import (
    MODEL_TIER_FLASH,
    PROVIDER_QWEN,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    generate_text,
    get_model_for_tier,
)

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

from services.embedding_service import get_embedding, get_query_embedding
from config import settings
from services.cache_service import get_cache, generate_cache_key


from infrastructure.db_manager import DatabaseManager, safe_read_clob

def extract_concepts_and_relations(text: str):
    """Uses Gemini to extract structured concepts and their connections."""
    if not text or len(text) < 50:
        return [], []
        
    from prompts.graph_prompts import GRAPH_EXTRACTION_PROMPT
    prompt = GRAPH_EXTRACTION_PROMPT.format(text=text)
    
    try:
        model = get_model_for_tier(MODEL_TIER_FLASH)
        result = generate_text(
            model=model,
            prompt=prompt,
            task="graph_extract_concepts",
            model_tier=MODEL_TIER_FLASH,
            timeout_s=45.0,
            provider_hint=PROVIDER_QWEN,
            route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
            allow_secondary_fallback=True,
            fallback_state={"secondary_fallback_used": 0},
        )
        text_resp = result.text.strip()
        
        # Avoid console encoding crashes on Windows terminals.
        logger.debug(
            "Graph extraction raw response preview",
            extra={"preview": text_resp[:100].encode("ascii", "ignore").decode("ascii")},
        )
        
        # Clean potential markdown
        if "```json" in text_resp:
            text_resp = re.search(r'```json\s*(.*?)\s*```', text_resp, re.DOTALL).group(1)
        elif "```" in text_resp:
            text_resp = re.search(r'```\s*(.*?)\s*```', text_resp, re.DOTALL).group(1)
            
        data = json.loads(text_resp)
        concepts = data.get('concepts', [])
        relations = data.get('relations', [])

        # Normalize concepts: accept list of strings or list of objects
        normalized_concepts = []
        for c in concepts:
            if isinstance(c, str):
                name = c.strip()
                if name:
                    normalized_concepts.append({"name": name, "type": "AUTOMATIC", "description": None})
            elif isinstance(c, dict):
                name = (c.get("name") or "").strip()
                if not name:
                    continue
                normalized_concepts.append({
                    "name": name,
                    "type": (c.get("type") or "AUTOMATIC").strip(),
                    "description": (c.get("description") or "").strip() or None
                })
        return normalized_concepts, relations
    except Exception as e:
        print(f"[ERROR] Extraction failed: {e}")
        return [], []

def save_to_graph(content_id: int, concepts: list, relations: list) -> bool:
    """Saves extracted data to Oracle Graph tables."""
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                concept_map = {} # name_lower -> id
                
                # 1. Save Concepts & Link to Chunk
                for concept in concepts:
                    if isinstance(concept, dict):
                        name_clean = concept.get("name", "").strip()[:255]
                        ctype = (concept.get("type") or "AUTOMATIC").strip()[:50]
                        desc = concept.get("description")
                    else:
                        name_clean = str(concept).strip()[:255]
                        ctype = "AUTOMATIC"
                        desc = None
                    if not name_clean:
                        continue

                    # Normalize bilingual format: "Düşüş (The Fall)" -> name="Düşüş", alias="The Fall"
                    alias = None
                    m = re.match(r"^(.+?)\\s*\\((.+)\\)\\s*$", name_clean)
                    if m:
                        name_clean = m.group(1).strip()[:255]
                        alias = m.group(2).strip()[:255] if m.group(2) else None

                    name_lower = name_clean.lower()
                    desc_embedding = None
                    if desc and isinstance(desc, str):
                        desc_clean = desc.strip()
                        if len(desc_clean) >= 20:
                            desc_embedding = get_embedding(desc_clean)

                    # Upsert Concept (case-insensitive)
                    cursor.execute("""
                        MERGE INTO TOMEHUB_CONCEPTS target
                        USING (SELECT :name as name, :name_lower as name_lower, :ctype as ctype, :p_descr as descr FROM DUAL) src
                        ON (LOWER(target.name) = src.name_lower)
                        WHEN MATCHED THEN
                            UPDATE SET
                                CONCEPT_TYPE = COALESCE(target.CONCEPT_TYPE, src.ctype),
                                DESCRIPTION = CASE
                                    WHEN target.DESCRIPTION IS NULL THEN TO_CLOB(src.descr)
                                    ELSE target.DESCRIPTION
                                END,
                                DESCRIPTION_EMBEDDING = CASE
                                    WHEN target.DESCRIPTION_EMBEDDING IS NULL THEN :p_desc_vec
                                    ELSE target.DESCRIPTION_EMBEDDING
                                END
                        WHEN NOT MATCHED THEN
                            INSERT (name, concept_type, description, description_embedding)
                            VALUES (src.name, src.ctype, TO_CLOB(src.descr), :p_desc_vec)
                    """, {"name": name_clean, "name_lower": name_lower, "ctype": ctype, "p_descr": desc, "p_desc_vec": desc_embedding})
                    
                    # Get ID
                    cursor.execute("SELECT id FROM TOMEHUB_CONCEPTS WHERE LOWER(name) = :name_lower", {"name_lower": name_lower})
                    row = cursor.fetchone()
                    if not row:
                        continue
                    cid = row[0]
                    concept_map[name_lower] = cid

                    # Insert alias if exists
                    if alias:
                        try:
                            cursor.execute("""
                                INSERT INTO TOMEHUB_CONCEPT_ALIASES (concept_id, alias)
                                VALUES (:p_cid, :p_alias)
                            """, {"p_cid": cid, "p_alias": alias})
                        except oracledb.IntegrityError:
                            pass
                    
                    # Link to Chunk
                    try:
                        # Compute strength if embeddings available
                        strength = None
                        justification = None
                        try:
                            cursor.execute("""
                                SELECT VEC_EMBEDDING, CONTENT_CHUNK
                                FROM TOMEHUB_CONTENT_V2
                                WHERE ID = :p_id
                            """, {"p_id": content_id})
                            c_row = cursor.fetchone()
                            if c_row:
                                content_vec = c_row[0]
                                content_text = safe_read_clob(c_row[1]) if c_row[1] else ""
                                if desc_embedding is not None and content_vec is not None:
                                    cursor.execute("""
                                        SELECT 1 - VECTOR_DISTANCE(:p_desc, :p_vec, COSINE) FROM DUAL
                                    """, {"p_desc": desc_embedding, "p_vec": content_vec})
                                    strength = cursor.fetchone()[0]

                                # Simple justification
                                if content_text:
                                    lowered = content_text.lower()
                                    if name_clean.lower() in lowered:
                                        justification = f"Exact match: '{name_clean}'"
                                    elif alias and alias.lower() in lowered:
                                        justification = f"Exact match: '{alias}'"
                                    elif strength is not None:
                                        justification = "Semantic match via embedding"
                        except Exception:
                            pass

                        cursor.execute("""
                            INSERT INTO TOMEHUB_CONCEPT_CHUNKS (concept_id, content_id, strength, justification)
                            VALUES (:cid, :ch_id, :p_strength, :p_just)
                        """, {"cid": cid, "ch_id": content_id, "p_strength": strength, "p_just": justification})
                    except oracledb.IntegrityError:
                        pass # Already linked
                    
                # 2. Save Relations
                for rel in relations:
                    # Expecting [src, type, dst, confidence]
                    if len(rel) >= 3:
                        src_name = rel[0]
                        rel_type = rel[1]
                        dst_name = rel[2]
                        try:
                            weight = float(rel[3]) if len(rel) > 3 else 1.0
                        except (TypeError, ValueError):
                            weight = 1.0
                        
                        sid = concept_map.get(str(src_name).strip().lower())
                        did = concept_map.get(str(dst_name).strip().lower())
                        
                        if sid and did:
                            try:
                                cursor.execute("""
                                    INSERT INTO TOMEHUB_RELATIONS (src_id, dst_id, rel_type, weight)
                                    VALUES (:sid, :did, :rtype, :wght)
                                """, {"sid": sid, "did": did, "rtype": rel_type[:100], "wght": weight})
                            except oracledb.IntegrityError:
                                # Duplicate relation (unique constraint) - safe to skip
                                pass
                            
                conn.commit()
                return True
    except Exception as e:
        print(f"[ERROR] DB Save failed: {e}")
        return False

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

    # 2. Alias Match
    cursor.execute("""
        SELECT concept_id FROM TOMEHUB_CONCEPT_ALIASES
        WHERE LOWER(alias) LIKE :term
        FETCH FIRST 5 ROWS ONLY
    """, {"term": f"%{clean_text}%"})
    ids.extend([row[0] for row in cursor.fetchall()])
    return ids

def find_concepts_by_batch(names: list[str], cursor) -> list[int]:
    """
    Finds concept IDs for a list of names (case-insensitive).
    """
    if not names:
        return []
        
    # Use IN clause for exact lower match - benefits from Functional Index
    bind_names = [f":n{i}" for i in range(len(names))]
    bind_clause = ",".join(bind_names)
    params = {f"n{i}": n.lower().strip() for i, n in enumerate(names)}
    
    sql = f"SELECT id FROM TOMEHUB_CONCEPTS WHERE LOWER(name) IN ({bind_clause})"
    cursor.execute(sql, params)
    
    ids = [row[0] for row in cursor.fetchall()]

    # Alias batch match
    sql_alias = f"SELECT concept_id FROM TOMEHUB_CONCEPT_ALIASES WHERE LOWER(alias) IN ({bind_clause})"
    cursor.execute(sql_alias, params)
    ids.extend([row[0] for row in cursor.fetchall()])

    return ids


class GraphRetrievalError(Exception):
    """Raised when GraphRAG retrieval fails, allowing the caller to handle degradation."""
    pass

def get_graph_candidates(query_text: str, firebase_uid: str, limit: int = 15, offset: int = 0) -> list[dict]:
    """
    GraphRAG Retrieval:
    1. Identify concepts in Query.
    2. Traverse interactions (Query -> Concept A -> Related Concept B).
    3. Fetch chunks linked to Concept B.
    
    Returns list of chunks formatted for search_service.
    Raises GraphRetrievalError on failure.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] --- GRAPHRAG RETRIEVAL: '{query_text}' (limit={limit}, offset={offset}) ---")

    
    # Check Cache (Task B2)
    cache = get_cache()
    cache_key = None
    if cache:
        cache_key = generate_cache_key("graph_candidates", query_text, firebase_uid)
        cached_results = cache.get(cache_key)
        if cached_results is not None:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [CACHE HIT] Returning cached graph candidates.")
            return cached_results

    candidates = []
    
    try:
        with DatabaseManager.get_read_connection() as conn:
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
                    if concepts:
                        # B3: Batch lookup concepts (N+1 Elimination)
                        concept_ids.extend(find_concepts_by_batch(
                            [c.get("name") if isinstance(c, dict) else str(c) for c in concepts],
                            cursor
                        ))

                # If still empty, use semantic search over DESCRIPTION_EMBEDDING
                if not concept_ids:
                    q_vec = get_query_embedding(query_text)
                    if q_vec:
                        cursor.execute("""
                            SELECT id FROM TOMEHUB_CONCEPTS
                            WHERE DESCRIPTION_EMBEDDING IS NOT NULL
                            ORDER BY VECTOR_DISTANCE(DESCRIPTION_EMBEDDING, :p_vec, COSINE)
                            FETCH FIRST 5 ROWS ONLY
                        """, {"p_vec": q_vec})
                        concept_ids.extend([row[0] for row in cursor.fetchall()])
                
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
                
                # ORA-22848 fix:
                # `ct.content_chunk` is a CLOB and cannot participate in DISTINCT comparison.
                # Deduplicate first on non-CLOB keys (including content_id), then fetch CLOB in outer select.
                sql = """
                    SELECT
                        ct.content_chunk,
                        gh.page_number,
                        gh.title,
                        gh.content_type as source_type,
                        gh.related_concept,
                        gh.rel_type,
                        gh.weight,
                        gh.strength
                    FROM (
                        SELECT DISTINCT
                            ct.id AS content_id,
                            ct.page_number,
                            ct.title,
                            ct.content_type,
                            c_neighbor.name as related_concept,
                            r.rel_type,
                            r.weight,
                            cc.strength
                        FROM TOMEHUB_RELATIONS r
                        JOIN TOMEHUB_CONCEPTS c_neighbor ON (r.dst_id = c_neighbor.id OR r.src_id = c_neighbor.id)
                        JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c_neighbor.id = cc.concept_id
                        JOIN TOMEHUB_CONTENT_V2 ct ON cc.content_id = ct.id
                        WHERE (r.src_id IN ({SEQ}) OR r.dst_id IN ({SEQ}))
                        AND ct.firebase_uid = :p_uid
                        AND ct.ai_eligible = 1
                        AND c_neighbor.id NOT IN ({SEQ})
                        AND (cc.strength IS NULL OR cc.strength >= :p_strength)
                    ) gh
                    JOIN TOMEHUB_CONTENT_V2 ct ON ct.id = gh.content_id
                    OFFSET :p_offset ROWS FETCH FIRST :p_limit ROWS ONLY
                """
                
                # Format the IN clause params SAFE WAY
                bind_names = [f":id_{i}" for i in range(len(concept_ids))]
                bind_clause = ",".join(bind_names)
                
                safe_sql = sql.replace("{SEQ}", bind_clause)
                
                params = {"p_uid": firebase_uid, "p_limit": limit, "p_offset": offset, "p_strength": settings.CONCEPT_STRENGTH_MIN}
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
                    strength = float(r[7]) if r[7] is not None else None
                    
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
                        'reason': f"Linked via {neighbor_name} ({rel_type}, w={final_graph_score:.2f}, s={strength:.2f})" if strength is not None else f"Linked via {neighbor_name} ({rel_type}, w={final_graph_score:.2f})"
                    })
            
    except Exception as e:
        logger.error(f"Graph Retrieval failed: {e}")
        # Re-raise as specific error for "Fail Loud" policy
        raise GraphRetrievalError(f"Graph traversal failed: {str(e)}") from e
        
    # Cache results (60 minutes)
    if cache and cache_key and candidates:
        cache.set(cache_key, candidates, ttl=3600)

    return candidates

if __name__ == "__main__":
    # Test
    sample = "Ludwig Wittgenstein's Tractatus Logico-Philosophicus discusses how language reflects the world's structure."
    # c, r = extract_concepts_and_relations(sample)
    # save_to_graph(123, c, r) # Mock
    print("Graph Service Loaded.")

