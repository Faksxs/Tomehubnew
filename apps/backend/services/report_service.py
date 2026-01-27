# -*- coding: utf-8 -*-
"""
TomeHub Report Service
======================
Generates comprehensive summaries (File Reports) for ingested books.
Uses Gemini 2.0 Flash with adaptive sampling for large documents.
"""

import os
import json
import random
import logging
import time
import google.generativeai as genai
from typing import List, Dict, Optional
import oracledb
from infrastructure.db_manager import DatabaseManager, safe_read_clob

logger = logging.getLogger("report_service")

# Configure Gemini
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    logger.warning("GEMINI_API_KEY is not set. Report generation will fail.")
else:
    genai.configure(api_key=api_key)

MODEL_NAME = "gemini-flash-latest" # Using 1.5 Flash for better quota/stability

def get_book_chunks(book_id: str, firebase_uid: str) -> List[Dict]:
    """Retrieve all text chunks for a book, sorted by sequence."""
    chunks = []
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT CONTENT_CHUNK, PAGE_NUMBER, CHUNK_INDEX
                    FROM TOMEHUB_CONTENT
                    WHERE BOOK_ID = :p_bid AND FIREBASE_UID = :p_uid
                    ORDER BY PAGE_NUMBER ASC, CHUNK_INDEX ASC
                """
                cursor.execute(query, {"p_bid": book_id, "p_uid": firebase_uid})
                rows = cursor.fetchall()
                
                for row in rows:
                    content = safe_read_clob(row[0])
                    chunks.append({
                        "text": content,
                        "page": row[1],
                        "index": row[2]
                    })
    except Exception as e:
        logger.error(f"Failed to fetch chunks for book {book_id}: {e}")
        
    return chunks

def adaptive_sample(chunks: List[Dict], max_chars: int = 500000) -> str:
    """
    Constructs a representative text body from chunks.
    If total length > max_chars, samples Head (10%) + Middle (Random) + Tail (10%).
    """
    full_text = "\n".join([c["text"] for c in chunks])
    total_chars = len(full_text)
    
    if total_chars <= max_chars:
        return full_text
        
    logger.info(f"Book is large ({total_chars} chars). Sampling to {max_chars} chars.")
    
    # Simple sampling strategy:
    # Top 10%
    limit_10 = int(len(chunks) * 0.1)
    head_chunks = chunks[:limit_10]
    tail_chunks = chunks[-limit_10:] if limit_10 > 0 else []
    
    # Reset
    middle_start = limit_10
    middle_end = len(chunks) - limit_10
    middle_indices = range(middle_start, middle_end)
    
    if not middle_indices:
        return "\n".join([c["text"] for c in head_chunks + tail_chunks])
        
    # Calculate step to fit budget
    # Avg chunk size
    avg_size = total_chars / len(chunks) if chunks else 1000
    current_chars = sum(len(c["text"]) for c in head_chunks + tail_chunks)
    remaining_budget = max_chars - current_chars
    
    target_middle_count = int(remaining_budget / avg_size)
    
    if target_middle_count > 0:
        step = max(1, len(middle_indices) // target_middle_count)
        selected_middle_indices = middle_indices[::step]
        sampled_middle = [chunks[i] for i in selected_middle_indices]
    else:
        sampled_middle = []
        
    # Reassemble in order
    final_sequence = head_chunks + sampled_middle + tail_chunks
    # Sort by index just in case
    final_sequence.sort(key=lambda x: (x['page'], x['index']))
    
    return "\n".join([c["text"] for c in final_sequence])

def generate_file_report(book_id: str, firebase_uid: str):
    """
    Generates and saves a report for the given book.
    """
    logger.info(f"Generating report for Book ID: {book_id}")
    
    # 1. Fetch Content
    chunks = get_book_chunks(book_id, firebase_uid)
    if not chunks:
        logger.warning(f"No chunks found for book {book_id}. Skipping report.")
        return False
        
    # 2. Prepare Context (Sampling)
    # 500k chars is approx 125k tokens. Safe for Flash.
    context_text = adaptive_sample(chunks, max_chars=400000)
    
    # 3. Generate with Gemini
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        
        prompt = """
        Analyze the following book content and provide a structured report.
        
        Return the output as a JSON object with these keys:
        - "summary": A comprehensive summary of the book (approx 300 words). Capture the main arguments, narrative arc, or core purpose.
        - "key_topics": A list of strings representing the main themes or topics (e.g. ["Ethics", "Utilitarianism", "History of Rome"]).
        - "entities": A list of objects for key entities (people, places, concepts). Format: {{"name": "Socrates", "type": "Person"}}. Limit to top 20.
        
        Content:
        {text}
        """
        
        response = model.generate_content(
            prompt.format(text=context_text),
            generation_config={"response_mime_type": "application/json"}
        )
        
        data = json.loads(response.text)
        
        summary = data.get("summary", "No summary generated.")
        topics = json.dumps(data.get("key_topics", []), ensure_ascii=False)
        entities = json.dumps(data.get("entities", []), ensure_ascii=False)
        
        # 4. Save to DB
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # Merge logic using DELETE then INSERT (Simpler for cross-db compatibility logic if needed, but merge is proper)
                # We'll use MERGE for Oracle
                
                merge_sql = """
                MERGE INTO TOMEHUB_FILE_REPORTS target
                USING (SELECT :p_bid as b_id, :p_uid as u_id FROM DUAL) src
                ON (target.BOOK_ID = src.b_id AND target.FIREBASE_UID = src.u_id)
                WHEN MATCHED THEN
                    UPDATE SET 
                        SUMMARY_TEXT = :p_summary,
                        KEY_TOPICS = :p_topics,
                        ENTITIES = :p_entities,
                        UPDATED_AT = CURRENT_TIMESTAMP
                WHEN NOT MATCHED THEN
                    INSERT (BOOK_ID, FIREBASE_UID, SUMMARY_TEXT, KEY_TOPICS, ENTITIES)
                    VALUES (src.b_id, src.u_id, :p_summary, :p_topics, :p_entities)
                """
                
                cursor.execute(merge_sql, {
                    "p_bid": book_id,
                    "p_uid": firebase_uid,
                    "p_summary": summary,
                    "p_topics": topics,
                    "p_entities": entities
                })
                conn.commit()

                
        logger.info(f"Report generated and saved for {book_id}")
        return True
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        print(f"[ERROR] DETAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

# For manual testing
if __name__ == "__main__":
    import sys
    # Load env manually if run as script
    # ...
    pass
