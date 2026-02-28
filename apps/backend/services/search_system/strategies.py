from typing import List, Dict, Any, Optional
import os
import logging
import re
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.text_utils import deaccent_text, get_lemmas, repair_common_mojibake
from config import settings

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


def _is_oracle_text_exact_enabled() -> bool:
    # Oracle Text should be first-path by default; legacy LIKE remains emergency fallback.
    return os.getenv("SEARCH_EXACT_ORACLE_TEXT_ENABLED", "true").strip().lower() == "true"


def _is_oracle_text_single_token_enabled() -> bool:
    return os.getenv("SEARCH_EXACT_ORACLE_TEXT_SINGLE_TOKEN_ENABLED", "true").strip().lower() == "true"


def _oracle_text_min_rows_for_backfill() -> int:
    # Default=1 keeps backfill disabled for non-empty Oracle Text hits.
    # Legacy LIKE is still used when Oracle returns zero rows or errors.
    raw = os.getenv("SEARCH_EXACT_ORACLE_TEXT_MIN_ROWS", "1").strip()
    try:
        value = int(raw)
    except Exception:
        value = 1
    if value < 1:
        value = 1
    if value > 500:
        value = 500
    return value


def _build_oracle_text_query(raw_query: str) -> str:
    """
    Build a conservative Oracle Text query from user input.
    - Normalize/deaccent first
    - Keep only alphanumeric tokens
    - Join with AND for precision
    """
    normalized = _normalize_match_text(raw_query or "")
    tokens = [t for t in normalized.split(" ") if t and len(t) >= 2]
    if not tokens:
        return ""
    # Cap token count to keep query parser cost bounded.
    tokens = tokens[:8]
    return " AND ".join(tokens)


def _should_use_oracle_text_for_query(raw_query: str) -> bool:
    normalized = _normalize_match_text(raw_query or "")
    tokens = [t for t in normalized.split(" ") if t and len(t) >= 2]
    if len(tokens) >= 2:
        return True
    if len(tokens) == 1 and _is_oracle_text_single_token_enabled():
        return True
    return False


def _merge_rows_prefer_first(primary_rows: List[Any], secondary_rows: List[Any], max_rows: int) -> List[Any]:
    """
    Merge two row lists by row-id (r[0]), preserving primary order.
    """
    out: List[Any] = []
    seen_ids = set()

    for row in primary_rows or []:
        row_id = row[0] if row else None
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        out.append(row)
        if len(out) >= max_rows:
            return out

    for row in secondary_rows or []:
        row_id = row[0] if row else None
        if row_id in seen_ids:
            continue
        seen_ids.add(row_id)
        out.append(row)
        if len(out) >= max_rows:
            break
    return out


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

    uses_v2_alias = " c." in sql or " c " in sql
    field = "c.content_type" if uses_v2_alias else "source_type"

    if rt == "BOOK":
        if field == "source_type":
            sql += " AND source_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT', 'NOTES') "
        else:
            sql += " AND c.content_type IN ('PDF', 'EPUB', 'PDF_CHUNK', 'BOOK', 'HIGHLIGHT', 'INSIGHT') "
    elif rt == "ALL_NOTES":
        if field == "source_type":
            sql += " AND source_type IN ('HIGHLIGHT', 'INSIGHT', 'NOTES') "
        else:
            sql += " AND c.content_type IN ('HIGHLIGHT', 'INSIGHT') "
    elif rt == "PERSONAL_NOTE":
        sql += f" AND {field} = 'PERSONAL_NOTE' "
    elif rt in {"ARTICLE", "WEBSITE"}:
        sql += f" AND {field} = :p_res_type "
        params["p_res_type"] = rt
    else:
        # Backward-compatible strict mode for custom/legacy values.
        sql += f" AND {field} = :p_res_type "
        params["p_res_type"] = rt

    return (sql, params)


def _apply_book_id_filter(sql: str, params: Dict[str, Any], book_id: Optional[str]) -> tuple:
    bid = str(book_id or "").strip()
    if bid:
        uses_v2_alias = " c." in sql or " c " in sql
        if uses_v2_alias:
            sql += " AND c.item_id = :p_book_id "
        else:
            sql += " AND book_id = :p_book_id "
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

                    base_sql = """
                        SELECT c.id, c.content_chunk, c.title, c.content_type as source_type, c.page_number, 
                               c.tags_json as tags, l.summary_text as summary, c.comment_text as "COMMENT",
                               c.item_id as book_id, c.normalized_content
                        FROM TOMEHUB_CONTENT_V2 c
                        LEFT JOIN TOMEHUB_LIBRARY_ITEMS l ON c.item_id = l.item_id AND c.firebase_uid = l.firebase_uid
                        WHERE c.firebase_uid = :p_uid
                          AND c.AI_ELIGIBLE = 1
                    """

                    base_params = {
                        "p_uid": firebase_uid,
                        "p_candidate_limit": candidate_limit,
                    }
                    exact_like_pattern = _contains_like_pattern(q_deaccented)

                    oracle_text_query = _build_oracle_text_query(query)
                    oracle_text_enabled = (
                        _is_oracle_text_exact_enabled()
                        and bool(oracle_text_query)
                        and _should_use_oracle_text_for_query(query)
                    )
                    min_rows_for_backfill = _oracle_text_min_rows_for_backfill()

                    def _run_exact_query(include_pdf: bool, use_oracle_text: bool) -> List[Any]:
                        sql = base_sql
                        params = dict(base_params)

                        sql, params = _apply_resource_type_filter(sql, params, resource_type)
                        sql, params = _apply_book_id_filter(sql, params, book_id)
                        sql, params = _apply_visibility_filter(sql, params, visibility_scope)
                        sql, params = _apply_content_type_filter(sql, params, content_type)
                        sql, params = _apply_ingestion_type_filter(sql, params, ingestion_type)

                        if not include_pdf and _should_exclude_pdf_in_first_pass(resource_type, book_id):
                            sql += " AND c.content_type NOT IN ('PDF', 'EPUB', 'PDF_CHUNK') "

                        if use_oracle_text:
                            params["p_oracle_text_query"] = oracle_text_query
                            sql += " AND CONTAINS(c.content_chunk, :p_oracle_text_query, 1) > 0 "
                        else:
                            params["p_exact_like"] = exact_like_pattern
                            sql += " AND c.normalized_content LIKE :p_exact_like ESCAPE '\\' "

                        sql += """
                            ORDER BY id DESC
                            FETCH FIRST :p_candidate_limit ROWS ONLY
                        """
                        cursor.execute(sql, params)
                        return cursor.fetchall()

                    rows: List[Any] = []
                    match_mode = "exact_deaccented"

                    # First pass: prefer Oracle Text (feature-flagged), fallback to legacy LIKE.
                    if oracle_text_enabled:
                        try:
                            rows = _run_exact_query(include_pdf=False, use_oracle_text=True)
                            match_mode = "exact_oracle_text"
                            if len(rows) < min_rows_for_backfill:
                                legacy_rows = _run_exact_query(include_pdf=False, use_oracle_text=False)
                                rows = _merge_rows_prefer_first(rows, legacy_rows, candidate_limit)
                                match_mode = "exact_oracle_text_backfill"
                        except Exception as oracle_err:
                            logger.warning(
                                "ExactMatchStrategy Oracle Text disabled for this request due to error: %s",
                                oracle_err,
                            )
                            rows = []

                    if not rows:
                        rows = _run_exact_query(include_pdf=False, use_oracle_text=False)
                        match_mode = "exact_deaccented"

                    # Fallback pass with PDF included (only when query is not scoped).
                    if not rows and not resource_type and not book_id:
                        logger.info("ExactMatchStrategy: no first-pass results, trying PDF-inclusive fallback")
                        if oracle_text_enabled:
                            try:
                                rows = _run_exact_query(include_pdf=True, use_oracle_text=True)
                                match_mode = "exact_oracle_text"
                                if len(rows) < min_rows_for_backfill:
                                    legacy_rows = _run_exact_query(include_pdf=True, use_oracle_text=False)
                                    rows = _merge_rows_prefer_first(rows, legacy_rows, candidate_limit)
                                    match_mode = "exact_oracle_text_backfill"
                            except Exception as oracle_err:
                                logger.warning(
                                    "ExactMatchStrategy Oracle Text fallback failed, using legacy LIKE: %s",
                                    oracle_err,
                                )
                                rows = []
                        if not rows:
                            rows = _run_exact_query(include_pdf=True, use_oracle_text=False)
                            match_mode = "exact_deaccented"
                    
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
                            'match_type': match_mode
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


class OdlShadowRescueStrategy(SearchStrategy):
    """
    Strategy for ODL secondary rescue retrieval.
    Reads additive candidates from TOMEHUB_CONTENT_ODL_SHADOW.
    """

    def search(
        self,
        query: str,
        firebase_uid: str,
        limit: int = 8,
        offset: int = 0,
        resource_type: Optional[str] = None,
        book_id: Optional[str] = None,
        visibility_scope: Optional[str] = None,
        content_type: Optional[str] = None,
        ingestion_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # ODL shadow only serves PDF-like chunks.
        if content_type and str(content_type).strip().upper() not in {"PDF", "EPUB", "PDF_CHUNK"}:
            return []
        if resource_type:
            rt = str(resource_type).strip().upper()
            if rt not in {"BOOK", "PDF", "PDF_CHUNK", "EPUB"}:
                return []
        if not bool(getattr(settings, "ODL_RESCUE_ENABLED", False)):
            return []

        query_text = str(query or "").strip()
        if not query_text:
            return []
        q_deaccented = deaccent_text(query_text)
        lemma_candidates = _filter_query_lemmas(get_lemmas(query_text))[:6]

        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    candidate_limit = min(max(int(limit or 8) * 24, 200), 1200)
                    sql = """
                        SELECT
                            s.ID, s.CONTENT_CHUNK, s.TITLE, s.PAGE_NUMBER, s.CHUNK_INDEX,
                            s.NORMALIZED_CONTENT, s.LEMMA_TOKENS, s.ITEM_ID, s.CONTENT_HASH
                        FROM TOMEHUB_CONTENT_ODL_SHADOW s
                        LEFT JOIN TOMEHUB_LIBRARY_ITEMS l
                            ON s.ITEM_ID = l.ITEM_ID AND s.FIREBASE_UID = l.FIREBASE_UID
                        WHERE s.FIREBASE_UID = :p_uid
                          AND EXISTS (
                              SELECT 1
                              FROM TOMEHUB_ODL_SHADOW_STATUS st
                              WHERE st.FIREBASE_UID = s.FIREBASE_UID
                                AND st.ITEM_ID = s.ITEM_ID
                                AND st.STATUS = 'READY'
                          )
                    """
                    params: Dict[str, Any] = {"p_uid": firebase_uid, "p_candidate_limit": candidate_limit}
                    sql, params = _apply_book_id_filter(sql, params, book_id)
                    sql, params = _apply_visibility_filter(sql, params, visibility_scope)
                    sql += """
                        ORDER BY s.CREATED_AT DESC, NVL(s.PAGE_NUMBER, 0), NVL(s.CHUNK_INDEX, 0)
                        FETCH FIRST :p_candidate_limit ROWS ONLY
                    """
                    cursor.execute(sql, params)
                    rows = cursor.fetchall() or []

                    out: List[Dict[str, Any]] = []
                    for r in rows:
                        content = safe_read_clob(r[1])
                        normalized = safe_read_clob(r[5]) or content
                        if not content:
                            continue

                        exact_hit = _contains_exact_term_boundary(normalized, q_deaccented)
                        lemma_hits = _count_lemma_stem_hits(normalized, lemma_candidates) if lemma_candidates else 0
                        if not exact_hit and lemma_hits <= 0:
                            continue

                        score = 0.0
                        if exact_hit:
                            score = 65.0 + min(20.0, len(query_text.split()) * 2.0) + min(10.0, float(lemma_hits) * 2.0)
                            match_type = "odl_shadow_exact"
                        else:
                            score = 40.0 + min(35.0, float(lemma_hits) * 5.0)
                            match_type = "odl_shadow_lemma"

                        title = str(r[2] or "")
                        if title and (
                            _contains_exact_term_boundary(title, q_deaccented)
                            or any(_contains_lemma_stem_boundary(title, lm) for lm in lemma_candidates)
                        ):
                            score += 4.0

                        out.append(
                            {
                                "id": f"odl:{r[0]}",
                                "title": title,
                                "content_chunk": content,
                                "source_type": "ODL_SHADOW",
                                "page_number": r[3],
                                "chunk_index": r[4],
                                "tags": None,
                                "summary": None,
                                "comment": None,
                                "book_id": str(r[7] or ""),
                                "score": min(99.0, score),
                                "match_type": match_type,
                                "odl_shadow": True,
                                "content_hash": str(r[8] or ""),
                            }
                        )
                        if len(out) >= int(limit or 8):
                            break
                    return out
        except Exception as e:
            if "ORA-00942" not in str(e):
                logger.warning("OdlShadowRescueStrategy failed", exc_info=True)
            return []
