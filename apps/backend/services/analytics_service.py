# -*- coding: utf-8 -*-
"""
TomeHub Analytics Service
=========================
Deterministic analytics (Layer-3) for questions like:
"X kelimesi kaç kez geçiyor?"
"""

import re
from typing import Optional, Tuple

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
                      AND source_type IN ('PDF','EPUB','PDF_CHUNK')
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

    except Exception:
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_id, best_score = candidates[0]
    if len(candidates) > 1 and candidates[1][1] >= best_score - 5:
        return None

    return best_id


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
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Build IN clause
                bind_names = [f":st{i}" for i in range(len(source_types))]
                bind_clause = ",".join(bind_names)
                params = {f"st{i}": st for i, st in enumerate(source_types)}
                params.update({"p_uid": firebase_uid, "p_bid": book_id})

                for candidate in candidates:
                    # Sanitize candidate for JSON path usage
                    safe_candidate = candidate.replace('"', '\\"')
                    json_path = f'$."{safe_candidate}"'

                    sql = f"""
                        SELECT NVL(SUM(
                            JSON_VALUE(
                                token_freq,
                                '{json_path}'
                                RETURNING NUMBER
                                DEFAULT 0 ON ERROR
                                DEFAULT 0 ON EMPTY
                            )
                        ), 0)
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                          AND book_id = :p_bid
                          AND source_type IN ({bind_clause})
                          AND token_freq IS NOT NULL
                    """

                    cursor.execute(sql, params)
                    row = cursor.fetchone()
                    if row:
                        value = int(row[0] or 0)
                        if value > count:
                            count = value
    except Exception:
        # Fail safe: return 0 on errors (non-blocking analytics)
        count = 0

    return count
