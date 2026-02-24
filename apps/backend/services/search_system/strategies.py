from typing import List, Dict, Any, Optional
import os
import logging
import re
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.text_utils import deaccent_text, get_lemmas, repair_common_mojibake

logger = logging.getLogger("search_strategies")

# Common Turkish connectors / stop lemmas that should not drive Layer-2 recall.
_STOP_LEMMAS_ASCII = {
    "ve", "veya", "ile", "ama", "fakat", "ancak", "lakin", "ki",
    "de", "da", "gibi", "icin", "gore", "kadar", "hem",
    "ya", "yada", "yahut", "mi", "mu",
}

def _filter_query_lemmas(lemmas: List[str]) -> List[str]:
    filtered: List[str] = []
    for lemma in lemmas or []:
        norm = deaccent_text((lemma or "").strip()).lower()
        if len(norm) < 2:
            continue
        if norm in _STOP_LEMMAS_ASCII:
            continue
        filtered.append(lemma)
    return filtered


def _normalize_match_text(text: str) -> str:
    # Preserve token boundaries before deaccenting; some normalizers can drop punctuation.
    pre = repair_common_mojibake(text or "").lower()
    pre = re.sub(r"[\W_]+", " ", pre, flags=re.UNICODE)
    norm = deaccent_text(pre).lower()
    norm = re.sub(r"[^a-z0-9]+", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm


def _contains_exact_term_boundary(haystack_text: str, query_text: str) -> bool:
    haystack = _normalize_match_text(haystack_text)
    needle = _normalize_match_text(query_text)
    if not haystack or not needle:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _contains_lemma_stem_boundary(haystack_text: str, lemma_text: str) -> bool:
    haystack = _normalize_match_text(haystack_text)
    stem = _normalize_match_text(lemma_text)
    if not haystack or not stem or len(stem) < 3:
        return False
    # Match tokens that start with lemma stem (niyet -> niyet, niyetli, niyetler),
    # but do not allow inner-word matches (medeniyet should not match niyet).
    pattern = rf"(?<![a-z0-9]){re.escape(stem)}[a-z0-9]*(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _count_lemma_stem_hits(haystack_text: str, lemma_texts: List[str]) -> int:
    haystack = _normalize_match_text(haystack_text)
    if not haystack:
        return 0
    total = 0
    for lemma in lemma_texts or []:
        stem = _normalize_match_text(lemma)
        if len(stem) < 3:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(stem)}[a-z0-9]*(?![a-z0-9])"
        total += len(re.findall(pattern, haystack))
    return total


def _contains_inner_substring_only(haystack_text: str, query_text: str) -> bool:
    haystack = _normalize_match_text(haystack_text)
    needle = _normalize_match_text(query_text)
    if not haystack or not needle:
        return False
    if needle not in haystack:
        return False
    return not _contains_lemma_stem_boundary(haystack_text, query_text)


def _escape_like_literal(value: str, escape_char: str = "\\") -> str:
    """
    Escape Oracle LIKE wildcard characters so user query is treated as literal text.
    """
    raw = str(value or "")
    esc = str(escape_char or "\\")
    # Order matters: escape the escape char first.
    raw = raw.replace(esc, esc + esc)
    raw = raw.replace("%", esc + "%")
    raw = raw.replace("_", esc + "_")
    return raw


def _contains_like_pattern(value: str, escape_char: str = "\\") -> str:
    return f"%{_escape_like_literal(value, escape_char=escape_char)}%"

class SearchStrategy:
    def search(self, query: str, firebase_uid: str, limit: int = 100, offset: int = 0, **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError

def _normalize_resource_type(resource_type: Optional[str]) -> Optional[str]:
    if resource_type is None:
        return None
    value = str(resource_type).strip().upper()
    return value or None


def _apply_resource_type_filter(sql: str, params: Dict[str, Any], resource_type: Optional[str]) -> tuple:
    rt = _normalize_resource_type(resource_type)
    if not rt:
        return (sql, params)

    if rt == "BOOK":
        sql += " AND c.content_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT') "
    elif rt == "ALL_NOTES":
        sql += " AND c.content_type IN ('HIGHLIGHT', 'INSIGHT') "
    elif rt == "PERSONAL_NOTE":
        sql += " AND c.content_type = 'PERSONAL_NOTE' "
    elif rt in {"ARTICLE", "WEBSITE"}:
        sql += " AND c.content_type = :p_res_type "
        params["p_res_type"] = rt
    else:
        # Backward-compatible strict mode for custom/legacy values.
        sql += " AND c.content_type = :p_res_type "
        params["p_res_type"] = rt

    return (sql, params)


def _apply_book_id_filter(sql: str, params: Dict[str, Any], book_id: Optional[str]) -> tuple:
    bid = str(book_id or "").strip()
    if bid:
        sql += " AND c.item_id = :p_book_id "
        params["p_book_id"] = bid
    return (sql, params)


def _normalize_visibility_scope(visibility_scope: Optional[str]) -> str:
    scope = str(visibility_scope or "default").strip().lower()
    if scope not in {"default", "all"}:
        return "default"
    return scope


def _apply_visibility_filter(sql: str, params: Dict[str, Any], visibility_scope: Optional[str]) -> tuple:
    scope = _normalize_visibility_scope(visibility_scope)
    if scope == "all":
        sql += " AND NVL(l.search_visibility, 'DEFAULT') <> 'NEVER_RETRIEVE' "
        return (sql, params)
    sql += " AND NVL(l.search_visibility, 'DEFAULT') = 'DEFAULT' "
    return (sql, params)


def _apply_content_type_filter(sql: str, params: Dict[str, Any], content_type: Optional[str]) -> tuple:
    ct = str(content_type or "").strip().upper()
    if not ct:
        return (sql, params)
    sql += " AND c.content_type = :p_content_type "
    params["p_content_type"] = ct
    return (sql, params)


def _apply_ingestion_type_filter(sql: str, params: Dict[str, Any], ingestion_type: Optional[str]) -> tuple:
    it = str(ingestion_type or "").strip().upper()
    if not it:
        return (sql, params)
    sql += " AND INGESTION_TYPE = :p_ingestion_type "
    params["p_ingestion_type"] = it
    return (sql, params)


def _should_exclude_pdf_in_first_pass(resource_type: Optional[str], book_id: Optional[str]) -> bool:
    # Scoped retrieval should never hide PDF chunks in first pass.
    if str(book_id or "").strip():
        return False

    rt = _normalize_resource_type(resource_type)
    if not rt:
        return True

    # Explicit scopes already constrain source_type; no extra PDF exclusion needed.
    if rt in {"BOOK", "ALL_NOTES", "PERSONAL_NOTE", "ARTICLE", "WEBSITE", "PDF", "EPUB", "PDF_CHUNK"}:
        return False
    return False

class ExactMatchStrategy(SearchStrategy):
    """
    Strategy for exact (de-accented) matching.
    """
    def search(
        self,
        query: str,
        firebase_uid: str,
        limit: int = 1000,
        offset: int = 0,
        resource_type: Optional[str] = None,
        book_id: Optional[str] = None,
        visibility_scope: Optional[str] = None,
        content_type: Optional[str] = None,
        ingestion_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    q_deaccented = deaccent_text(query)
                    candidate_limit = min(max(limit * 4, limit + 40), 2500)
                    
                    sql = """
                        SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number, 
                               c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT",
                               c.item_id as book_id, c.normalized_content
                        FROM TOMEHUB_CONTENT_V2 c
                        LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                        WHERE c.firebase_uid = :p_uid
                          AND c.AI_ELIGIBLE = 1
                    """
                    
                    params = {
                        "p_uid": firebase_uid, 
                        "p_candidate_limit": candidate_limit,
                        "p_exact_like": _contains_like_pattern(q_deaccented),
                    }
                    
                    sql, params = _apply_resource_type_filter(sql, params, resource_type)
                    sql, params = _apply_book_id_filter(sql, params, book_id)
                    sql, params = _apply_visibility_filter(sql, params, visibility_scope)
                    sql, params = _apply_content_type_filter(sql, params, content_type)
                    sql, params = _apply_ingestion_type_filter(sql, params, ingestion_type)
                    
                    # 1. TRY FIRST: Search without PDF (exclude raw PDF content)
                    if _should_exclude_pdf_in_first_pass(resource_type, book_id):
                        sql += " AND c.content_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK') "
                    
                    # 2. SEARCH CONDITION (bind-safe; escape LIKE wildcards)
                    sql += " AND text_deaccented LIKE :p_exact_like ESCAPE '\\' "

                    # 3. Simple Sort (Priority handled in Orchestrator)
                    sql += """
                        ORDER BY id DESC
                        FETCH FIRST :p_candidate_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    # 4. FALLBACK: If no results found and no resource_type filter, search including PDF content
                    if not rows and not resource_type and not book_id:
                        logger.info(f"ExactMatchStrategy: No results without PDF content, trying with PDF fallback")
                        sql_with_pdf = """
                            SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number, 
                                   c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT",
                                   c.item_id as book_id, c.normalized_content
                            FROM TOMEHUB_CONTENT_V2 c
                            LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                            WHERE c.firebase_uid = :p_uid
                              AND c.AI_ELIGIBLE = 1
                        """
                        sql_with_pdf += " AND text_deaccented LIKE :p_exact_like ESCAPE '\\' "
                        sql_with_pdf, params = _apply_visibility_filter(sql_with_pdf, params, visibility_scope)
                        sql_with_pdf, params = _apply_content_type_filter(sql_with_pdf, params, content_type)
                        sql_with_pdf, params = _apply_ingestion_type_filter(sql_with_pdf, params, ingestion_type)
                        sql_with_pdf += """
                            ORDER BY id DESC
                            FETCH FIRST :p_candidate_limit ROWS ONLY
                        """
                        cursor.execute(sql_with_pdf, params)
                        rows = cursor.fetchall()
                    
                    results = []
                    for r in rows:
                        content = safe_read_clob(r[1])
                        normalized_content = safe_read_clob(r[9])
                        if not _contains_exact_term_boundary(normalized_content or content, q_deaccented):
                            continue
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
                            'book_id': r[8],
                            'score': 100.0,
                            'match_type': 'exact_deaccented'
                        })
                        if len(results) >= limit:
                            break
                    return results

        except Exception as e:
            logger.error(f"ExactMatchStrategy failed: {e}", exc_info=True)
            return []

class LemmaMatchStrategy(SearchStrategy):
    """
    Strategy for Lemma-based matching (Fuzzy-ish).
    """
    def search(
        self,
        query: str,
        firebase_uid: str,
        limit: int = 1000,
        offset: int = 0,
        resource_type: Optional[str] = None,
        book_id: Optional[str] = None,
        visibility_scope: Optional[str] = None,
        content_type: Optional[str] = None,
        ingestion_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        lemmas = _filter_query_lemmas(get_lemmas(query))
        if not lemmas:
            return []
        lemma_candidates = lemmas[:5]
            
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    sql = """
                        SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number, 
                               c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT",
                               c.item_id as book_id, c.normalized_content
                        FROM TOMEHUB_CONTENT_V2 c
                        LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                        WHERE c.firebase_uid = :p_uid
                          AND c.AI_ELIGIBLE = 1
                    """
                    candidate_limit = min(max(limit * 4, limit + 40), 2500)
                    params = {"p_uid": firebase_uid, "p_candidate_limit": candidate_limit}
                    
                    sql, params = _apply_resource_type_filter(sql, params, resource_type)
                    sql, params = _apply_book_id_filter(sql, params, book_id)
                    sql, params = _apply_visibility_filter(sql, params, visibility_scope)
                    sql, params = _apply_content_type_filter(sql, params, content_type)
                    sql, params = _apply_ingestion_type_filter(sql, params, ingestion_type)

                    # 1. TRY FIRST: Search without PDF (exclude raw PDF content)
                    if _should_exclude_pdf_in_first_pass(resource_type, book_id):
                        sql += " AND c.content_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK') "
                    
                    lemma_conditions = []
                    for i, lemma in enumerate(lemma_candidates):
                        p_name = f"p_lemma_{i}"
                        lemma_conditions.append(f"lemma_tokens LIKE :{p_name}")
                        params[p_name] = f'%"{lemma}"%'
                    
                    if lemma_conditions:
                        sql += " AND (" + " OR ".join(lemma_conditions) + ")"
                    
                    # 3. Simple Sort (Priority handled in Orchestrator)
                    sql += """
                         ORDER BY id DESC
                         FETCH FIRST :p_candidate_limit ROWS ONLY
                    """
                    
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    
                    # 4. FALLBACK: If no results found and no resource_type filter, search including PDF content
                    if not rows and not resource_type and not book_id:
                        logger.info(f"LemmaMatchStrategy: No results without PDF content, trying with PDF fallback")
                        sql_with_pdf = """
                            SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number, 
                                   c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT",
                                   c.item_id as book_id, c.normalized_content
                            FROM TOMEHUB_CONTENT_V2 c
                            LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                            WHERE c.firebase_uid = :p_uid
                              AND c.AI_ELIGIBLE = 1
                        """
                        lemma_conditions_fb = []
                        for i, lemma in enumerate(lemma_candidates):
                            p_name = f"p_lemma_{i}"
                            lemma_conditions_fb.append(f"lemma_tokens LIKE :{p_name}")
                        
                        if lemma_conditions_fb:
                            sql_with_pdf += " AND (" + " OR ".join(lemma_conditions_fb) + ")"
                        sql_with_pdf, params = _apply_visibility_filter(sql_with_pdf, params, visibility_scope)
                        sql_with_pdf, params = _apply_content_type_filter(sql_with_pdf, params, content_type)
                        sql_with_pdf, params = _apply_ingestion_type_filter(sql_with_pdf, params, ingestion_type)
                        
                        sql_with_pdf += """
                             ORDER BY id DESC
                             FETCH FIRST :p_candidate_limit ROWS ONLY
                        """
                        cursor.execute(sql_with_pdf, params)
                        rows = cursor.fetchall()
                    
                    for r in rows:
                        content = safe_read_clob(r[1])
                        normalized_content = safe_read_clob(r[9])
                        haystack = normalized_content or content
                        if not any(_contains_lemma_stem_boundary(haystack, lemma) for lemma in lemma_candidates):
                            continue
                        hit_count = _count_lemma_stem_hits(haystack, lemma_candidates)
                        if hit_count <= 0:
                            continue
                        title = r[2] if isinstance(r[2], str) else safe_read_clob(r[2])
                        if (
                            len(lemma_candidates) == 1
                            and hit_count == 1
                            and _contains_inner_substring_only(title, lemma_candidates[0])
                        ):
                            continue
                        tags = safe_read_clob(r[5])
                        summary = safe_read_clob(r[6])
                        note = safe_read_clob(r[7])
                        title_boost = 4.0 if any(_contains_lemma_stem_boundary(title, lemma) for lemma in lemma_candidates) else 0.0
                        score = min(95.0, 70.0 + (hit_count * 5.0) + title_boost)
                        
                        results.append({
                            'id': r[0],
                            'title': title,
                            'content_chunk': content,
                            'source_type': r[3],
                            'page_number': r[4],
                            'tags': tags,
                            'summary': summary,
                            'comment': note,
                            'book_id': r[8],
                            'score': score,
                            'match_type': 'lemma_fuzzy'
                        })
                        if len(results) >= limit:
                            break
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
        
    def search(
        self,
        query: str,
        firebase_uid: str,
        limit: int = 100,
        offset: int = 0,
        intent: str = 'SYNTHESIS',
        resource_type: Optional[str] = None,
        book_id: Optional[str] = None,
        visibility_scope: Optional[str] = None,
        content_type: Optional[str] = None,
        ingestion_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        emb = self.get_embedding(query)
        if not emb:
            return []
            
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    results = []
                    
                    def run_query(custom_limit, length_filter=None, exclude_pdf=True):
                        sql = """
                            SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number,
                                   c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT", c.item_id as book_id,
                                   (VECTOR_DISTANCE(c.vec_embedding, :vec, COSINE) / NULLIF(c.rag_weight, 0.0001)) as dist
                            FROM TOMEHUB_CONTENT_V2 c
                            LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                            WHERE c.firebase_uid = :p_uid
                              AND c.AI_ELIGIBLE = 1
                        """
                        
                        params = {"p_uid": firebase_uid, "vec": emb, "p_limit": custom_limit}
                        
                        sql, params = _apply_resource_type_filter(sql, params, resource_type)
                        sql, params = _apply_book_id_filter(sql, params, book_id)
                        sql, params = _apply_visibility_filter(sql, params, visibility_scope)
                        sql, params = _apply_content_type_filter(sql, params, content_type)
                        sql, params = _apply_ingestion_type_filter(sql, params, ingestion_type)

                        # Apply PDF exclusion filter if requested and no resource_type
                        if exclude_pdf and _should_exclude_pdf_in_first_pass(resource_type, book_id):
                            sql += " AND c.content_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK') "

                        if length_filter:
                            if length_filter == 'SHORT':
                                sql += " AND DBMS_LOB.GETLENGTH(c.content_chunk) < 600 "
                            elif length_filter == 'LONG':
                                sql += " AND DBMS_LOB.GETLENGTH(c.content_chunk) > 600 "
                                
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
                    
                    # FALLBACK: If no results found and no resource_type filter, search including PDF content
                    if not rows and not resource_type and not book_id:
                        logger.info(f"SemanticMatchStrategy: No results without PDF content, trying with PDF fallback")
                        if intent == 'DIRECT' or intent == 'FOLLOW_UP':
                            sweep_limit = max(5, limit // 2)
                            rows.extend(run_query(sweep_limit, exclude_pdf=False))
                            rows.extend(run_query(sweep_limit, length_filter='SHORT', exclude_pdf=False))
                        elif intent == 'NARRATIVE':
                            rows.extend(run_query(15, exclude_pdf=False))
                            rows.extend(run_query(10, length_filter='LONG', exclude_pdf=False))
                        else:
                            rows.extend(run_query(limit, exclude_pdf=False))
                        
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
                        dist = r[9]
                        
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
                            'book_id': r[8],
                            'score': score,
                            'match_type': 'semantic'
                        })
                        
                    results.sort(key=lambda x: x['score'], reverse=True)
                    return results[:limit]

        except Exception as e:
            logger.error(f"SemanticMatchStrategy failed: {e}", exc_info=True)
            return []
