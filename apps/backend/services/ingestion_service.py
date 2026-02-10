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

logger = get_logger("ingestion_service")
from services.monitoring import INGESTION_LATENCY
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
    if st in {"NOTES", "HIGHLIGHTS"}:
        return "HIGHLIGHT"
    if st in {"INSIGHTS"}:
        return "INSIGHT"
    # Unknown types default to PERSONAL_NOTE (safe semantic fallback)
    logger.warning(f"[WARN] Unknown source_type '{source_type}', defaulting to PERSONAL_NOTE")
    return "PERSONAL_NOTE"


def normalize_highlight_type(highlight_type: Optional[str]) -> str:
    """
    Normalize highlight type to canonical DB values.
    Canonical set: HIGHLIGHT, INSIGHT
    """
    st = str(highlight_type or "highlight").strip().lower()
    if st in {"insight", "note"}:
        return "INSIGHT"
    return "HIGHLIGHT"


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
            FROM TOMEHUB_CONTENT 
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
            DELETE FROM TOMEHUB_CONTENT 
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


def ingest_book(file_path: str, title: str, author: str, firebase_uid: str = "test_user_001", book_id: str = None, categories: Optional[str] = None) -> bool:
    # Normalize categories: remove newlines and extra spaces
    if categories:
        categories = ",".join([c.strip() for c in categories.replace("\n", ",").split(",") if c.strip()])
    prepared_categories = prepare_labels(categories) if categories else []
    # DEBUG: Verify file exists at start
    print(f"[DEBUG] File exists at start: {os.path.exists(file_path)}")
    
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

    print("=" * 70)
    print("TomeHub Book Ingestion Pipeline")
    print("=" * 70)
    print(f"\n[INFO] Book: {title}")
    print(f"[INFO] Author: {author}")
    print(f"[INFO] File: {file_path}")
    print(f"[INFO] Book ID: {book_id}")
    
    # Step 1: Extract Content
    print(f"\n{'='*70}")
    print("Step 1: Extracting Content")
    print(f"{'='*70}")
    
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
    print(f"\n{'='*70}")
    print("Step 2 & 3: Atomic Database Transaction (Locking -> Processing -> Ingestion)")
    print(f"{'='*70}")
    
    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Mirroring Logic: Ensure Book Exists in TOMEHUB_BOOKS
                try:
                   cursor.execute("""
                       MERGE INTO TOMEHUB_BOOKS b
                       USING (SELECT :p_id as id, :p_title as title, :p_author as author, :p_uid as uid FROM DUAL) src
                       ON (b.ID = src.id)
                       WHEN NOT MATCHED THEN
                           INSERT (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
                           VALUES (src.id, src.title, src.author, src.uid, CURRENT_TIMESTAMP)
                       WHEN MATCHED THEN
                           UPDATE SET LAST_UPDATED = CURRENT_TIMESTAMP
                   """, {
                       "p_id": book_id,
                       "p_title": title,
                       "p_author": author,
                       "p_uid": firebase_uid
                   })
                   # Note: We commit this via standard flow later, or implicit if successful
                   logger.info(f"Mirrored book '{title}' to TOMEHUB_BOOKS")
                except Exception as e:
                   # Mirroring is secondary, don't break ingestion if this fails but log strictly assuming constraints disabled
                   logger.warning(f"Mirroring to TOMEHUB_BOOKS failed (Non-critical): {e}")

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
                print(f"\n{'='*70}")
                print("Step 3: Processing Chunks (Parallel NLP + Batch Embeddings)")
                print(f"{'='*70}")
                
                insert_sql = """
                INSERT INTO TOMEHUB_CONTENT 
                (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, token_freq, categories)
                VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm_content, :p_deaccent, :p_lemmas, :p_token_freq, :p_cats)
                RETURNING id INTO :p_out_id
                """
                
                successful_inserts = 0
                failed_embeddings = 0
                
                BATCH_SIZE = 50
                
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
                    chunk_text_before = chunk_text
                    
                    # Force Repair via Linguistic Correction Service
                    repaired_text = corrector_service.fix_text(chunk_text)
                    repaired = False
                    
                    if repaired_text != chunk_text:
                        chunk_text = repaired_text
                        repaired = True
                        # Log simple confirmation
                        logger.info("Linguistic Filter applied (Regex/Dict)", extra={"chunk_index": idx})
                    
                    decluttered_text = DataCleanerService.clean_with_ai(chunk_text, title=title, author=author)
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
                        'skip': skip_chunk
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
                                "p_chunk_type": chunk.get('type', 'paragraph'),
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
                            print(f"[FAILED] Chunk {res['index']} DB insert: {e}")
                    
                    print(f"[PROGRESS] Processed {min(i + BATCH_SIZE, len(valid_chunks))}/{len(valid_chunks)} chunks...")
                
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

                print(f"\n{'='*70}")
                print("Step 4: Committing to Database (Releases Lock)")
                print(f"{'='*70}")
                
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
    print(f"\n{'='*70}")
    print("Step 5: Cleaning Up File")
    print(f"{'='*70}")
    
    try:
        if successful_inserts > 0:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[SUCCESS] Ingestion successful. Deleted temp file: {file_path}")
            else:
                print("[WARNING] File not found for deletion.")
        else:
             logger.warning(f"Ingestion incomplete (0 inserts). Preserving file for inspection: {file_path}")
             print(f"[WARNING] File preserved: {file_path}")
             
    except Exception as e:
        print(f"[ERROR] Failed to delete file: {e}")
    
    if successful_inserts == 0:
        INGESTION_LATENCY.labels(status="fail", source_type=source_type).observe(time.time() - start_time)
        logger.error(f"Ingestion failed: 0 chunks were successfully inserted (valid_chunks: {len(valid_chunks)})")
        return False
    
    INGESTION_LATENCY.labels(status="success", source_type=source_type).observe(time.time() - start_time)
    # Invalidate cache for this user (new content added)
    try:
        from services.cache_service import get_cache
        cache = get_cache()
        if cache:
            # Invalidate all search results for this user
            # Pattern: search:*:{firebase_uid}:*
            pattern = f"search:*:{firebase_uid}:*"
            cache.delete_pattern(pattern)
            logger.info(f"Cache invalidated for user {firebase_uid} (pattern: {pattern})")
            
            # Also invalidate book-specific caches if book_id is available
            if book_id:
                pattern = f"search:*:*:{book_id}:*"
                cache.delete_pattern(pattern)
                logger.info(f"Cache invalidated for book {book_id} (pattern: {pattern})")
    except Exception as e:
        logger.warning(f"Cache invalidation failed (non-critical): {e}")
        
    return True
def ingest_text_item(
    text: str,
    title: str,
    author: str,
    source_type: str = "PERSONAL_NOTE",
    firebase_uid: str = "test_user_001",
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
    print(f"\n[INFO] Text Ingestion: {title}")
    try:
        with DatabaseManager.get_write_connection() as connection:
            with connection.cursor() as cursor:
                # Gatekeeper: Validation
                if not DataHealthService.validate_content(text):
                    print(f"[SKIPPED] Content too short or empty: {title}")
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
                        INSERT INTO TOMEHUB_CONTENT 
                        (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, categories, "COMMENT", tags)
                        VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_cats, :p_comment, :p_tags)
                        RETURNING id INTO :p_out_id
                    """, {
                        "p_uid": firebase_uid,
                        "p_type": db_source_type,
                        "p_title": f"{title} - {author}",
                        "p_content": text,
                        "p_chunk_type": chunk_type or "paragraph",
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
                    print(f"[SUCCESS] Text Item Ingested: {title} (Type: {db_source_type})")
                    return True
                
                print(f"[ERROR] Embedding was None for: {title}")
                return False
                
    except Exception as e:
        print(f"Error: {e}")
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
                    DELETE FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id = :p_book
                      AND source_type IN ('HIGHLIGHT', 'INSIGHT', 'NOTES')
                    """,
                    {"p_uid": firebase_uid, "p_book": book_id},
                )
                deleted = cursor.rowcount or 0

                if not highlights:
                    connection.commit()
                    return {"success": True, "deleted": deleted, "inserted": 0}

                texts = [h.get("text", "") for h in highlights]
                embeddings = batch_get_embeddings(texts)

                insert_sql = """
                    INSERT INTO TOMEHUB_CONTENT
                    (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, "COMMENT", tags)
                    VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_comment, :p_tags)
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
                            "p_chunk_type": chunk_type,
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
    Keep Personal Note representation in AI store consistent with category policy.
    - Always deletes existing PERSONAL_NOTE/INSIGHT rows for this note id
    - Re-inserts only when category == IDEAS and delete_only is False
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
                    DELETE FROM TOMEHUB_CONTENT
                    WHERE firebase_uid = :p_uid
                      AND book_id = :p_book
                      AND source_type IN ('PERSONAL_NOTE', 'INSIGHT')
                    """,
                    {"p_uid": firebase_uid, "p_book": book_id},
                )
                deleted = cursor.rowcount or 0

                normalized_category = str(category or "PRIVATE").strip().upper()
                if delete_only or normalized_category != "IDEAS":
                    connection.commit()
                    return {"success": True, "deleted": deleted, "inserted": 0}

                text = (content or "").strip()
                if not DataHealthService.validate_content(text):
                    connection.commit()
                    return {"success": True, "deleted": deleted, "inserted": 0}

                embedding = get_embedding(text)
                if embedding is None:
                    return {"success": False, "deleted": deleted, "inserted": 0, "error": "embedding_failed"}

                tags_json = json.dumps(tags, ensure_ascii=False) if tags else None
                prepared_tags = prepare_labels(tags_json) if tags_json else []
                out_id = cursor.var(oracledb.NUMBER)

                cursor.execute(
                    """
                    INSERT INTO TOMEHUB_CONTENT
                    (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, "COMMENT", tags)
                    VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_comment, :p_tags)
                    RETURNING id INTO :p_out_id
                    """,
                    {
                        "p_uid": firebase_uid,
                        "p_type": "INSIGHT",
                        "p_title": f"{title} - {author}",
                        "p_content": text,
                        "p_chunk_type": "personal_note",
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
                return {"success": True, "deleted": deleted, "inserted": inserted}
    except Exception as e:
        logger.error(f"[ERROR] sync_personal_note_for_item failed: {e}")
        return {"success": False, "deleted": deleted, "inserted": inserted, "error": str(e)}

def process_bulk_items_logic(items: list, firebase_uid: str) -> dict:
    print(f"Bulk processing {len(items)} items...")
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
                            print("[WARN] Embedding missing for item, skipping.")
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
                            INSERT INTO TOMEHUB_CONTENT 
                            (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, categories, "COMMENT", tags)
                            VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_cats, :p_comment, :p_tags)
                            RETURNING id INTO :p_out_id
                        """, {
                            "p_uid": firebase_uid,
                            "p_type": db_source_type,
                            "p_title": f"{item.get('title')} - {item.get('author')}",
                            "p_content": text,
                            "p_chunk_type": item.get('chunk_type') or 'full_text',
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
                        print(f"Item failed: {e}")
                conn.commit()
    except Exception as e:
        print(f"Bulk process error: {e}")
        
    return {"success": success}

if __name__ == "__main__":
    DatabaseManager.init_pool()
    if len(sys.argv) >= 5:
        # python ingest_book.py <path> <title> <author> [uid] [book_id]
        path = sys.argv[1]
        title = sys.argv[2]
        author = sys.argv[3]
        uid = sys.argv[4] if len(sys.argv) > 4 else "test_user_001"
        book_id = sys.argv[5] if len(sys.argv) > 5 else None
        
        ingest_book(path, title, author, uid, book_id)
