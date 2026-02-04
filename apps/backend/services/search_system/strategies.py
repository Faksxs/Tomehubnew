from typing import List, Dict, Any, Optional
import os
import logging
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.text_utils import deaccent_text, get_lemmas

logger = logging.getLogger("search_strategies")

class SearchStrategy:
    def search(self, query: str, firebase_uid: str, limit: int = 20, **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError

def _apply_resource_type_filter(sql: str, params: Dict[str, Any], resource_type: Optional[str]) -> tuple:
    if resource_type:
        sql += " AND source_type = :p_res_type"
        params["p_res_type"] = resource_type
    return sql, params

class ExactMatchStrategy(SearchStrategy):
    """
    Strategy for exact (de-accented) matching.
    """
    def search(self, query: str, firebase_uid: str, limit: int = 20, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    q_deaccented = deaccent_text(query)
                    
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number, 
                               tags, summary, "COMMENT",
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
                    
                    sql, params = _apply_resource_type_filter(sql, params, resource_type)
                        
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
                        content = safe_read_clob(r[1])
                        tags = safe_read_clob(r[5])
                        summary = safe_read_clob(r[6])
                        note = safe_read_clob(r[7])
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'comment': note,
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
    def search(self, query: str, firebase_uid: str, limit: int = 20, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        lemmas = get_lemmas(query)
        if not lemmas:
            return []
            
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number,
                               tags, summary, "COMMENT"
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                    """
                    params = {"p_uid": firebase_uid, "p_limit": limit}
                    
                    sql, params = _apply_resource_type_filter(sql, params, resource_type)
                    
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
                        content = safe_read_clob(r[1])
                        tags = safe_read_clob(r[5])
                        summary = safe_read_clob(r[6])
                        note = safe_read_clob(r[7])
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'comment': note,
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
        emb = self.get_embedding(query)
        if not emb:
            return []
            
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    def run_query(custom_limit, length_filter=None):
                        sql = """
                            SELECT id, content_chunk, title, source_type, page_number,
                                   tags, summary, "COMMENT",
                                   VECTOR_DISTANCE(vec_embedding, :vec, COSINE) as dist
                            FROM TOMEHUB_CONTENT
                            WHERE firebase_uid = :p_uid
                        """
                        
                        params = {"p_uid": firebase_uid, "vec": emb, "p_limit": custom_limit}
                        
                        sql, params = _apply_resource_type_filter(sql, params, resource_type)

                        if length_filter:
                            if length_filter == 'SHORT':
                                sql += " AND LENGTH(content_chunk) < 600 "
                            elif length_filter == 'LONG':
                                sql += " AND LENGTH(content_chunk) > 600 "
                                
                        sql += """
                            ORDER BY dist ASC
                            FETCH FIRST :p_limit ROWS ONLY
                        """
                        
                        cursor.execute(sql, params)
                        return cursor.fetchall()
                    
                    rows = []
                    if intent == 'DIRECT' or intent == 'FOLLOW_UP':
                        sweep_limit = max(5, limit // 2)
                        rows.extend(run_query(sweep_limit))
                        rows.extend(run_query(sweep_limit, length_filter='SHORT'))
                    elif intent == 'NARRATIVE':
                        rows.extend(run_query(15))
                        rows.extend(run_query(10, length_filter='LONG'))
                    else:
                        rows.extend(run_query(limit))
                        
                    seen_ids = set()
                    unique_rows = []
                    for r in rows:
                        if r[0] not in seen_ids:
                            seen_ids.add(r[0])
                            unique_rows.append(r)
                            
                    for r in unique_rows:
                        content = safe_read_clob(r[1])
                        tags = safe_read_clob(r[5])
                        summary = safe_read_clob(r[6])
                        note = safe_read_clob(r[7])
                        dist = r[8]
                        
                        score = max(0, (1 - dist) * 100) if dist is not None else 0.0
                        
                        results.append({
                            'id': r[0],
                            'title': r[2],
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'comment': note,
                            'score': score,
                            'match_type': 'semantic'
                        })
                        
                    results.sort(key=lambda x: x['score'], reverse=True)
                    return results[:limit]

        except Exception as e:
            logger.error(f"SemanticMatchStrategy failed: {e}", exc_info=True)
            return []
