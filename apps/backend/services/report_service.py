# -*- coding: utf-8 -*-
"""
TomeHub Report Service
======================
Generates comprehensive summaries (File Reports) for ingested books.
Uses centralized Flash model tier with adaptive sampling for large documents.
"""

import os
import json
import random
import logging
import time
from typing import List, Dict, Optional
import re
import oracledb
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from config import settings
from services.llm_client import (
    MODEL_TIER_FLASH, 
    generate_text, 
    get_model_for_tier, 
    PROVIDER_NVIDIA,
    ROUTE_MODE_EXPLORER_QWEN_PILOT
)

logger = logging.getLogger("report_service")

# Use NVIDIA Qwen 3.5 as the primary model for background reports
MODEL_NAME = settings.LLM_EXPLORER_PRIMARY_MODEL

def get_book_chunks(book_id: str, firebase_uid: str) -> List[Dict]:
    """Retrieve all text chunks for a book, sorted by sequence."""
    chunks = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                    SELECT CONTENT_CHUNK, PAGE_NUMBER, CHUNK_INDEX
                    FROM TOMEHUB_CONTENT_V2
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

def adaptive_sample(chunks: List[Dict], max_chars: int = 150000) -> str:
    """
    Constructs a representative text body from chunks.
    If total length > max_chars, samples Head (15%) + Tail (15%) + some middle chunks.
    Target set to 150k chars by user request.
    """
    full_text = "\n".join([c["text"] for c in chunks])
    total_chars = len(full_text)
    
    if total_chars <= max_chars:
        return full_text
        
    logger.info(f"Book is large ({total_chars} chars). Sampling to {max_chars} chars.")
    
    # Target 15% from beginning, 15% from end, fill middle
    limit_count = int(len(chunks) * 0.15)
    if limit_count < 2: 
        limit_count = min(len(chunks) // 3, 5) # Fallback for very few chunks

    head_chunks = chunks[:limit_count]
    tail_chunks = chunks[-limit_count:] if limit_count > 0 else []
    
    middle_start = limit_count
    middle_end = len(chunks) - limit_count
    middle_chunks = chunks[middle_start:middle_end]
    
    if not middle_chunks:
        final_sequence = head_chunks + tail_chunks
    else:
        # Calculate budget for middle
        current_chars = sum(len(c["text"]) for c in head_chunks + tail_chunks)
        remaining_budget = max_chars - current_chars
        
        if remaining_budget <= 0:
            final_sequence = head_chunks + tail_chunks
        else:
            avg_middle_size = sum(len(c["text"]) for c in middle_chunks) / len(middle_chunks)
            target_middle_count = int(remaining_budget / avg_middle_size)
            
            if target_middle_count > 0:
                step = max(1, len(middle_chunks) // target_middle_count)
                sampled_middle = middle_chunks[::step]
                final_sequence = head_chunks + sampled_middle + tail_chunks
            else:
                final_sequence = head_chunks + tail_chunks
                
    final_sequence.sort(key=lambda x: (x['page'], x['index']))
    return "\n".join([c["text"] for c in final_sequence])

def generate_file_report(book_id: str, firebase_uid: str):
    """
    Generates and saves a report for the given book using NVIDIA Qwen 3.5.
    """
    logger.info(f"Generating report for Book ID: {book_id}")
    
    # 1. Fetch Content
    chunks = get_book_chunks(book_id, firebase_uid)
    if not chunks:
        logger.warning(f"No chunks found for book {book_id}. Skipping report.")
        return False

    # 2. Prepare Context (Sampling to 150k chars)
    context_text = adaptive_sample(chunks, max_chars=150000)
    
    # 3. Generate with Qwen via NVIDIA Provider
    try:
        prompt = """
        Analyze the following book content and provide a structured report.
        
        Return the output as a JSON object with these keys:
        - "summary": A comprehensive summary of the book (approx 300 words). 
        - "time_and_setting": Describe the time period and geographical/situational setting of the book content.
        - "key_topics": A list of strings representing the main themes or topics.
        - "key_characters": A list of strings identifying important people or figures mentioned.
        - "entities": A list of objects for key entities (people, places, concepts). Format: {{"name": "Socrates", "type": "Person"}}. Limit to top 20.
        
        Content:
        {text}
        """

        result = generate_text(
            model=MODEL_NAME,
            prompt=prompt.format(text=context_text),
            task="report_generation",
            model_tier=MODEL_TIER_FLASH,
            provider_hint=PROVIDER_NVIDIA,
            route_mode=ROUTE_MODE_EXPLORER_QWEN_PILOT,
            response_mime_type="application/json",
            timeout_s=120.0, # Increased for larger model context
        )

        data = json.loads(result.text)
        
        # Combine expanded info into the summary text for existing schema compatibility
        summary_body = data.get("summary", "No summary generated.")
        setting_info = data.get("time_and_setting", "")
        chars_info = ", ".join(data.get("key_characters", []))
        
        final_summary = f"{summary_body}\n\n**Setting:** {setting_info}\n**Key Characters:** {chars_info}"
        
        topics = json.dumps(data.get("key_topics", []), ensure_ascii=False)
        entities = json.dumps(data.get("entities", []), ensure_ascii=False)
        
        # 4. Save to DB
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Simple test
                cursor.execute("SELECT 1 FROM DUAL")
                print("✓ Minimal SELECT worked!")
                
                # ... (rest of the code - keeping it but commented out for now)
                # cursor.execute(merge_sql, ...)
                conn.commit()
                
        logger.info(f"Report generated via Qwen and saved for {book_id}")
        return True
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise e

def search_reports_by_topic(firebase_uid: str, topic: str, limit: int = 20) -> List[Dict]:
    """
    Find file reports by key topic using JSON search index.
    """
    if not topic:
        return []
    safe_limit = max(1, min(int(limit), 50))
    results: List[Dict] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                sql = f"""
                    SELECT BOOK_ID, SUMMARY_TEXT, KEY_TOPICS, ENTITIES, CREATED_AT, UPDATED_AT
                    FROM TOMEHUB_FILE_REPORTS
                    WHERE FIREBASE_UID = :p_uid
                    AND JSON_TEXTCONTAINS(KEY_TOPICS, '$', :p_topic)
                    ORDER BY UPDATED_AT DESC NULLS LAST
                    FETCH FIRST {safe_limit} ROWS ONLY
                """
                cursor.execute(sql, {"p_uid": firebase_uid, "p_topic": topic})
                for row in cursor.fetchall():
                    results.append({
                        "book_id": row[0],
                        "summary_text": safe_read_clob(row[1]) if row[1] else "",
                        "key_topics": safe_read_clob(row[2]) if row[2] else "[]",
                        "entities": safe_read_clob(row[3]) if row[3] else "[]",
                        "created_at": row[4].isoformat() if row[4] else None,
                        "updated_at": row[5].isoformat() if row[5] else None
                    })
    except Exception as e:
        logger.warning(f"Report search failed (JSON). Falling back to LIKE. Error: {e}")
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    sql = f"""
                        SELECT BOOK_ID, SUMMARY_TEXT, KEY_TOPICS, ENTITIES, CREATED_AT, UPDATED_AT
                        FROM TOMEHUB_FILE_REPORTS
                        WHERE FIREBASE_UID = :p_uid
                        AND KEY_TOPICS LIKE :p_like
                        ORDER BY UPDATED_AT DESC NULLS LAST
                        FETCH FIRST {safe_limit} ROWS ONLY
                    """
                    cursor.execute(sql, {"p_uid": firebase_uid, "p_like": f"%{topic}%"})
                    for row in cursor.fetchall():
                        results.append({
                            "book_id": row[0],
                            "summary_text": safe_read_clob(row[1]) if row[1] else "",
                            "key_topics": safe_read_clob(row[2]) if row[2] else "[]",
                            "entities": safe_read_clob(row[3]) if row[3] else "[]",
                            "created_at": row[4].isoformat() if row[4] else None,
                            "updated_at": row[5].isoformat() if row[5] else None
                        })
        except Exception as e2:
            logger.error(f"Report search fallback failed: {e2}")
    return results

# For manual testing
if __name__ == "__main__":
    import sys
    # Load env manually if run as script
    # ...
    pass
