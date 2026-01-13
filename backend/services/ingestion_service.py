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
from services.embedding_service import get_embedding
from utils.text_utils import normalize_text, deaccent_text, get_lemmas
import json

# Load environment variables - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)


def get_database_connection():
    """
    Establish connection to Oracle Database.
    
    Returns:
        oracledb.Connection: Active database connection
    """
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN", "tomehubdb_high")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    if not password:
        raise ValueError("DB_PASSWORD not found in .env file")
    
    connection = oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=password
    )
    
    return connection


def ingest_book(file_path: str, title: str, author: str, firebase_uid: str = "test_user_001", book_id: str = None) -> bool:
    """
    Complete book ingestion pipeline.
    
    1. Determine file type (PDF/EPUB)
    2. Extract text chunks with smart chunking
    3. Generate embeddings
    4. Store in Oracle DB (linked to book_id)
    5. CLEANUP: Delete the original file
    
    Args:
        file_path (str): Path to the file
        title (str): Book title
        author (str): Book author
        firebase_uid (str): User identifier
        book_id (str): Unique book identifier (linking chunks to metadata)
    
    Returns:
        bool: True if successful
    """
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
        print(f"[ERROR] Unsupported file type: {file_ext}")
        return False
    
    if not chunks:
        print(f"\n[ERROR] Failed to extract content")
        return False
    
    print(f"\n[SUCCESS] Extracted {len(chunks)} chunks")
    
    # Step 2: Connect to database
    print(f"\n{'='*70}")
    print("Step 2: Connecting to Oracle Database")
    print(f"{'='*70}")
    
    connection = None
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [OK] Connected to database")
    except Exception as e:
        print(f"\n[ERROR] Failed to connect to database: {e}")
        return False
    
    # Step 3: Process chunks
    print(f"\n{'='*70}")
    print("Step 3: Processing Chunks and Generating Embeddings")
    print(f"{'='*70}")
    
    insert_sql = """
    INSERT INTO TOMEHUB_CONTENT 
    (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens)
    VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm_content, :p_deaccent, :p_lemmas)
    """
    
    successful_inserts = 0
    failed_embeddings = 0
    
    for i, chunk in enumerate(chunks):
        chunk_text = chunk['text']
        page_num = chunk.get('page_num', 0) # 0 for epubs/unknown
        
        if not chunk_text or len(chunk_text.strip()) < 10:
            continue
            
        # Normalize content for search
        normalized_text = normalize_text(chunk_text)
        # Phase 1 NLP columns
        deaccented_text = deaccent_text(chunk_text)
        lemmas_json = json.dumps(get_lemmas(chunk_text), ensure_ascii=False)
            
        try:
            embedding = get_embedding(chunk_text)
            
            if embedding is None:
                failed_embeddings += 1
                continue
                
            cursor.execute(insert_sql, {
                "p_uid": firebase_uid,
                "p_type": "PDF" if file_ext == '.pdf' else "EPUB",
                "p_title": f"{title} - {author}",
                "p_content": chunk_text,
                "p_chunk_type": chunk.get('type', 'paragraph'),
                "p_page": page_num,
                "p_chunk_idx": i,
                "p_vec": embedding,
                "p_book_id": book_id,
                "p_norm_content": normalized_text,
                "p_deaccent": deaccented_text,
                "p_lemmas": lemmas_json
            })
            
            successful_inserts += 1
            if i % 10 == 0:
                print(f"[PROGRESS] Processed {i}/{len(chunks)}...")
                
        except Exception as e:
            print(f"[FAILED] Chunk {i}: {e}")
            continue
    
    # Step 4: Commit
    print(f"\n{'='*70}")
    print("Step 4: Committing to Database")
    print(f"{'='*70}")
    
    try:
        connection.commit()
        print(f"[SUCCESS] {successful_inserts} chunks inserted.")
    except Exception as e:
        print(f"[ERROR] Commit failed: {e}")
        connection.rollback()
        return False
    finally:
        cursor.close()
        connection.close()
    
    # Step 5: Cleanup
    print(f"\n{'='*70}")
    print("Step 5: Cleaning Up File")
    print(f"{'='*70}")
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[SUCCESS] Deleted original file: {file_path}")
        else:
            print("[WARNING] File not found for deletion.")
    except Exception as e:
        print(f"[ERROR] Failed to delete file: {e}")
    
    return successful_inserts > 0

# (Keep ingest_text_item and process_bulk_items_logic as is, just ensuring imports)
def ingest_text_item(text: str, title: str, author: str, source_type: str = "NOTE", firebase_uid: str = "test_user_001") -> bool:
    print(f"\n[INFO] Text Ingestion: {title}")
    try:
        connection = get_database_connection()
        cursor = connection.cursor()
        
        # NLP Processing
        normalized_text = normalize_text(text)
        deaccented_text = deaccent_text(text)
        lemmas_json = json.dumps(get_lemmas(text), ensure_ascii=False)
        
        embedding = get_embedding(text)
        if embedding:
            cursor.execute("""
                INSERT INTO TOMEHUB_CONTENT 
                (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, normalized_content, text_deaccented, lemma_tokens)
                VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_norm, :p_deaccent, :p_lemmas)
            """, {
                "p_uid": firebase_uid,
                "p_type": source_type,
                "p_title": f"{title} - {author}",
                "p_content": text,
                "p_chunk_type": "full_text",
                "p_page": 1,
                "p_chunk_idx": 0,
                "p_vec": embedding,
                "p_norm": normalized_text,
                "p_deaccent": deaccented_text,
                "p_lemmas": lemmas_json
            })
            connection.commit()
            return True
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        if 'connection' in locals(): connection.close()

def process_bulk_items_logic(items: list, firebase_uid: str) -> dict:
    print(f"Bulk processing {len(items)} items...")
    success = 0
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        import time
        for item in items:
            try:
                text = item.get('text', '')
                
                # NLP Processing
                normalized_text = normalize_text(text)
                deaccented_text = deaccent_text(text)
                lemmas_json = json.dumps(get_lemmas(text), ensure_ascii=False)
                
                embedding = get_embedding(text)
                if embedding:
                    cursor.execute("""
                        INSERT INTO TOMEHUB_CONTENT 
                        (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, normalized_content, text_deaccented, lemma_tokens)
                        VALUES (:uid, :type, :title, :content, 'full_text', 1, 0, :vec, :norm, :deaccent, :lemmas)
                    """, {
                        "uid": firebase_uid,
                        "type": item.get('type', 'NOTE'),
                        "title": f"{item.get('title')} - {item.get('author')}",
                        "content": text,
                        "vec": embedding,
                        "norm": normalized_text,
                        "deaccent": deaccented_text,
                        "lemmas": lemmas_json
                    })
                    success += 1
                    time.sleep(0.5) # Rate limit
            except Exception as e:
                print(f"Item failed: {e}")
        conn.commit()
    finally:
        conn.close()
        
    return {"success": success}

if __name__ == "__main__":
    if len(sys.argv) >= 5:
        # python ingest_book.py <path> <title> <author> [uid] [book_id]
        path = sys.argv[1]
        title = sys.argv[2]
        author = sys.argv[3]
        uid = sys.argv[4] if len(sys.argv) > 4 else "test_user_001"
        book_id = sys.argv[5] if len(sys.argv) > 5 else None
        
        ingest_book(path, title, author, uid, book_id)
