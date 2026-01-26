from abc import ABC, abstractmethod
from typing import List, Dict, Any
import oracledb

# Import DatabaseManager
from infrastructure.db_manager import DatabaseManager
from utils.text_utils import normalize_text, deaccent_text, get_lemmas

class SearchStrategy(ABC):
    """
    Abstract Base Class for Search Strategies.
    Each strategy implements a specific retrieval logic.
    """
    
    @abstractmethod
    def search(self, query: str, firebase_uid: str, limit: int = 20) -> List[Dict[str, Any]]:
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
    def search(self, query: str, firebase_uid: str, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    q_deaccented = deaccent_text(query)
                    
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number, 
                               tags, summary, personal_note,
                               normalized_content
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                        AND text_deaccented LIKE '%' || :p_term || '%'
                        FETCH FIRST :p_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, {"p_uid": firebase_uid, "p_term": q_deaccented, "p_limit": limit})
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
            print(f"[ERROR] ExactMatchStrategy failed: {e}")
            return []

class LemmaMatchStrategy(SearchStrategy):
    """
    Strategy for Lemma-based matching (Fuzzy-ish).
    """
    def search(self, query: str, firebase_uid: str, limit: int = 20) -> List[Dict[str, Any]]:
        lemmas = get_lemmas(query)
        if not lemmas:
            return []
            
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    # We enforce ALL lemmas must be present? Or ANY? 
                    # Smart Search used "ANY" but iterated. Let's do ANY for broader recall or ALL for precision.
                    # Let's try to match ANY lemma first.
                    
                    # Since Oracle doesn't have native array overlap easily without types, 
                    # we iterate Python side or use LIKE on JSON array stored in DB?
                    # DB has `lemma_tokens` (CLOB or JSON).
                    
                    # Simplified: Check for first 3 lemmas
                    for lemma in lemmas[:3]: 
                        sql = """
                            SELECT id, content_chunk, title, source_type, page_number,
                                   tags, summary, personal_note
                            FROM TOMEHUB_CONTENT
                            WHERE firebase_uid = :p_uid
                            AND lemma_tokens LIKE '%' || :p_lemma || '%'
                            FETCH FIRST :p_limit ROWS ONLY
                        """
                        cursor.execute(sql, {"p_uid": firebase_uid, "p_lemma": f'"{lemma}"', "p_limit": limit})
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
                                'score': 90.0, # Base score for lemma
                                'match_type': 'lemma_fuzzy',
                                'match_term': lemma
                            })
                    return results # Orchestrator handles deduplication

        except Exception as e:
            print(f"[ERROR] LemmaMatchStrategy failed: {e}")
            return []

class SemanticMatchStrategy(SearchStrategy):
    """
    Strategy for Vector/Semantic Search.
    """
    def __init__(self, embedding_service_fn):
        self.get_embedding = embedding_service_fn
        
    def search(self, query: str, firebase_uid: str, limit: int = 20) -> List[Dict[str, Any]]:
        emb = self.get_embedding(query)
        if not emb:
            return []
            
        try:
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    sql = """
                        SELECT id, content_chunk, title, source_type, page_number,
                               tags, summary, personal_note,
                               VECTOR_DISTANCE(vec_embedding, :vec, COSINE) as dist
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                        ORDER BY dist ASC
                        FETCH FIRST :p_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, {"p_uid": firebase_uid, "vec": emb, "p_limit": limit})
                    rows = cursor.fetchall()
                    
                    results = []
                    for r in rows:
                        content = r[1].read() if r[1] else ""
                        tags = r[5].read() if r[5] else ""
                        summary = r[6].read() if r[6] else ""
                        note = r[7].read() if r[7] else ""
                        dist = r[8]
                        if dist is None:
                            # Handle missing vector in DB gracefully
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
                    return results

        except Exception as e:
            print(f"[ERROR] SemanticMatchStrategy failed: {e}")
            return []
