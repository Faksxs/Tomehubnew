# -*- coding: utf-8 -*-
"""
TomeHub Book Ingestion Pipeline
================================
Master script to automate the complete data ingestion flow:
PDF/EPUB → Text Extraction → Embedding Generation → Oracle Database Storage

Author: TomeHub Team
Date: 2026-01-09
"""

import os
import sys
import hashlib
import threading
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import oracledb
import uuid

# Import TomeHub services
from services.pdf_service import extract_pdf_content
from services.epub_service import extract_epub_content
from services.embedding_service import get_embedding, batch_get_embeddings
from services.correction_service import LinguisticCorrectionService

# Initialize the linguistic corrector (loads dictionary once)
corrector_service = LinguisticCorrectionService()
from services.data_health_service import DataHealthService
from services.data_cleaner_service import DataCleanerService
from utils.text_utils import normalize_text, deaccent_text, get_lemmas, get_lemma_frequencies
from utils.tag_utils import prepare_labels
import json
from concurrent.futures import ThreadPoolExecutor
from utils.logger import get_logger
from config import settings

logger = get_logger("ingestion_service")
from services.monitoring import (
    INGESTION_LATENCY,
    DATA_CLEANER_AI_APPLIED_TOTAL,
    DATA_CLEANER_AI_SKIPPED_TOTAL,
    DATA_CLEANER_NOISE_SCORE,
)
from services.epistemic_distribution_service import (
    delete_epistemic_distribution,
    maybe_trigger_epistemic_distribution_refresh_async,
)
import time

# Phase 6: Semantic Classification at Ingest Time
try:
    from services.semantic_classifier import classify_passage_fast
except ImportError:
    # Fallback if module not available
    def classify_passage_fast(text):
        return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.5}
# Load environment variables - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)



from infrastructure.db_manager import DatabaseManager, acquire_lock

# Removed local get_database_connection


def _runtime_log(message: str, level: str = "info") -> None:
    normalized = (level or "info").lower()
    msg = str(message)
    if normalized == "info":
        lowered = msg.lower()
        if "[error]" in lowered:
            normalized = "error"
        elif "[warning]" in lowered or "[warn]" in lowered:
            normalized = "warning"
        elif "[debug]" in lowered:
            normalized = "debug"
    if normalized == "debug":
        if settings.DEBUG_VERBOSE_PIPELINE:
            logger.debug(msg)
        return
    if normalized == "warning":
        logger.warning(msg)
        return
    if normalized == "error":
        logger.error(msg)
        return
    logger.info(msg)

def _insert_content_categories(cursor, content_id: int, prepared_categories):
    if not prepared_categories:
        return
    for raw, norm in prepared_categories:
        try:
            cursor.execute(
                """
                INSERT INTO TOMEHUB_CONTENT_CATEGORIES (content_id, category, category_norm)
                VALUES (:p_cid, :p_cat, :p_norm)
                """,
                {"p_cid": content_id, "p_cat": raw, "p_norm": norm},
            )
        except oracledb.IntegrityError:
            # Duplicate category for this content_id
            pass


def _insert_content_tags(cursor, content_id: int, prepared_tags):
    if not prepared_tags:
        return
    for raw, norm in prepared_tags:
        try:
            cursor.execute(
                """
                INSERT INTO TOMEHUB_CONTENT_TAGS (content_id, tag, tag_norm)
                VALUES (:p_cid, :p_tag, :p_norm)
                """,
                {"p_cid": content_id, "p_tag": raw, "p_norm": norm},
            )
        except oracledb.IntegrityError:
            # Duplicate tag for this content_id
            pass


def normalize_source_type(source_type: Optional[str]) -> str:
    """
    Normalize incoming source types to canonical values.
    Canonical set: PDF, EPUB, PDF_CHUNK, BOOK, ARTICLE, WEBSITE, PERSONAL_NOTE, HIGHLIGHT, INSIGHT
    """
    if not source_type:
        return "PERSONAL_NOTE"
    st = str(source_type).strip().upper()
    if st in {"PDF", "EPUB", "PDF_CHUNK", "BOOK", "ARTICLE", "WEBSITE", "PERSONAL_NOTE", "HIGHLIGHT", "INSIGHT"}:
        return st
    if st in {"NOTE", "PERSONAL"}:
        return "PERSONAL_NOTE"
    if st in {"HIGHLIGHTS"}:
        return "HIGHLIGHT"
    if st in {"INSIGHTS"}:
        return "INSIGHT"
    # Unknown types default to PERSONAL_NOTE (safe semantic fallback)
    logger.warning(f"[WARN] Unknown source_type '{source_type}', defaulting to PERSONAL_NOTE")
    return "PERSONAL_NOTE"


def _mirror_book_registry_rows(
    cursor,
    *,
    book_id: str,
    title: str,
    author: str,
    firebase_uid: str,
) -> None:
    """
    Best-effort registry mirroring for Phase 1C routing prep.

    Writes to the new canonical table (TOMEHUB_LIBRARY_ITEMS) additively while
    preserving legacy mirror behavior in TOMEHUB_BOOKS.
    Any failure is logged as non-critical to avoid breaking ingestion.
    """
    if not book_id or not firebase_uid:
        return

    # 1) New canonical master (additive; Phase 1A may not exist in all envs yet)
    try:
        cursor.execute(
            """
            MERGE INTO TOMEHUB_LIBRARY_ITEMS li
            USING (
                SELECT
                    :p_item_id AS item_id,
                    :p_uid AS firebase_uid,
                    :p_title AS title,
                    :p_author AS author
                FROM DUAL
            ) src
            ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
            WHEN NOT MATCHED THEN
                INSERT (
                    ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, CREATED_AT, UPDATED_AT
                )
                VALUES (
                    src.item_id, src.firebase_uid, 'BOOK', src.title, src.author, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            WHEN MATCHED THEN
                UPDATE SET
                    TITLE = COALESCE(src.title, li.TITLE),
                    AUTHOR = COALESCE(src.author, li.AUTHOR),
                    UPDATED_AT = CURRENT_TIMESTAMP
            """,
            {
                "p_item_id": book_id,
                "p_uid": firebase_uid,
                "p_title": title,
                "p_author": author,
            },
        )
        logger.info(f"Mirrored book '{title}' to TOMEHUB_LIBRARY_ITEMS")
    except Exception as e:
        logger.warning(f"Mirroring to TOMEHUB_LIBRARY_ITEMS failed (Non-critical): {e}")


def normalize_highlight_type(highlight_type: Optional[str]) -> str:
    """
    Normalize highlight type to canonical DB values.
    Canonical set: HIGHLIGHT, INSIGHT
    """
    st = str(highlight_type or "highlight").strip().lower()
    if st in {"insight", "note"}:
        return "INSIGHT"
    return "HIGHLIGHT"


def _invalidate_search_cache(firebase_uid: str, book_id: Optional[str] = None) -> None:
    """
    Best-effort cache invalidation for user/book search results.
    """
    if not firebase_uid:
        return

    try:
        from services.cache_service import get_cache

        cache = get_cache()
        if not cache:
            return

        user_pattern = f"search:*:{firebase_uid}:*"
        cache.delete_pattern(user_pattern)
        logger.info(f"Cache invalidated for user {firebase_uid} (pattern: {user_pattern})")

        if book_id:
            book_pattern = f"search:*:*:{book_id}:*"
            cache.delete_pattern(book_pattern)
            logger.info(f"Cache invalidated for book {book_id} (pattern: {book_pattern})")
    except Exception as e:
        logger.warning(f"Cache invalidation failed (non-critical): {e}")


def _emit_change_event_best_effort(
    *,
    firebase_uid: str,
    item_id: Optional[str],
    entity_type: str,
    event_type: str,
    payload: Optional[dict] = None,
) -> None:
    if not firebase_uid:
        return
    try:
        from services.change_event_service import emit_change_event

        emit_change_event(
            firebase_uid=firebase_uid,
            item_id=item_id,
            entity_type=entity_type,
            event_type=event_type,
            payload=payload or {},
            source_service="ingestion_service",
        )
    except Exception as e:
        logger.debug(f"[DEBUG] change event emit skipped: {e}")


def check_book_exists(title: str, author: str, firebase_uid: str, conn=None) -> bool:
    """
    Check if a book with the same title and author already exists for the user.
    """
    should_close = False
    try:
        if conn is None:
            conn = DatabaseManager.get_write_connection()
            should_close = True
            
        # If we created the connection, we own the cursor cycle. 
        # If conn passed in, we should create a cursor but NOT close the conn.
        # However, to be safe/clean, let's use a with block for cursor only.
        
        with conn.cursor() as cursor:
            # Search for any chunk matching user, title, and author
            # Note: Title in DB is often formatted as "Title - Author" in ingest_book
            db_title = f"{title} - {author}"
            
            query = """
            SELECT COUNT(*) 
            FROM TOMEHUB_CONTENT_V2 
            WHERE firebase_uid = :p_uid 
                AND title = :p_title
            """
            
            cursor.execute(query, {"p_uid": firebase_uid, "p_title": db_title})
            count = cursor.fetchone()[0]
            return count > 0

    except Exception as e:
        logger.error(f"Error checking book existence: {e}")
        return False
    finally:
        # Only close if we opened it (Legacy support)
        # Note: DatabaseManager.get_write_connection() usually returns a pooled conn 
        # that needs .close() to return to pool.
        if should_close and conn:
            conn.close()


def delete_book_content(title: str, author: str, firebase_uid: str, conn=None) -> bool:
    """
    Delete all chunks for a specific book/user to allow re-ingestion.
    """
    should_close = False
    try:
        if conn is None:
            conn = DatabaseManager.get_write_connection()
            should_close = True
            
        with conn.cursor() as cursor:
            db_title = f"{title} - {author}"
            
            query = """
            DELETE FROM TOMEHUB_CONTENT_V2 
            WHERE firebase_uid = :p_uid 
                AND title = :p_title
            """
            cursor.execute(query, {"p_uid": firebase_uid, "p_title": db_title})
            deleted_count = cursor.rowcount
            
            # verify_leak refactor used 'transaction' block in caller usually, but here...
            # If we passed local conn, we commit. If external, we let caller commit?
            # It's safer to commit here if we own the transaction logic for this step, 
            # BUT for atomic race fix, we want CALLER to commit.
            
            if should_close:
                 conn.commit() 
            # If shared conn, DO NOT commit yet, let caller do it.
            
            logger.info(f"Deleted {deleted_count} existing chunks for '{title}' to allow overwrite.")
            return True

    except Exception as e:
        logger.error(f"Error deleting book content: {e}")
        return False
    finally:
        if should_close and conn:
            conn.close()


def _is_missing_table_error(error: Exception) -> bool:
    if not isinstance(error, oracledb.DatabaseError):
        return False
    try:
        return getattr(error.args[0], "code", None) == 942
    except Exception:
        return False


def _is_invalid_identifier_error(error: Exception) -> bool:
    if not isinstance(error, oracledb.DatabaseError):
        return False
    try:
        return getattr(error.args[0], "code", None) == 904
    except Exception:
        return False


def _table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = :p_table
        """,
        {"p_table": str(table_name or "").upper()},
    )
    return {str(r[0]).upper() for r in cursor.fetchall()}


def _chunked(seq, size: int):
    chunk = []
    for item in seq:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def purge_item_content(firebase_uid: str, book_id: str) -> dict:
    """
    Hard-delete all DB rows linked to a specific user item id.
    """
    deleted = 0
    aux_deleted = {
        "ingested_files": 0,
        "file_reports": 0,
        "external_meta": 0,
        "external_edges": 0,
        "library_items": 0,
        "index_state": 0,
        "book_epistemic_metrics": 0,
    }

    if not firebase_uid:
        return {"success": False, "deleted": 0, "error": "firebase_uid required"}
    if not book_id:
        return {"success": False, "deleted": 0, "error": "book_id required"}

    binds = {"p_uid": firebase_uid, "p_book": book_id}

    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Schema-aware content table resolution (V2 vs legacy, book_id vs item_id drift).
                content_table = None
                content_cols = set()
                for candidate in ("TOMEHUB_CONTENT_V2", "TOMEHUB_CONTENT"):
                    cols = _table_columns(cursor, candidate)
                    if cols:
                        content_table = candidate
                        content_cols = cols
                        break

                content_item_col = None
                content_id_col = "ID" if "ID" in content_cols else None
                for c in ("ITEM_ID", "BOOK_ID"):
                    if c in content_cols:
                        content_item_col = c
                        break

                content_ids: list[int] = []
                if content_table and content_item_col:
                    try:
                        if content_id_col:
                            cursor.execute(
                                f"""
                                SELECT {content_id_col}
                                FROM {content_table}
                                WHERE FIREBASE_UID = :p_uid
                                  AND {content_item_col} = :p_book
                                """,
                                binds,
                            )
                            for row in cursor.fetchall():
                                try:
                                    if row and row[0] is not None:
                                        content_ids.append(int(row[0]))
                                except Exception:
                                    continue
                    except Exception as q_err:
                        if not (_is_missing_table_error(q_err) or _is_invalid_identifier_error(q_err)):
                            raise

                    # Child-first delete for content-linked tables (best-effort, schema-aware).
                    if content_ids:
                        child_specs = [
                            ("TOMEHUB_CONTENT_TAGS", ("CONTENT_ID", "CHUNK_ID")),
                            ("TOMEHUB_CONTENT_CATEGORIES", ("CONTENT_ID", "CHUNK_ID")),
                            ("TOMEHUB_FLOW_SEEN", ("CHUNK_ID", "CONTENT_ID")),
                            ("TOMEHUB_CONCEPT_CHUNKS", ("CONTENT_ID", "CHUNK_ID")),
                        ]
                        for child_table, col_candidates in child_specs:
                            try:
                                child_cols = _table_columns(cursor, child_table)
                                if not child_cols:
                                    continue
                                child_col = next((c for c in col_candidates if c in child_cols), None)
                                if not child_col:
                                    continue
                                for batch in _chunked(content_ids, 500):
                                    local_binds = {}
                                    phs = []
                                    for i, cid in enumerate(batch):
                                        k = f"p_c{i}"
                                        phs.append(f":{k}")
                                        local_binds[k] = cid
                                    cursor.execute(
                                        f"DELETE FROM {child_table} WHERE {child_col} IN ({', '.join(phs)})",
                                        local_binds,
                                    )
                            except Exception as child_err:
                                if _is_missing_table_error(child_err) or _is_invalid_identifier_error(child_err):
                                    logger.debug(f"[DEBUG] purge_item_content skipped child cleanup for {child_table}: {child_err}")
                                    continue
                                raise

                    cursor.execute(
                        f"""
                        DELETE FROM {content_table}
                        WHERE FIREBASE_UID = :p_uid
                          AND {content_item_col} = :p_book
                        """,
                        binds,
                    )
                    deleted = cursor.rowcount or 0
                else:
                    logger.warning("[WARN] purge_item_content could not resolve active content table/item key column")

                aux_specs = (
                    ("index_state", "TOMEHUB_ITEM_INDEX_STATE", ("ITEM_ID", "BOOK_ID")),
                    ("ingested_files", "TOMEHUB_INGESTED_FILES", ("BOOK_ID", "ITEM_ID")),
                    ("file_reports", "TOMEHUB_FILE_REPORTS", ("BOOK_ID", "ITEM_ID")),
                    ("external_meta", "TOMEHUB_EXTERNAL_BOOK_META", ("BOOK_ID", "ITEM_ID")),
                    ("external_edges", "TOMEHUB_EXTERNAL_EDGES", ("BOOK_ID", "ITEM_ID")),
                    ("book_epistemic_metrics", "TOMEHUB_BOOK_EPISTEMIC_METRICS", ("BOOK_ID", "ITEM_ID")),
                    ("library_items", "TOMEHUB_LIBRARY_ITEMS", ("ITEM_ID", "BOOK_ID")),
                )
                for key, table_name, id_col_candidates in aux_specs:
                    try:
                        aux_cols = _table_columns(cursor, table_name)
                        if not aux_cols:
                            continue
                        id_col = next((c for c in id_col_candidates if c in aux_cols), None)
                        if not id_col:
                            logger.debug(f"[DEBUG] purge_item_content skipped {table_name}: no id column among {id_col_candidates}")
                            continue
                        cursor.execute(
                            f"""
                            DELETE FROM {table_name}
                            WHERE FIREBASE_UID = :p_uid
                              AND {id_col} = :p_book
                            """,
                            binds,
                        )
                        aux_deleted[key] = cursor.rowcount or 0
                    except Exception as aux_error:
                        if _is_missing_table_error(aux_error) or _is_invalid_identifier_error(aux_error):
                            logger.debug(f"[DEBUG] purge_item_content skipped schema-mismatch table for {key}")
                            continue
                        raise

            connection.commit()

        _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
        delete_epistemic_distribution(book_id=book_id, firebase_uid=firebase_uid)
        _emit_change_event_best_effort(
            firebase_uid=firebase_uid,
            item_id=book_id,
            entity_type="CONTENT",
            event_type="item.purged",
            payload={"deleted": deleted, "aux_deleted": aux_deleted},
        )
        return {"success": True, "deleted": deleted, "aux_deleted": aux_deleted}
    except Exception as e:
        logger.error(f"[ERROR] purge_item_content failed: {e}")
        return {"success": False, "deleted": deleted, "aux_deleted": aux_deleted, "error": str(e)}


def ingest_book(file_path: str, title: str, author: str, firebase_uid: str, book_id: str = None, categories: Optional[str] = None) -> bool:
    # Normalize categories: remove newlines and extra spaces
    if categories:
        categories = ",".join([c.strip() for c in categories.replace("\n", ",").split(",") if c.strip()])
    prepared_categories = prepare_labels(categories) if categories else []
    # DEBUG: Verify file exists at start
    _runtime_log(f"[DEBUG] File exists at start: {os.path.exists(file_path)}")
    
    start_time = time.time()
    source_type = "PDF" if file_path.lower().endswith(".pdf") else "EPUB"
    
    # Step 0: Duplicate Check / Overwrite
    # Step 0: Optimistic Duplicate Check (Fast fail, but not atomic)
    # If it exists, we warn/plan to overwrite, but we don't delete yet to avoid deleting while another process is writing.
    # We will do the ACTUAL authoritative check-and-delete inside the transaction lock later.
    optimistic_exists = check_book_exists(title, author, firebase_uid)
    if optimistic_exists:
        logger.info(f"Book '{title}' by {author} exists (Optimistic check). Will overwrite atomically later.")
    
    if not book_id:
        book_id = str(uuid.uuid4())

    _runtime_log("=" * 70)
    _runtime_log("TomeHub Book Ingestion Pipeline")
    _runtime_log("=" * 70)
    _runtime_log(f"\n[INFO] Book: {title}")
    _runtime_log(f"[INFO] Author: {author}")
    _runtime_log(f"[INFO] File: {file_path}")
    _runtime_log(f"[INFO] Book ID: {book_id}")
    
    # Step 1: Extract Content
    _runtime_log(f"\n{'='*70}")
    _runtime_log("Step 1: Extracting Content")
    _runtime_log(f"{'='*70}")
    
    file_ext = os.path.splitext(file_path)[1].lower()
    chunks = []
    
    if file_ext == '.pdf':
        chunks = extract_pdf_content(file_path)
    elif file_ext == '.epub':
        chunks = extract_epub_content(file_path)
    else:
        logger.error("Unsupported file type", extra={"file": file_path, "ext": file_ext})
        return False
    
    if not chunks:
        logger.error("Failed to extract content (chunks is empty or None)", extra={"file": file_path})
        return False
    
    logger.info("Content extraction successful", extra={"chunk_count": len(chunks), "file": file_path})
    
    # Step 2: Connect to database & ATOMIC TRANSACTION START
    _runtime_log(f"\n{'='*70}")
    _runtime_log("Step 2 & 3: Atomic Database Transaction (Locking -> Processing -> Ingestion)")
    _runtime_log(f"{'='*70}")
    
    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Phase 1C routing prep: mirror to new canonical registry additively while
                # preserving legacy TOMEHUB_BOOKS behavior.
                _mirror_book_registry_rows(
                    cursor,
                    book_id=book_id,
                    title=title,
                    author=author,
                    firebase_uid=firebase_uid,
                )

                # A. ACQUIRE LOCK (The critical section starts here)
                # Task 6.1: Deterministic Lock Name
                # Normalize title/author to ensure "Book A" and "book a" map to the same lock
                # We use simple lower()+strip() to be safe but permissive.
                norm_title = title.lower().strip()
                norm_author = author.lower().strip()
                
                import hashlib
                safe_key = hashlib.md5(f"{norm_title}_{norm_author}".encode('utf-8')).hexdigest()
                lock_name = f"ingest_{firebase_uid}_{safe_key}"
                
                logger.info("Acquiring ingestion lock...", extra={"lock": lock_name})
                acquire_lock(cursor, lock_name, timeout=30)
                
                # B. AUTHORITATIVE CHECK & DELETE
                # Now that we have the lock, no one else is writing this book for this user.
                if check_book_exists(title, author, firebase_uid, conn=connection):
                    logger.info("Authoritative check found existing book. Deleting under lock.")
                    delete_book_content(title, author, firebase_uid, conn=connection)

                # C. PROCESS & INSERT
                logger.info("Connected to database & Locked.")
            
                # Step 3: Process chunks in batches
                _runtime_log(f"\n{'='*70}")
                _runtime_log("Step 3: Processing Chunks (Parallel NLP + Batch Embeddings)")
                _runtime_log(f"{'='*70}")
                
                insert_sql = """
                INSERT INTO TOMEHUB_CONTENT_V2 
                (firebase_uid, content_type, title, content_chunk, page_number, chunk_index, vec_embedding, item_id, normalized_content, text_deaccented, lemma_tokens, token_freq, categories)
                VALUES (:p_uid, :p_type, :p_title, :p_content, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm_content, :p_deaccent, :p_lemmas, :p_token_freq, :p_cats)
                RETURNING id INTO :p_out_id
                """
                
                successful_inserts = 0
                failed_embeddings = 0
                
                BATCH_SIZE = 50
                data_cleaner_lock = threading.Lock()
                data_cleaner_cache: dict[str, str] = {}
                data_cleaner_budget = {
                    "ai_enabled": bool(getattr(settings, "INGESTION_DATA_CLEANER_AI_ENABLED", True)),
                    "noise_threshold": int(getattr(settings, "INGESTION_DATA_CLEANER_NOISE_THRESHOLD", 4) or 4),
                    "max_calls_per_book": int(getattr(settings, "INGESTION_DATA_CLEANER_MAX_CALLS_PER_BOOK", 40) or 40),
                    "min_chars_for_ai": int(getattr(settings, "INGESTION_DATA_CLEANER_MIN_CHARS_FOR_AI", 180) or 180),
                    "cache_size": int(getattr(settings, "INGESTION_DATA_CLEANER_CACHE_SIZE", 256) or 0),
                    "ai_calls_used": 0,
                    "ai_calls_applied": 0,
                    "cache_hits": 0,
                    "skip_low_noise": 0,
                    "skip_budget": 0,
                    "skip_disabled": 0,
                    "skip_too_short": 0,
                }

                def _data_cleaner_cache_key(text: str) -> str:
                    payload = (text or "").encode("utf-8", errors="ignore")
                    return hashlib.sha1(payload).hexdigest()
                
                def process_single_chunk_nlp(idx_chunk_tuple):
                    idx, chunk = idx_chunk_tuple
                    chunk_text = chunk['text']
                    skip_chunk = False
                    
                    # Phase 14: SIS Integration (Smart Chunking Quality Gate)
                    sis = chunk.get('sis', {})
                    if sis:
                        score = sis.get('score', 0)
                        decision = sis.get('decision', 'EMBED')
                        
                        if decision == 'QUARANTINE':
                            logger.warning("Chunk Quarantined due to low SIS", extra={
                                "sis_score": score,
                                "decision": decision,
                                "details": sis.get('details'),
                                "page": chunk.get('page_num')
                            })
                            skip_chunk = True
                    
                    # Phase 13 Optimization: LINGUISTIC FILTER (Non-AI Repair)
                    # We apply deterministic regex and dictionary rules using ftfy + symspell
                    # This replaces the slow AI method and prevents memory crashes.
                    # Force Repair via Linguistic Correction Service
                    repaired_text = corrector_service.fix_text(chunk_text)
                    repaired = False
                    
                    if repaired_text != chunk_text:
                        chunk_text = repaired_text
                        repaired = True
                        # Log simple confirmation
                        logger.info("Linguistic Filter applied (Regex/Dict)", extra={"chunk_index": idx})
                    
                    # Rule-first cleaning (cheap, always-on)
                    rule_cleaned_text = DataCleanerService.strip_basic_patterns(chunk_text)
                    use_ai_cleaner = False
                    ai_cleaner_reason = "low_noise"
                    ai_cleaner_cache_hit = False
                    ai_noise_assessment = DataCleanerService.assess_noise(rule_cleaned_text, title=title, author=author)
                    ai_noise_score = int(ai_noise_assessment.get("score", 0))
                    try:
                        DATA_CLEANER_NOISE_SCORE.observe(ai_noise_score)
                    except Exception:
                        pass

                    decluttered_text = rule_cleaned_text

                    if not data_cleaner_budget["ai_enabled"]:
                        ai_cleaner_reason = "disabled"
                        with data_cleaner_lock:
                            data_cleaner_budget["skip_disabled"] += 1
                        try:
                            DATA_CLEANER_AI_SKIPPED_TOTAL.labels(reason="disabled").inc()
                        except Exception:
                            pass
                    elif len(rule_cleaned_text) < int(data_cleaner_budget["min_chars_for_ai"]):
                        ai_cleaner_reason = "too_short"
                        with data_cleaner_lock:
                            data_cleaner_budget["skip_too_short"] += 1
                        try:
                            DATA_CLEANER_AI_SKIPPED_TOTAL.labels(reason="too_short").inc()
                        except Exception:
                            pass
                    elif ai_noise_score < int(data_cleaner_budget["noise_threshold"]):
                        ai_cleaner_reason = "low_noise"
                        with data_cleaner_lock:
                            data_cleaner_budget["skip_low_noise"] += 1
                        try:
                            DATA_CLEANER_AI_SKIPPED_TOTAL.labels(reason="low_noise").inc()
                        except Exception:
                            pass
                    else:
                        cache_key = _data_cleaner_cache_key(rule_cleaned_text)
                        reserved_slot = False
                        cached_value = None
                        with data_cleaner_lock:
                            if cache_key in data_cleaner_cache:
                                cached_value = data_cleaner_cache.get(cache_key)
                                data_cleaner_budget["cache_hits"] += 1
                            elif data_cleaner_budget["ai_calls_used"] < int(data_cleaner_budget["max_calls_per_book"]):
                                data_cleaner_budget["ai_calls_used"] += 1
                                reserved_slot = True
                            else:
                                data_cleaner_budget["skip_budget"] += 1

                        if cached_value is not None:
                            decluttered_text = cached_value or rule_cleaned_text
                            ai_cleaner_cache_hit = True
                            ai_cleaner_reason = "cache_hit"
                            try:
                                DATA_CLEANER_AI_SKIPPED_TOTAL.labels(reason="cache_hit").inc()
                            except Exception:
                                pass
                        elif reserved_slot:
                            use_ai_cleaner = True
                            ai_cleaner_reason = "applied"
                            decluttered_text = DataCleanerService.clean_with_ai(
                                rule_cleaned_text,
                                title=title,
                                author=author,
                            )
                            with data_cleaner_lock:
                                data_cleaner_budget["ai_calls_applied"] += 1
                                cache_size = int(data_cleaner_budget["cache_size"])
                                if cache_size > 0:
                                    if len(data_cleaner_cache) >= cache_size:
                                        # FIFO-ish eviction (dict preserves insertion order on modern Python)
                                        try:
                                            oldest_key = next(iter(data_cleaner_cache))
                                            data_cleaner_cache.pop(oldest_key, None)
                                        except Exception:
                                            data_cleaner_cache.clear()
                                    data_cleaner_cache[cache_key] = decluttered_text
                            try:
                                DATA_CLEANER_AI_APPLIED_TOTAL.inc()
                            except Exception:
                                pass
                        else:
                            ai_cleaner_reason = "budget_exhausted"
                            try:
                                DATA_CLEANER_AI_SKIPPED_TOTAL.labels(reason="budget_exhausted").inc()
                            except Exception:
                                pass

                    return {
                        'index': idx,
                        'chunk': chunk,
                        'text_used': chunk_text, # The (potentially repaired) text
                        'repaired': repaired,
                        'normalized': normalize_text(chunk_text),
                        'deaccented': deaccent_text(chunk_text),
                        'lemmas': json.dumps(get_lemmas(chunk_text), ensure_ascii=False),
                        'lemma_freqs': json.dumps(get_lemma_frequencies(decluttered_text), ensure_ascii=False),
                        'classification': classify_passage_fast(chunk_text),
                        'decluttered_text': decluttered_text,
                        'skip': skip_chunk,
                        'data_cleaner_ai_used': use_ai_cleaner,
                        'data_cleaner_ai_reason': ai_cleaner_reason,
                        'data_cleaner_cache_hit': ai_cleaner_cache_hit,
                        'data_cleaner_noise_score': ai_noise_score,
                        'data_cleaner_noise_signals': ai_noise_assessment.get("signals", {}),
                    }

                # Filter out empty/short chunks before processing
                valid_chunks = [(i, c) for i, c in enumerate(chunks) if DataHealthService.validate_content(c.get('text'))]
                
                if not valid_chunks:
                    logger.warning(f"No valid chunks found (length >= 10) out of {len(chunks)} extracted chunks.")
                    return False

                for i in range(0, len(valid_chunks), BATCH_SIZE):
                    batch = valid_chunks[i:i+BATCH_SIZE]
                    
                    # 1. Parallel NLP processing for the batch
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        nlp_results = list(executor.map(process_single_chunk_nlp, batch))
                    
                    # Filter out skipped (Quarantined) chunks
                    valid_nlp_results = [r for r in nlp_results if not r.get('skip')]
                    
                    if not valid_nlp_results:
                        continue
                        
                    # 2. Batch Embedding generation (Using Repaired Text)
                    batch_texts = [r['text_used'] for r in valid_nlp_results]
                    embeddings = batch_get_embeddings(batch_texts)
                    
                    # 3. Database Insertion (Batch)
                    for idx, res in enumerate(valid_nlp_results):
                        chunk = res['chunk']
                        embedding = embeddings[idx]
                        
                        if embedding is None:
                            failed_embeddings += 1
                            continue
                            
                        try:
                            out_id = cursor.var(oracledb.NUMBER)
                            cursor.execute(insert_sql, {
                                "p_uid": firebase_uid,
                                "p_type": "PDF" if file_ext == '.pdf' else "EPUB",
                                "p_title": f"{title} - {author}",
                                "p_content": res['decluttered_text'],
                                "p_page": chunk.get('page_num', 0),
                                "p_chunk_idx": res['index'],
                                "p_vec": embedding,
                                "p_book_id": book_id,
                                "p_norm_content": res['normalized'],
                                "p_deaccent": res['deaccented'],
                                "p_lemmas": res['lemmas'],
                                "p_token_freq": res['lemma_freqs'],
                                "p_cats": categories,
                                "p_out_id": out_id
                            })
                            new_id = out_id.getvalue()
                            if isinstance(new_id, list):
                                new_id = new_id[0] if new_id else None
                            if new_id is not None:
                                _insert_content_categories(cursor, int(new_id), prepared_categories)
                            successful_inserts += 1
                        except Exception as e:
                            _runtime_log(f"[FAILED] Chunk {res['index']} DB insert: {e}")
                    
                    _runtime_log(f"[PROGRESS] Processed {min(i + BATCH_SIZE, len(valid_chunks))}/{len(valid_chunks)} chunks...")

                try:
                    logger.info(
                        "Data cleaner ingestion summary",
                        extra={
                            "title": title,
                            "author": author,
                            "valid_chunk_count": len(valid_chunks),
                            "ai_enabled": data_cleaner_budget["ai_enabled"],
                            "noise_threshold": data_cleaner_budget["noise_threshold"],
                            "max_calls_per_book": data_cleaner_budget["max_calls_per_book"],
                            "ai_calls_used": data_cleaner_budget["ai_calls_used"],
                            "ai_calls_applied": data_cleaner_budget["ai_calls_applied"],
                            "cache_hits": data_cleaner_budget["cache_hits"],
                            "skip_low_noise": data_cleaner_budget["skip_low_noise"],
                            "skip_budget": data_cleaner_budget["skip_budget"],
                            "skip_disabled": data_cleaner_budget["skip_disabled"],
                            "skip_too_short": data_cleaner_budget["skip_too_short"],
                        },
                    )
                except Exception:
                    pass
                
                # Step 4: Commit (Releases Lock)
                # Fail Loud Check: Abort if "Swiss Cheese" (Too many missing embeddings)
                total_processed = successful_inserts + failed_embeddings
                if total_processed > 0:
                    failure_rate = failed_embeddings / total_processed
                    if failure_rate > 0.10: # >10% failure
                        error_msg = f"Ingestion Aborted: High embedding failure rate ({failure_rate:.1%}). threshold=10%"
                        logger.error(error_msg, extra={"failed": failed_embeddings, "total": total_processed})
                        connection.rollback()
                        raise Exception(error_msg)

                _runtime_log(f"\n{'='*70}")
                _runtime_log("Step 4: Committing to Database (Releases Lock)")
                _runtime_log(f"{'='*70}")
                
                connection.commit()
                logger.info("Ingestion complete (Lock Released)", extra={
                    "successful_inserts": successful_inserts,
                    "failed_embeddings": failed_embeddings,
                    "book_id": book_id
                })

    except Exception as e:
        logger.error("Database operation failed", extra={"error": str(e)})
        # Context manager handles closing, no explicit rollback needed if we assume pool cleans up, 
        # avoiding manually accessing 'connection' here since it might not be bound if get_connection fails
        return False
    
    # Step 5: Cleanup
    _runtime_log(f"\n{'='*70}")
    _runtime_log("Step 5: Cleaning Up File")
    _runtime_log(f"{'='*70}")
    
    try:
        if successful_inserts > 0:
            if os.path.exists(file_path):
                os.remove(file_path)
                _runtime_log(f"[SUCCESS] Ingestion successful. Deleted temp file: {file_path}")
            else:
                _runtime_log("[WARNING] File not found for deletion.")
        else:
             logger.warning(f"Ingestion incomplete (0 inserts). Preserving file for inspection: {file_path}")
             _runtime_log(f"[WARNING] File preserved: {file_path}")
             
    except Exception as e:
        _runtime_log(f"[ERROR] Failed to delete file: {e}")
    
    if successful_inserts == 0:
        INGESTION_LATENCY.labels(status="fail", source_type=source_type).observe(time.time() - start_time)
        logger.error(f"Ingestion failed: 0 chunks were successfully inserted (valid_chunks: {len(valid_chunks)})")
        return False
    
    INGESTION_LATENCY.labels(status="success", source_type=source_type).observe(time.time() - start_time)
    _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
    maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="ingest_book")
    _emit_change_event_best_effort(
        firebase_uid=firebase_uid,
        item_id=book_id,
        entity_type="BOOK",
        event_type="book.ingested",
        payload={
            "title": title,
            "author": author,
            "source_type": source_type,
            "chunks_inserted": successful_inserts,
            "data_cleaner": {
                "ai_calls_used": data_cleaner_budget.get("ai_calls_used", 0) if 'data_cleaner_budget' in locals() else 0,
                "ai_calls_applied": data_cleaner_budget.get("ai_calls_applied", 0) if 'data_cleaner_budget' in locals() else 0,
                "cache_hits": data_cleaner_budget.get("cache_hits", 0) if 'data_cleaner_budget' in locals() else 0,
                "skip_low_noise": data_cleaner_budget.get("skip_low_noise", 0) if 'data_cleaner_budget' in locals() else 0,
                "skip_budget": data_cleaner_budget.get("skip_budget", 0) if 'data_cleaner_budget' in locals() else 0,
            },
        },
    )

    return True
def ingest_text_item(
    text: str,
    title: str,
    author: str,
    firebase_uid: str,
    source_type: str = "PERSONAL_NOTE",
    categories: Optional[str] = None,
    book_id: Optional[str] = None,
    page_number: Optional[int] = None,
    chunk_type: Optional[str] = None,
    chunk_index: Optional[int] = None,
    comment: Optional[str] = None,
    tags: Optional[list] = None,
) -> bool:
    # Normalize categories
    if categories:
        categories = ",".join([c.strip() for c in categories.replace("\n", ",").split(",") if c.strip()])
    prepared_categories = prepare_labels(categories) if categories else []
    _runtime_log(f"\n[INFO] Text Ingestion: {title}")
    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Gatekeeper: Validation
                if not DataHealthService.validate_content(text):
                    _runtime_log(f"[SKIPPED] Content too short or empty: {title}")
                    return False

                # NLP Processing
                normalized_text = normalize_text(text)
                deaccented_text = deaccent_text(text)
                lemmas_json = json.dumps(get_lemmas(text), ensure_ascii=False)
                
                embedding = get_embedding(text)
                if embedding:
                    # Generate a book_id if one doesn't exist contextually
                    if not book_id:
                        book_id = str(uuid.uuid4())

                    db_source_type = normalize_source_type(source_type)
                    tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                    prepared_tags = prepare_labels(tags_json) if tags_json else []

                    out_id = cursor.var(oracledb.NUMBER)
                    cursor.execute("""
                        INSERT INTO TOMEHUB_CONTENT_V2 
                        (firebase_uid, content_type, title, content_chunk, page_number, chunk_index, vec_embedding, item_id, normalized_content, text_deaccented, lemma_tokens, categories, comment_text, tags_json)
                        VALUES (:p_uid, :p_type, :p_title, :p_content, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_cats, :p_comment, :p_tags)
                        RETURNING id INTO :p_out_id
                    """, {
                        "p_uid": firebase_uid,
                        "p_type": db_source_type,
                        "p_title": f"{title} - {author}",
                        "p_content": text,
                        "p_page": page_number or 1,
                        "p_chunk_idx": chunk_index or 0,
                        "p_vec": embedding,
                        "p_book_id": book_id,
                        "p_norm": normalized_text,
                        "p_deaccent": deaccented_text,
                        "p_lemmas": lemmas_json,
                        "p_cats": categories,
                        "p_comment": comment,
                        "p_tags": tags_json,
                        "p_out_id": out_id
                    })
                    new_id = out_id.getvalue()
                    if isinstance(new_id, list):
                        new_id = new_id[0] if new_id else None
                    if new_id is not None:
                        _insert_content_categories(cursor, int(new_id), prepared_categories)
                        _insert_content_tags(cursor, int(new_id), prepared_tags)
                    connection.commit()
                    _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                    maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="ingest_text_item")
                    _emit_change_event_best_effort(
                        firebase_uid=firebase_uid,
                        item_id=book_id,
                        entity_type=db_source_type,
                        event_type="item.updated",
                        payload={"source_type": db_source_type, "title": title},
                    )
                    _runtime_log(f"[SUCCESS] Text Item Ingested: {title} (Type: {db_source_type})")
                    return True
                
                _runtime_log(f"[ERROR] Embedding was None for: {title}")
                return False
                
    except Exception as e:
        _runtime_log(f"Error: {e}")
        return False

def sync_highlights_for_item(
    firebase_uid: str,
    book_id: str,
    title: str,
    author: str,
    highlights: list
) -> dict:
    """
    Replace all highlights/insights for a given book_id with the provided list.
    """
    deleted = 0
    inserted = 0

    if not book_id:
        return {"success": False, "deleted": 0, "inserted": 0, "error": "book_id required"}

    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Delete existing highlight/insight rows for this book/user
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_CONTENT_V2
                    WHERE firebase_uid = :p_uid
                      AND item_id = :p_book
                      AND content_type IN ('HIGHLIGHT', 'INSIGHT')
                    """,
                    {"p_uid": firebase_uid, "p_book": book_id},
                )
                deleted = cursor.rowcount or 0

                if not highlights:
                    connection.commit()
                    _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                    maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="sync_highlights_empty")
                    _emit_change_event_best_effort(
                        firebase_uid=firebase_uid,
                        item_id=book_id,
                        entity_type="HIGHLIGHT",
                        event_type="highlight.synced",
                        payload={"deleted": deleted, "inserted": 0},
                    )
                    return {"success": True, "deleted": deleted, "inserted": 0}

                texts = [h.get("text", "") for h in highlights]
                embeddings = batch_get_embeddings(texts)

                insert_sql = """
                    INSERT INTO TOMEHUB_CONTENT_V2
                    (firebase_uid, content_type, title, content_chunk, page_number, chunk_index, vec_embedding, item_id, normalized_content, text_deaccented, lemma_tokens, comment_text, tags_json)
                    VALUES (:p_uid, :p_type, :p_title, :p_content, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_comment, :p_tags)
                    RETURNING id INTO :p_out_id
                """

                for idx, h in enumerate(highlights):
                    text = (h.get("text") or "").strip()
                    if not DataHealthService.validate_content(text):
                        continue

                    source_type = normalize_highlight_type(h.get("type", "highlight"))
                    chunk_type = "insight" if source_type == "INSIGHT" else "highlight"
                    comment = h.get("comment") if source_type == "HIGHLIGHT" else None
                    page_number = h.get("pageNumber")
                    tags = h.get("tags") or []
                    tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                    prepared_tags = prepare_labels(tags_json) if tags_json else []

                    embedding = embeddings[idx] if idx < len(embeddings) else None
                    if embedding is None:
                        continue

                    out_id = cursor.var(oracledb.NUMBER)
                    cursor.execute(
                        insert_sql,
                        {
                            "p_uid": firebase_uid,
                            "p_type": source_type,
                            "p_title": f"{title} - {author}",
                            "p_content": text,
                            "p_page": page_number,
                            "p_chunk_idx": idx,
                            "p_vec": embedding,
                            "p_book_id": book_id,
                            "p_norm": normalize_text(text),
                            "p_deaccent": deaccent_text(text),
                            "p_lemmas": json.dumps(get_lemmas(text), ensure_ascii=False),
                            "p_comment": comment,
                            "p_tags": tags_json,
                            "p_out_id": out_id,
                        },
                    )
                    new_id = out_id.getvalue()
                    if isinstance(new_id, list):
                        new_id = new_id[0] if new_id else None
                    if new_id is not None:
                        _insert_content_tags(cursor, int(new_id), prepared_tags)
                    inserted += 1

                connection.commit()
                _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="sync_highlights")
                _emit_change_event_best_effort(
                    firebase_uid=firebase_uid,
                    item_id=book_id,
                    entity_type="HIGHLIGHT",
                    event_type="highlight.synced",
                    payload={"deleted": deleted, "inserted": inserted},
                )
                return {"success": True, "deleted": deleted, "inserted": inserted}
    except Exception as e:
        logger.error(f"[ERROR] sync_highlights_for_item failed: {e}")
        return {"success": False, "deleted": deleted, "inserted": inserted, "error": str(e)}


def sync_personal_note_for_item(
    firebase_uid: str,
    book_id: str,
    title: str,
    author: str,
    content: Optional[str],
    tags: Optional[list],
    category: str = "PRIVATE",
    delete_only: bool = False,
) -> dict:
    """
    Keep Personal Note representation in Oracle AI store in sync with Firestore.
    - Always deletes existing PERSONAL_NOTE/INSIGHT rows for this note id
    - Re-inserts for all categories when delete_only is False
    - Keeps IDEAS as INSIGHT for backward-compatible retrieval; others use PERSONAL_NOTE
    """
    deleted = 0
    inserted = 0

    if not book_id:
        return {"success": False, "deleted": 0, "inserted": 0, "error": "book_id required"}

    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_CONTENT_V2
                    WHERE firebase_uid = :p_uid
                      AND item_id = :p_book
                      AND content_type IN ('PERSONAL_NOTE', 'INSIGHT')
                    """,
                    {"p_uid": firebase_uid, "p_book": book_id},
                )
                deleted = cursor.rowcount or 0

                normalized_category = str(category or "PRIVATE").strip().upper()
                if delete_only:
                    connection.commit()
                    _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                    maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="sync_personal_note_delete")
                    _emit_change_event_best_effort(
                        firebase_uid=firebase_uid,
                        item_id=book_id,
                        entity_type="PERSONAL_NOTE",
                        event_type="note.synced",
                        payload={"deleted": deleted, "inserted": 0, "delete_only": True, "category": normalized_category},
                    )
                    return {"success": True, "deleted": deleted, "inserted": 0}

                text = (content or "").strip()
                if not DataHealthService.validate_content(text):
                    connection.commit()
                    _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                    maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="sync_personal_note_invalid")
                    _emit_change_event_best_effort(
                        firebase_uid=firebase_uid,
                        item_id=book_id,
                        entity_type="PERSONAL_NOTE",
                        event_type="note.synced",
                        payload={"deleted": deleted, "inserted": 0, "invalid_content": True, "category": normalized_category},
                    )
                    return {"success": True, "deleted": deleted, "inserted": 0}

                embedding = get_embedding(text)
                if embedding is None:
                    return {"success": False, "deleted": deleted, "inserted": 0, "error": "embedding_failed"}

                tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                prepared_tags = prepare_labels(tags_json) if tags_json else []
                out_id = cursor.var(oracledb.NUMBER)

                db_source_type = "INSIGHT" if normalized_category == "IDEAS" else "PERSONAL_NOTE"
                chunk_type = f"personal_note_{normalized_category.lower()}"

                cursor.execute(
                    """
                    INSERT INTO TOMEHUB_CONTENT_V2
                    (firebase_uid, content_type, title, content_chunk, page_number, chunk_index, vec_embedding, item_id, normalized_content, text_deaccented, lemma_tokens, comment_text, tags_json)
                    VALUES (:p_uid, :p_type, :p_title, :p_content, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_comment, :p_tags)
                    RETURNING id INTO :p_out_id
                    """,
                    {
                        "p_uid": firebase_uid,
                        "p_type": db_source_type,
                        "p_title": f"{title} - {author}",
                        "p_content": text,
                        "p_page": 1,
                        "p_chunk_idx": 0,
                        "p_vec": embedding,
                        "p_book_id": book_id,
                        "p_norm": normalize_text(text),
                        "p_deaccent": deaccent_text(text),
                        "p_lemmas": json.dumps(get_lemmas(text), ensure_ascii=False),
                        "p_comment": None,
                        "p_tags": tags_json,
                        "p_out_id": out_id,
                    },
                )
                new_id = out_id.getvalue()
                if isinstance(new_id, list):
                    new_id = new_id[0] if new_id else None
                if new_id is not None:
                    _insert_content_tags(cursor, int(new_id), prepared_tags)
                inserted = 1
                connection.commit()
                _invalidate_search_cache(firebase_uid=firebase_uid, book_id=book_id)
                maybe_trigger_epistemic_distribution_refresh_async(book_id=book_id, firebase_uid=firebase_uid, reason="sync_personal_note")
                _emit_change_event_best_effort(
                    firebase_uid=firebase_uid,
                    item_id=book_id,
                    entity_type="PERSONAL_NOTE",
                    event_type="note.synced",
                    payload={"deleted": deleted, "inserted": inserted, "category": normalized_category},
                )
                return {"success": True, "deleted": deleted, "inserted": inserted}
    except Exception as e:
        logger.error(f"[ERROR] sync_personal_note_for_item failed: {e}")
        return {"success": False, "deleted": deleted, "inserted": inserted, "error": str(e)}

def process_bulk_items_logic(items: list, firebase_uid: str) -> dict:
    _runtime_log(f"Bulk processing {len(items)} items...")
    success = 0
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                import time
                for item in items:
                    try:
                        text = item.get('text', '')
                        if not DataHealthService.validate_content(text):
                            continue
                        
                        embedding = get_embedding(text)
                        if not embedding:
                            _runtime_log("[WARN] Embedding missing for item, skipping.")
                            continue

                        # NLP Processing
                        normalized_text = normalize_text(text)
                        deaccented_text = deaccent_text(text)
                        lemmas_json = json.dumps(get_lemmas(text), ensure_ascii=False)

                        # Normalize categories if present in item
                        cats = item.get('categories')
                        if cats:
                            cats = ",".join([c.strip() for c in cats.replace("\n", ",").split(",") if c.strip()])
                        prepared_categories = prepare_labels(cats) if cats else []

                        tags = item.get('tags')
                        tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                        prepared_tags = prepare_labels(tags_json) if tags_json else []

                        out_id = cursor.var(oracledb.NUMBER)
                        db_source_type = normalize_source_type(item.get('type', 'PERSONAL_NOTE'))
                        cursor.execute("""
                            INSERT INTO TOMEHUB_CONTENT_V2 
                            (firebase_uid, content_type, title, content_chunk, page_number, chunk_index, vec_embedding, item_id, normalized_content, text_deaccented, lemma_tokens, categories, comment_text, tags_json)
                            VALUES (:p_uid, :p_type, :p_title, :p_content, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_cats, :p_comment, :p_tags)
                            RETURNING id INTO :p_out_id
                        """, {
                            "p_uid": firebase_uid,
                            "p_type": db_source_type,
                            "p_title": f"{item.get('title')} - {item.get('author')}",
                            "p_content": text,
                            "p_page": item.get('page_number') or 1,
                            "p_chunk_idx": item.get('chunk_index') or 0,
                            "p_vec": embedding,
                            "p_book_id": item.get('book_id'),
                            "p_norm": normalized_text,
                            "p_deaccent": deaccented_text,
                            "p_lemmas": lemmas_json,
                            "p_cats": cats,
                            # Here item.get is used differently in old logic? No, just keys.
                            "p_comment": item.get('comment'), 
                            "p_tags": tags_json,
                            "p_out_id": out_id
                        })
                        new_id = out_id.getvalue()
                        if isinstance(new_id, list):
                            new_id = new_id[0] if new_id else None
                        if new_id is not None:
                            _insert_content_categories(cursor, int(new_id), prepared_categories)
                            _insert_content_tags(cursor, int(new_id), prepared_tags)
                        success += 1
                        time.sleep(0.2) # Rate limit
                    except Exception as e:
                        _runtime_log(f"Item failed: {e}")
                conn.commit()
    except Exception as e:
        _runtime_log(f"Bulk process error: {e}")
        
    return {"success": success}

if __name__ == "__main__":
    DatabaseManager.init_pool()
    if len(sys.argv) < 5:
        print("Usage: python ingestion_service.py <path> <title> <author> <uid> [book_id]")
        sys.exit(1)
    path = sys.argv[1]
    title = sys.argv[2]
    author = sys.argv[3]
    uid = sys.argv[4]
    book_id = sys.argv[5] if len(sys.argv) > 5 else None
    
    ingest_book(path, title, author, uid, book_id)
