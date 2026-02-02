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
from services.correction_service import repair_ocr_text
from services.data_health_service import DataHealthService
from services.data_cleaner_service import DataCleanerService
from utils.text_utils import normalize_text, deaccent_text, get_lemmas
import json
from concurrent.futures import ThreadPoolExecutor
from utils.logger import get_logger

logger = get_logger("ingestion_service")

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


def check_book_exists(title: str, author: str, firebase_uid: str, conn=None) -> bool:
    """
    Check if a book with the same title and author already exists for the user.
    """
    should_close = False
    try:
        if conn is None:
            conn = DatabaseManager.get_connection()
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
        # Note: DatabaseManager.get_connection() usually returns a pooled conn 
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
            conn = DatabaseManager.get_connection()
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
    # DEBUG: Verify file exists at start
    print(f"[DEBUG] ingest_book called with file_path: {file_path}")
    print(f"[DEBUG] File exists at start: {os.path.exists(file_path)}")
    
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
        with DatabaseManager.get_connection() as connection:
            with connection.cursor() as cursor:
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
                (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, categories)
                VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm_content, :p_deaccent, :p_lemmas, :p_cats)
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
                    
                    # Phase 13 Optimization: OCR Quality Gating & Automated Repair
                    confidence = chunk.get('confidence', 1.0)
                    repaired = False
                    
                    # Only repair/embed if not skipped
                    if not skip_chunk and confidence < 0.7:
                        logger.warning("Low OCR Confidence detected. Triggering automated repair.", extra={
                            "confidence": confidence, 
                            "page": chunk.get('page_num'),
                            "chunk_index": idx
                        })
                        # Automated Repair using Gemini
                        repaired_text = repair_ocr_text(chunk_text)
                        if repaired_text != chunk_text:
                            chunk_text = repaired_text
                            repaired = True
                            logger.info("OCR Repair successful", extra={"chunk_index": idx, "page": chunk.get('page_num')})
                    
                    return {
                        'index': idx,
                        'chunk': chunk,
                        'text_used': chunk_text, # The (potentially repaired) text
                        'repaired': repaired,
                        'normalized': normalize_text(chunk_text),
                        'deaccented': deaccent_text(chunk_text),
                        'lemmas': json.dumps(get_lemmas(chunk_text), ensure_ascii=False),
                        'classification': classify_passage_fast(chunk_text),
                        'decluttered_text': DataCleanerService.clean_with_ai(chunk_text, title=title, author=author),
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
                                "p_cats": categories
                            })
                            successful_inserts += 1
                        except Exception as e:
                            print(f"[FAILED] Chunk {res['index']} DB insert: {e}")
                    
                    print(f"[PROGRESS] Processed {min(i + BATCH_SIZE, len(valid_chunks))}/{len(valid_chunks)} chunks...")
                
                # Step 4: Commit (Releases Lock)
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
        logger.error(f"Ingestion failed: 0 chunks were successfully inserted (valid_chunks: {len(valid_chunks)})")
        return False
    
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

# (Keep ingest_text_item and process_bulk_items_logic as is, just ensuring imports)
def ingest_text_item(text: str, title: str, author: str, source_type: str = "NOTE", firebase_uid: str = "test_user_001", categories: Optional[str] = None) -> bool:
    # Normalize categories
    if categories:
        categories = ",".join([c.strip() for c in categories.replace("\n", ",").split(",") if c.strip()])
    print(f"\n[INFO] Text Ingestion: {title}")
    try:
        with DatabaseManager.get_connection() as connection:
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
                    book_id = str(uuid.uuid4())
                    
                    # Map source_type to satisfy DB Constraint (PDF/EPUB only likely)
                    valid_types = ['PDF', 'EPUB']
                    db_source_type = source_type
                    if db_source_type not in valid_types:
                        db_source_type = 'PDF' # Fallback
                    
                    cursor.execute("""
                        INSERT INTO TOMEHUB_CONTENT 
                        (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, categories)
                        VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm, :p_deaccent, :p_lemmas, :p_cats)
                    """, {
                        "p_uid": firebase_uid,
                        "p_type": db_source_type,
                        "p_title": f"{title} - {author}",
                        "p_content": text,
                        "p_chunk_type": "paragraph",
                        "p_page": 1,
                        "p_chunk_idx": 0,
                        "p_vec": embedding,
                        "p_book_id": book_id,
                        "p_norm": normalized_text,
                        "p_deaccent": deaccented_text,
                        "p_lemmas": lemmas_json,
                        "p_cats": categories
                    })
                    connection.commit()
                    print(f"[SUCCESS] Text Item Ingested: {title} (Type: {db_source_type})")
                    return True
                
                print(f"[ERROR] Embedding was None for: {title}")
                return False
                
    except Exception as e:
        print(f"Error: {e}")
        return False

def process_bulk_items_logic(items: list, firebase_uid: str) -> dict:
    print(f"Bulk processing {len(items)} items...")
    success = 0
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                import time
                for item in items:
                    try:
                        text = item.get('text', '')
                        if not DataHealthService.validate_content(text):
                            continue
                        
                        # NLP Processing
                        normalized_text = normalize_text(text)
                        deaccented_text = deaccent_text(text)
                        lemmas_json = json.dumps(get_lemmas(text), ensure_ascii=False)

                        # Normalize categories if present in item
                        cats = item.get('categories')
                        if cats:
                            cats = ",".join([c.strip() for c in cats.replace("\n", ",").split(",") if c.strip()])

                        if embedding:
                            cursor.execute("""
                                INSERT INTO TOMEHUB_CONTENT 
                                (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, normalized_content, text_deaccented, lemma_tokens, categories)
                                VALUES (:p_uid, :p_type, :p_title, :p_content, 'full_text', 1, 0, :p_vec, :p_norm, :p_deaccent, :p_lemmas, :p_cats)
                            """, {
                                "p_uid": firebase_uid,
                                "p_type": item.get('type', 'NOTE'),
                                "p_title": f"{item.get('title')} - {item.get('author')}",
                                "p_content": text,
                                "p_vec": embedding,
                                "p_norm": normalized_text,
                                "p_deaccent": deaccented_text,
                                "p_lemmas": lemmas_json,
                                "p_cats": cats
                            })
                            success += 1
                            time.sleep(0.5) # Rate limit
                    except Exception as e:
                        print(f"Item failed: {e}")
                conn.commit()
    except Exception as e:
        print(f"Bulk process error: {e}")
        
    return {"success": success}
        
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
