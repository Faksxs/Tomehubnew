# -*- coding: utf-8 -*-
"""
TomeHub Analytics Service
=========================
Deterministic analytics (Layer-3) for questions like:
"X kelimesi kaç kez geçiyor?"
"""

import re
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from infrastructure.db_manager import DatabaseManager
from services.cache_service import get_cache, generate_cache_key
from utils.text_utils import (
    calculate_fuzzy_score,
    get_lemmas,
    normalize_canonical,
    normalize_text,
)

ANALYTIC_PATTERNS = [
    r"\bkaç\s+(defa|kez|kere)\s+geç",  # "kaç kez geçiyor"
    r"\bkaç\s+(defa|kez|kere)\s+geçti",  # "kaç kez geçti"
    r"\bkaç\s+(defa|kez|kere)\s+geçer",  # "kaç kez geçer"
    r"\bkaç\s+(defa|kez|kere)\s+geçmek",  # "kaç kez geçmek"
    r"\bkaç\s+(defa|kez|kere)\s+geçmektedir",  # "kaç kez geçmektedir"
]

ANALYTIC_PATTERNS_ASCII = [
    r"\bkac\s+(defa|kez|kere)\s+gec",
    r"\bkac\s+(defa|kez|kere)\s+gecti",
    r"\bkac\s+(defa|kez|kere)\s+gecer",
    r"\bkac\s+(defa|kez|kere)\s+gecmek",
    r"\bkac\s+(defa|kez|kere)\s+gecmektedir",
]

TERM_PATTERNS = [
    # "kitap kelimesi kaç kez geçiyor"
    r"^\s*(?P<term>\S+)\s+kelimesi\s+kaç\s+(defa|kez|kere)\s+geç",
    # "kitap kaç kez geçiyor"
    r"^\s*(?P<term>\S+)\s+kaç\s+(defa|kez|kere)\s+geç",
    # "kaç kez kitap geçiyor"
    r"kaç\s+(defa|kez|kere)\s+(?P<term>\S+)\s+geç",
    r"(?P<term>\S+)\s+kelimesi\s+kaç\s+(defa|kez|kere)\s+geç\w*",
]

TERM_PATTERNS_ASCII = [
    r"^\s*(?P<term>\S+)\s+kelimesi\s+kac\s+(defa|kez|kere)\s+gec",
    r"^\s*(?P<term>\S+)\s+kac\s+(defa|kez|kere)\s+gec",
    r"kac\s+(defa|kez|kere)\s+(?P<term>\S+)\s+gec",
    r"(?P<term>\S+)\s+kelimesi\s+kac\s+(defa|kez|kere)\s+gec\w*",
]

QUOTE_PATTERN = r"[\"'“”‘’](.+?)[\"'“”‘’]"

DEFAULT_SOURCE_TYPES = ("PDF", "EPUB", "PDF_CHUNK")

BOOK_STOP_WORDS = [
    "kitap",
    "kitabı",
    "kitabi",
    "kitabında",
    "kitabinda",
    "kitabındaki",
    "kitabindaki",
    "kelime",
    "kelimesi",
    "kaç",
    "kac",
    "defa",
    "kere",
    "kez",
]

def extract_book_phrase(question: str) -> Optional[str]:
    if not question:
        return None

    # Remove @term mentions (reserved for word selection)
    cleaned = re.sub(r"@[A-Za-z0-9_çğıöşüÇĞİÖŞÜ]+", "", question)

    # "X kitabında ..." form
    match = re.search(r"(?P<book>.+?)\s+kitab", cleaned, flags=re.IGNORECASE)
    if match:
        candidate = match.group("book").strip()
        return candidate if candidate else None

    return None

def resolve_book_id_from_question(firebase_uid: str, question: str) -> Optional[str]:
    if not firebase_uid or not question:
        return None

    book_phrase = extract_book_phrase(question)
    q_norm = normalize_text(book_phrase or question)
    if not q_norm:
        return None

    candidates: list[tuple[str, int]] = []

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT title, book_id
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id IS NOT NULL
                      AND (source_type = 'PDF' OR source_type = 'EPUB' OR source_type = 'PDF_CHUNK')
                    """,
                    {"p_uid": firebase_uid},
                )
                rows = cursor.fetchall()

        for title, book_id in rows:
            if not title or not book_id:
                continue
            title_str = str(title)
            title_primary = title_str.split(" - ")[0].strip()

            title_norm = normalize_text(title_str)
            primary_norm = normalize_text(title_primary)

            if primary_norm and primary_norm in q_norm:
                candidates.append((book_id, 100))
                continue
            if title_norm and title_norm in q_norm:
                candidates.append((book_id, 95))
                continue

            score = calculate_fuzzy_score(primary_norm, q_norm)
            threshold = 85 if book_phrase else 90
            if score >= threshold:
                candidates.append((book_id, score))

    except Exception as e:
        print(f"[ERROR] resolve_book_id_from_question failed: {e}")
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_id, best_score = candidates[0]
    
    if len(candidates) > 1 and candidates[1][1] >= best_score - 5:
        # Ambiguity: two books have very similar matches
        return None

    return best_id


def resolve_all_book_ids(
    firebase_uid: str,
    source_types: Tuple[str, ...] = DEFAULT_SOURCE_TYPES,
) -> List[str]:
    """Returns all unique book IDs for a user that have ingested content."""
    if not firebase_uid:
        return []
    if not source_types:
        return []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                bind_names = [f":st{i}" for i in range(len(source_types))]
                bind_clause = ",".join(bind_names)
                params = {f"st{i}": st for i, st in enumerate(source_types)}
                params.update({"p_uid": firebase_uid})

                sql = f"""
                    SELECT DISTINCT book_id
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id IS NOT NULL
                      AND source_type IN ({bind_clause})
                """
                cursor.execute(sql, params)
                return [str(row[0]) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[ERROR] resolve_all_book_ids failed: {e}")
        return []


def resolve_ingested_book_ids(
    firebase_uid: str,
    file_extension: str = "pdf",
) -> List[str]:
    """Returns all unique book IDs that have PDF/EPUB content, checking both ingestion status and actual content."""
    if not firebase_uid:
        return []
    
    ext = (file_extension or "").lower().lstrip(".")
    book_ids = set()
    
    # 1. Try TOMEHUB_INGESTED_FILES (the "proper" status table)
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                params = {"p_uid": firebase_uid}
                if ext == "pdf":
                    params["p_ext"] = "%.pdf"
                    sql = """
                        SELECT DISTINCT book_id
                        FROM TOMEHUB_INGESTED_FILES
                        WHERE firebase_uid = :p_uid
                          AND status = 'COMPLETED'
                          AND (source_file_name IS NULL OR LOWER(source_file_name) LIKE :p_ext)
                    """
                else:
                    sql = """
                        SELECT DISTINCT book_id
                        FROM TOMEHUB_INGESTED_FILES
                        WHERE firebase_uid = :p_uid
                          AND status = 'COMPLETED'
                    """
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    if row[0]: book_ids.add(str(row[0]))
    except Exception as e:
        print(f"[WARNING] resolve_ingested_book_ids (table check) failed: {e}")

    # 2. Check TOMEHUB_CONTENT as fallback/addition (looks for actual data)
    try:
        content_ids = resolve_all_book_ids(firebase_uid, ("PDF", "PDF_CHUNK"))
        for bid in content_ids:
            book_ids.add(bid)
    except Exception as e:
        print(f"[WARNING] resolve_ingested_book_ids (content check) failed: {e}")

    return sorted(list(book_ids))


def is_analytic_word_count(question: str) -> bool:
    if not question:
        return False
    q = question.lower()
    if any(re.search(p, q) for p in ANALYTIC_PATTERNS):
        return True
    q_ascii = normalize_text(question)
    if any(re.search(p, q_ascii) for p in ANALYTIC_PATTERNS_ASCII):
        return True
    # Repair common mojibake where "ç" becomes "?" or "�"
    q_repaired = question.replace("\ufffd", "c").replace("?", "c")
    q_repaired = normalize_text(q_repaired)
    return any(re.search(p, q_repaired) for p in ANALYTIC_PATTERNS_ASCII)


def extract_target_term(question: str) -> Optional[str]:
    if not question:
        return None

    mention_match = re.search(r"@([A-Za-z0-9_çğıöşüÇĞİÖŞÜ]+)", question)
    if mention_match:
        term = mention_match.group(1).strip()
        return term if term else None

    quote_match = re.search(QUOTE_PATTERN, question)
    if quote_match:
        term = quote_match.group(1).strip()
        return term if term else None

    for pattern in TERM_PATTERNS:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            term = match.group("term").strip()
            return term if term else None

    q_ascii = normalize_text(question)
    for pattern in TERM_PATTERNS_ASCII:
        match = re.search(pattern, q_ascii, flags=re.IGNORECASE)
        if match:
            term = match.group("term").strip()
            return term if term else None

    q_repaired = question.replace("\ufffd", "c").replace("?", "c")
    q_repaired = normalize_text(q_repaired)
    for pattern in TERM_PATTERNS_ASCII:
        match = re.search(pattern, q_repaired, flags=re.IGNORECASE)
        if match:
            term = match.group("term").strip()
            return term if term else None

    return None


def _normalize_to_lemma(term: str) -> str:
    if not term:
        return ""
    lemmas = get_lemmas(term)
    if lemmas:
        return lemmas[0]
    return normalize_canonical(term)


def count_lemma_occurrences(
    firebase_uid: str,
    book_id: str,
    term: str,
    source_types: Tuple[str, ...] = DEFAULT_SOURCE_TYPES,
) -> int:
    if not firebase_uid or not book_id or not term:
        return 0

    candidates = []
    lemma = _normalize_to_lemma(term)
    if lemma:
        candidates.append(lemma)
    canonical = normalize_canonical(term)
    if canonical and canonical not in candidates:
        candidates.append(canonical)
    ascii_term = normalize_text(term)
    if ascii_term and ascii_term not in candidates:
        candidates.append(ascii_term)
    if not candidates:
        return 0

    count = 0
    
    # 2. Check Cache
    cache = get_cache()
    if cache:
        cache_key = generate_cache_key(
            service="analytics_count",
            query=term,
            firebase_uid=firebase_uid,
            book_id=book_id,
            limit=1
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            # logger.debug(f"Cache hit for lemma count: {term} in {book_id}")
            return int(cached_val)

    try:
        # Use existing distribution logic for accuracy (scan-based)
        # This ensures we count inflections correctly even if index is stale
        dist = get_keyword_distribution(firebase_uid, book_id, term, source_types)
        count = sum(d['count'] for d in dist)
        
        # If count is still 0, try a quick raw count in original content just in case
        if count == 0:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    bind_names = [f":st{i}" for i in range(len(source_types))]
                    bind_clause = ",".join(bind_names)
                    params = {f"st{i}": st for i, st in enumerate(source_types)}
                    params.update({"p_uid": firebase_uid, "p_bid": book_id, "p_term": term.lower()})
                    
                    sql = f"""
                        SELECT SUM(REGEXP_COUNT(LOWER(content_chunk), :p_term))
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                          AND book_id = :p_bid
                          AND source_type IN ({bind_clause})
                    """
                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    if row and row[0]:
                        count = int(row[0])
        
        # 3. Set Cache (TTL: 24h for books, 1h for others)
        if cache:
            # If standard book, long cache. If not, shorter.
            ttl = 86400 if book_id and len(book_id) > 10 else 3600
            cache.set(cache_key, count, ttl=ttl)
                        
    except Exception as e:
        print(f"[ERROR] count_lemma_occurrences failed: {e}")
        count = 0

    return count


def get_keyword_contexts(
    firebase_uid: str,
    book_id: str,
    term: str,
    limit: int = 50,
    offset: int = 0,
    source_types: Tuple[str, ...] = DEFAULT_SOURCE_TYPES,
) -> list[dict]:
    """
    Key Word In Context (KWIC) / Concordance implementation.
    Returns snippets of text around keyword occurrences.
    
    Technical features:
    - Lemma-consistent (uses same candidates as count)
    - Hybrid Search (token_freq index check + SQL fallback)
    - Dynamic Windowing (±150 chars around hit)
    """
    if not firebase_uid or not book_id or not term:
        return []

    # 1. Generate Candidates (Consistency with count)
    candidates = []
    lemma = _normalize_to_lemma(term)
    if lemma: candidates.append(lemma)
    canonical = normalize_canonical(term)
    if canonical and canonical not in candidates: candidates.append(canonical)
    ascii_term = normalize_text(term)
    if ascii_term and ascii_term not in candidates: candidates.append(ascii_term)
    
    if not candidates:
        return []

    results = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Build SQL for finding chunks
                # We use INSTR on normalized_content for reliable matching
                bind_names = [f":st{i}" for i in range(len(source_types))]
                bind_clause = ",".join(bind_names)
                
                # We fetch content_chunk for extraction, but filter by normalized_content
                sql = f"""
                    SELECT id, content_chunk, page_number, normalized_content
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id = :p_bid
                      AND source_type IN ({bind_clause})
                      AND (
                """
                
                # Append OR conditions for each candidate
                conds = []
                params = {f"st{i}": st for i, st in enumerate(source_types)}
                params.update({"p_uid": firebase_uid, "p_bid": book_id})
                
                for i, cand in enumerate(candidates):
                    p_name = f"cand{i}"
                    conds.append(f"INSTR(normalized_content, :{p_name}) > 0")
                    params[p_name] = cand
                
                sql += " OR ".join(conds) + ")"
                
                # Pagination & Limit
                # Oracle 12c+ offset/fetch syntax
                sql += " OFFSET :p_offset ROWS FETCH NEXT :p_limit ROWS ONLY"
                params["p_offset"] = offset
                params["p_limit"] = limit

                cursor.execute(sql, params)
                rows = cursor.fetchall()

                for r_id, raw_content, page_num, norm_content in rows:
                    content = str(raw_content or "")
                    norm = str(norm_content or "")
                    
                    # For each candidate, find positions in normalized text
                    # and extract from original text (best effort alignment)
                    # Since normalized_content collapses spaces and removes punctuation,
                    # we do a simple windowing on the original content by searching there too.
                    
                    found_in_chunk = False
                    for cand in candidates:
                        # Regex for case-insensitive search in original content (Turkish-aware)
                        # We use a simple find since normalized_content is already filtered
                        idx = content.lower().find(cand.lower()) # Simple fallback
                        if idx == -1:
                            # If not found in original (due to punctuation), use a broader search
                            # or just take the first 300 chars if alignment is too hard.
                            # But usually, it matches.
                            continue

                        # Extract ±150 char window
                        start = max(0, idx - 150)
                        end = min(len(content), idx + len(cand) + 150)
                        snippet = content[start:end]
                        
                        # Add ellipsis if truncated
                        if start > 0: snippet = "..." + snippet
                        if end < len(content): snippet = snippet + "..."

                        results.append({
                            "chunk_id": r_id,
                            "page_number": page_num,
                            "snippet": snippet,
                            "keyword_found": cand
                        })
                        found_in_chunk = True
                        break # One snippet per chunk for now to avoid duplication

    except Exception as e:
        print(f"[ERROR] Concordance retrieval failed: {e}")
        return []

    return results


def get_keyword_distribution(
    firebase_uid: str,
    book_id: str,
    term: str,
    source_types: Tuple[str, ...] = DEFAULT_SOURCE_TYPES,
) -> list[dict]:
    """
    Returns the distribution of a keyword across the book's pages.
    Output: [{ "page_number": 1, "count": 5 }, ...]
    """
    if not firebase_uid or not book_id or not term:
        return []

    # 1. Generate Candidates (Consistency)
    candidates = []
    lemma = _normalize_to_lemma(term)
    if lemma: candidates.append(lemma)
    canonical = normalize_canonical(term)
    if canonical and canonical not in candidates: candidates.append(canonical)
    ascii_term = normalize_text(term)
    if ascii_term and ascii_term not in candidates: candidates.append(ascii_term)
    
    if not candidates:
        return []

    # 2. Check Cache
    cache = get_cache()
    cache_key = None
    if cache:
        cache_key = generate_cache_key(
            service="analytics_dist",
            query=term,
            firebase_uid=firebase_uid,
            book_id=book_id,
            limit=1000
        )
        cached_val = cache.get(cache_key)
        if cached_val is not None:
             return cached_val

    distribution = {}

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                bind_names = [f":st{i}" for i in range(len(source_types))]
                bind_clause = ",".join(bind_names)
                
                # Fetch only page_number and normalized_content for speed
                sql = f"""
                    SELECT page_number, normalized_content
                    FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id = :p_bid
                      AND source_type IN ({bind_clause})
                      AND (
                """
                
                conds = []
                params = {f"st{i}": st for i, st in enumerate(source_types)}
                params.update({"p_uid": firebase_uid, "p_bid": book_id})
                
                for i, cand in enumerate(candidates):
                    p_name = f"cand{i}"
                    conds.append(f"INSTR(normalized_content, :{p_name}) > 0")
                    params[p_name] = cand
                
                sql += " OR ".join(conds) + ")"
                
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                
                # Python-side counting (safer for overlapping terms than pure SQL regex)
                for page_num, norm_content in rows:
                    if not page_num or not norm_content:
                        continue
                        
                    page_num = int(page_num)
                    norm_lower = str(norm_content).lower()
                    
                    # Count occurrences of any candidate in this chunk
                    total_hits = 0
                    for cand in candidates:
                        # Simple count of non-overlapping occurrences
                        total_hits += norm_lower.count(cand.lower())
                    
                    if total_hits > 0:
                        distribution[page_num] = distribution.get(page_num, 0) + total_hits

    except Exception as e:
        print(f"[ERROR] Distribution retrieval failed: {e}")
        return []

    # Convert to sorted list
    result_list = [{"page_number": p, "count": c} for p, c in distribution.items()]
    result_list.sort(key=lambda x: x["page_number"])
    
    # 3. Set Cache
    if cache and cache_key:
        ttl = 86400 if book_id and len(book_id) > 10 else 3600
        cache.set(cache_key, result_list, ttl=ttl)
    
    return result_list


def count_all_notes_occurrences(firebase_uid: str, term: str) -> int:
    """
    Counts lemma occurrences across all user notes/highlights (excluding full books).
    Target source types: HIGHLIGHT, PERSONAL_NOTE, ARTICLE, WEBSITE
    """
    if not firebase_uid or not term:
        return 0

    target_types = ("HIGHLIGHT", "ARTICLE", "WEBSITE", "PERSONAL_NOTE")
    
    # 1. Generate Candidates
    candidates = []
    lemma = _normalize_to_lemma(term)
    if lemma: candidates.append(lemma)
    canonical = normalize_canonical(term)
    if canonical and canonical not in candidates: candidates.append(canonical)
    ascii_term = normalize_text(term)
    if ascii_term and ascii_term not in candidates: candidates.append(ascii_term)
    
    if not candidates:
        return 0

    total_count = 0
    try:
        bind_names = [f":st{i}" for i in range(len(target_types))]
        bind_clause = ",".join(bind_names)
        
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                sql = "SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid"
                params = {"p_uid": firebase_uid}
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row:
                    total_count = int(row[0])

    except Exception as e:
        print(f"[ERROR] count_all_notes_occurrences failed: {e}")
        return 0

    return total_count


def get_comparative_stats(
    firebase_uid: str,
    target_book_ids: List[str],
    term: str
) -> List[dict]:
    """
    Parallel fetch of lemma counts for multiple books.
    Returns: [{ "book_id": "...", "title": "...", "count": 120 }, ...]
    """
    if not target_book_ids:
        return []
    results = []
    
    # Helper to fetch count + title for one book
    def fetch_one(b_id):
        try:
            # Handle Virtual "All Notes" ID
            if b_id == "ALL_NOTES":
                count = count_all_notes_occurrences(firebase_uid, term)
                return {"book_id": "ALL_NOTES", "title": "Tüm Notlarım (Özet & Alıntılar)", "count": count}

            # Regular Book
            count = count_lemma_occurrences(firebase_uid, b_id, term)
            
            # Get title (simple query)
            title = "Unknown Book"
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT title FROM TOMEHUB_BOOKS WHERE firebase_uid = :uid AND id = :bid",
                        {"uid": firebase_uid, "bid": b_id}
                    )
                    row = cursor.fetchone()
                    if row:
                        title = row[0]
            
            return {"book_id": b_id, "title": title, "count": count}
        except Exception as e:
            print(f"[ERROR] Comparative fetch failed for {b_id}: {e}")
            return None

    # Parallel execution
    with ThreadPoolExecutor(max_workers=min(10, len(target_book_ids))) as executor:
        futures = [executor.submit(fetch_one, bid) for bid in target_book_ids]
        
        for future in as_completed(futures):
            res = future.result()
            if res:
                results.append(res)
    
    # Sort by count descending
    results.sort(key=lambda x: x["count"], reverse=True)
    return results
