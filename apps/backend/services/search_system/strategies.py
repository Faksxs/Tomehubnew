from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import oracledb

# Import DatabaseManager
from infrastructure.db_manager import DatabaseManager
from utils.text_utils import normalize_text, deaccent_text, get_lemmas
from utils.logger import get_logger

logger = get_logger("search_strategies")

class SearchStrategy(ABC):
    """
    Abstract Base Class for Search Strategies.
    Each strategy implements a specific retrieval logic.
    """
    
    @abstractmethod
    def search(self, query: str, firebase_uid: str, limit: int = 20, resource_type: Optional[str] = None) -> List[Dict[Any, Any]]:
        """
        Execute search.
        Returns a list of standardized result dictionaries.
        Format: [{'title': str, 'content': str, 'score': float, 'type': str, ...}]
        """
        pass

class ExactMatchStrategy(SearchStrategy):
    """
    Strategies for Exact De-accented Match.
    Fastest, high precision.
    """
    def search(self, query: str, firebase_uid: str, limit: int = 20, resource_type: Optional[str] = None) -> List[Dict[Any, Any]]:
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    q_deaccented = deaccent_text(query)
                    
                    # Layer 4 Mapping
                    source_type_map = {'BOOK': 'PDF', 'ARTICLE': 'ARTICLE', 'WEBSITE': 'WEBSITE', 'PERSONAL_NOTE': 'NOTE'}
                    db_type = source_type_map.get(resource_type)
                    
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number, 
                               tags, summary, personal_note,
                               normalized_content
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                    """
                    
                    params = {
                        "p_uid": firebase_uid, 
                        "p_term": q_deaccented, 
                        "p_term_lower": query.lower(),
                        "p_limit": limit
                    }
                    
                    if db_type:
                        sql += " AND source_type = :p_type "
                        params["p_type"] = db_type
                        
                    sql += """
                        AND (
                            text_deaccented LIKE '%' || :p_term || '%'
                            OR LOWER(content_chunk) LIKE '%' || :p_term_lower || '%'
                        )
                        FETCH FIRST :p_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    results = []
                    for r in rows:
                        content = r[1].read() if r[1] else ""
                        # r[5]=tags, r[6]=summary, r[7]=note need reading if CLOB
                        tags = r[5].read() if r[5] else ""
                        summary = r[6].read() if r[6] else ""
                        note = r[7].read() if r[7] else ""
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'personal_note': note,
                            'score': 100.0,
                            'match_type': 'exact_deaccented'
                        })
                    return results

        except Exception as e:
            logger.error(f"ExactMatchStrategy failed: {e}", exc_info=True)
            return []

class LemmaMatchStrategy(SearchStrategy):
    """
    Strategy for Lemma-based matching (Fuzzy-ish).
    """
    def search(self, query: str, firebase_uid: str, limit: int = 20, resource_type: Optional[str] = None) -> List[Dict[Any, Any]]:
        lemmas = get_lemmas(query)
        if not lemmas:
            return []
            
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Layer 4 Mapping
                    source_type_map = {'BOOK': 'PDF', 'ARTICLE': 'ARTICLE', 'WEBSITE': 'WEBSITE', 'PERSONAL_NOTE': 'NOTES'}
                    db_type = source_type_map.get(resource_type)

                    results = []
                    
                    # Build bulk query for up to 5 lemmas
                    # We match ANY lemma but Oracle doesn't have native "count matches" easily in LIKE OR
                    # So we use a search pattern that matches the JSON structure ["lemma1", "lemma2"]
                    
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number,
                               tags, summary, personal_note
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                    """
                    params = {"p_uid": firebase_uid, "p_limit": limit}
                    
                    if db_type:
                        sql += " AND source_type = :p_type "
                        params["p_type"] = db_type
                    
                    lemma_conditions = []
                    for i, lemma in enumerate(lemmas[:5]):
                        p_name = f"p_lemma_{i}"
                        lemma_conditions.append(f"lemma_tokens LIKE :{p_name}")
                        params[p_name] = f'%"{lemma}"%'
                    
                    if lemma_conditions:
                        sql += " AND (" + " OR ".join(lemma_conditions) + ")"
                    
                    sql += " FETCH FIRST :p_limit ROWS ONLY"
                    
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    for r in rows:
                        content = r[1].read() if r[1] else ""
                        tags = r[5].read() if r[5] else ""
                        summary = r[6].read() if r[6] else ""
                        note = r[7].read() if r[7] else ""
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'personal_note': note,
                            'score': 90.0,
                            'match_type': 'lemma_fuzzy'
                        })
                    return results

        except Exception as e:
            logger.error(f"LemmaMatchStrategy failed: {e}", exc_info=True)
            return []

class SemanticMatchStrategy(SearchStrategy):
    """
    Strategy for Vector/Semantic Search.
    """
    def __init__(self, embedding_service_fn):
        self.get_embedding = embedding_service_fn
        
    def search(self, query: str, firebase_uid: str, limit: int = 20, intent: str = 'SYNTHESIS', resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Executes semantic search with Content-Aware Filtering.
        
        Dynamic Tiered Retrieval:
        - DIRECT Intent: Bias towards shorter chunks (< 400 chars).
        - NARRATIVE Intent: Bias towards longer chunks (> 600 chars).
        - Otherwise: Standard retrieval.
        """
        emb = self.get_embedding(query)
        if not emb:
            return []
            
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    # Layer 4 Mapping
                    source_type_map = {'BOOK': 'PDF', 'ARTICLE': 'ARTICLE', 'WEBSITE': 'WEBSITE', 'PERSONAL_NOTE': 'NOTE'}
                    db_type = source_type_map.get(resource_type)

                    # Helper to run query
                    def run_query(custom_limit, length_filter=None):
                        sql = """
                            SELECT id, content_chunk, title, source_type, page_number,
                                   tags, summary, personal_note,
                                   VECTOR_DISTANCE(vec_embedding, :vec, COSINE) as dist
                            FROM TOMEHUB_CONTENT
                            WHERE firebase_uid = :p_uid
                        """
                        
                        params = {"p_uid": firebase_uid, "vec": emb, "p_limit": custom_limit}
                        
                        if db_type:
                            sql += " AND source_type = :p_type "
                            params["p_type"] = db_type

                        # Apply Content-Aware Filters
                        if length_filter:
                            if length_filter == 'SHORT':
                                sql += " AND LENGTH(content_chunk) < 600 " # Relaxed from 400 for better recall
                            elif length_filter == 'LONG':
                                sql += " AND LENGTH(content_chunk) > 600 "
                                
                        sql += """
                            ORDER BY dist ASC
                            FETCH FIRST :p_limit ROWS ONLY
                        """
                        
                        cursor.execute(sql, params)
                        return cursor.fetchall()
                    
                    # --- EXECUTE SUB-QUERIES ---
                    rows = []
                    
                    if intent == 'DIRECT' or intent == 'FOLLOW_UP':
                        # 1. Standard Sweep (ensure we don't miss good long answers)
                        # Use a portion of limit for each
                        sweep_limit = max(5, limit // 2)
                        rows.extend(run_query(sweep_limit))
                        # 2. Bias: Short & Punchy (Definitions/Factoids)
                        rows.extend(run_query(sweep_limit, length_filter='SHORT'))
                        
                    elif intent == 'NARRATIVE':
                        # 1. Standard Sweep
                        rows.extend(run_query(15))
                        # 2. Bias: Long & Contextual
                        rows.extend(run_query(10, length_filter='LONG'))
                        
                    else:
                        # SYNTHESIS / Default -> Standard Search
                        rows.extend(run_query(limit))
                        
                    # Deduplicate by ID
                    seen_ids = set()
                    unique_rows = []
                    for r in rows:
                        if r[0] not in seen_ids:
                            seen_ids.add(r[0])
                            unique_rows.append(r)
                            
                    # Process Results
                    for r in unique_rows:
                        content = r[1].read() if r[1] else ""
                        tags = r[5].read() if r[5] else ""
                        summary = r[6].read() if r[6] else ""
                        note = r[7].read() if r[7] else ""
                        dist = r[8]
                        
                        if dist is None:
                            score = 0.0
                        else:
                            score = max(0, (1 - dist) * 100)
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'personal_note': note,
                            'score': score,
                            'match_type': 'semantic'
                        })
                        
                    # Sort again by score after merge
                    results.sort(key=lambda x: x['score'], reverse=True)
                    return results[:limit]

        except Exception as e:
            logger.error(f"SemanticMatchStrategy failed: {e}", exc_info=True)
            return []
