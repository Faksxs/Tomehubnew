# -*- coding: utf-8 -*-
"""
TomeHub Chat History Service
============================
Manages persistent chat sessions and message history.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from infrastructure.db_manager import DatabaseManager, safe_read_clob

logger = logging.getLogger("chat_history_service")

def create_session(firebase_uid: str, title: str = "New Chat") -> int:
    """Create a new chat session and return its ID."""
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                id_var = cursor.var(int)
                cursor.execute("""
                    INSERT INTO TOMEHUB_CHAT_SESSIONS (FIREBASE_UID, TITLE)
                    VALUES (:p_uid, :title)
                    RETURNING ID INTO :id_col
                """, {"p_uid": firebase_uid, "title": title, "id_col": id_var})
                session_id = id_var.getvalue()[0]
                conn.commit()
                return int(session_id)
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        return None

def add_message(session_id: int, role: str, content: str, citations: Optional[List[Dict]] = None):
    """Save a message to the history."""
    try:
        citations_json = json.dumps(citations or [], ensure_ascii=False)
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO TOMEHUB_CHAT_MESSAGES (SESSION_ID, ROLE, CONTENT, CITATIONS)
                    VALUES (:p_sid, :p_role, :p_content, :p_citations)
                """, {
                    "p_sid": session_id,
                    "p_role": role,
                    "p_content": content,
                    "p_citations": citations_json
                })
                
                # Also update session's UPDATED_AT
                cursor.execute("UPDATE TOMEHUB_CHAT_SESSIONS SET UPDATED_AT = CURRENT_TIMESTAMP WHERE ID = :p_sid", {"p_sid": session_id})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to add message to session {session_id}: {e}")

def get_session_history(session_id: int, limit: int = 10) -> List[Dict]:
    """Retrieve last N messages for context."""
    messages = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT ROLE, CONTENT, CITATIONS
                    FROM (
                        SELECT ROLE, CONTENT, CITATIONS, CREATED_AT
                        FROM TOMEHUB_CHAT_MESSAGES
                        WHERE SESSION_ID = :p_sid
                        ORDER BY CREATED_AT DESC
                    )
                    WHERE ROWNUM <= :p_limit
                    ORDER BY CREATED_AT ASC
                """, {"p_sid": session_id, "p_limit": limit})
                
                rows = cursor.fetchall()
                for role, content_lob, citations_json in rows:
                    messages.append({
                        "role": role,
                        "content": safe_read_clob(content_lob),
                        "citations": json.loads(safe_read_clob(citations_json) or "[]")
                    })
    except Exception as e:
        logger.error(f"Failed to get history for session {session_id}: {e}")
        
    return messages

def get_session_context(session_id: int) -> Dict:
    """Return both running summary and recent messages."""
    result = {
        "summary": "",
        "recent_messages": []
    }
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT RUNNING_SUMMARY FROM TOMEHUB_CHAT_SESSIONS WHERE ID = :p_sid", {"p_sid": session_id})
                row = cursor.fetchone()
                if row:
                    result["summary"] = safe_read_clob(row[0]) or ""
                    
        result["recent_messages"] = get_session_history(session_id, limit=5)
    except Exception as e:
        logger.error(f"Failed to get context for session {session_id}: {e}")
        
    return result

def update_session_summary(session_id: int, summary: str):
    """Update the running summary of the session (legacy, still supports text)."""
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE TOMEHUB_CHAT_SESSIONS 
                    SET RUNNING_SUMMARY = :p_summary, UPDATED_AT = CURRENT_TIMESTAMP
                    WHERE ID = :p_sid
                """, {"p_summary": summary, "p_sid": session_id})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to update session summary {session_id}: {e}")

def update_conversation_state(session_id: int, state: Dict):
    """Update the structured conversation state (stored as JSON in RUNNING_SUMMARY)."""
    try:
        state_json = json.dumps(state, ensure_ascii=False)
        update_session_summary(session_id, state_json)
        logger.info(f"Session {session_id} conversation state updated.")
    except Exception as e:
        logger.error(f"Failed to update conversation state {session_id}: {e}")

def get_conversation_state(session_id: int) -> Dict:
    """
    Retrieve the structured conversation state.
    Returns default empty state if none exists or parsing fails.
    """
    default_state = {
        "active_topic": "",
        "assumptions": [],
        "open_questions": [],
        "established_facts": [],
        "turn_count": 0
    }
    
    try:
        ctx = get_session_context(session_id)
        summary = ctx.get('summary', '')
        
        if not summary:
            return default_state
            
        # Try to parse as JSON (new structured format)
        if summary.strip().startswith('{'):
            return json.loads(summary)
        else:
            # Legacy: plain text summary - migrate to structured format
            return {
                **default_state,
                "legacy_summary": summary,
                "active_topic": summary[:100] if summary else ""
            }
    except Exception as e:
        logger.error(f"Failed to get conversation state {session_id}: {e}")
        return default_state

def extract_structured_state(session_id: int):
    """
    Extracts structured conversation state from chat history using LLM.
    Replaces the old unstructured summarization.
    
    State includes:
    - active_topic: Current main subject of discussion
    - assumptions: List of working assumptions with confidence levels
    - open_questions: Unanswered questions from the conversation
    - established_facts: Verified information from user's notes
    """
    try:
        import google.generativeai as genai
        
        # 1. Fetch Context
        current_state = get_conversation_state(session_id)
        messages = get_session_history(session_id, limit=10)
        
        if len(messages) < 2:  # Too few to analyze
            return
        
        # 2. Build conversation log
        history_str = ""
        for msg in messages:
            content = msg['content'][:300] if len(msg['content']) > 300 else msg['content']
            history_str += f"{msg['role'].upper()}: {content}\n---\n"
        
        # 3. Prepare previous state for context
        prev_state_str = json.dumps(current_state, ensure_ascii=False, indent=2) if current_state.get('active_topic') else "İlk durum (henüz analiz yapılmadı)"
        
        # 4. Prompt for structured extraction
        prompt = f"""
Aşağıdaki konuşma geçmişini analiz ederek YAPILANDIRILMIŞ bir konuşma durumu çıkar.
SADECE JSON formatında yanıt ver, başka hiçbir şey yazma.

ÖNCEKİ DURUM:
{prev_state_str}

YENİ MESAJLAR:
{history_str}

JSON FORMATI (Türkçe içerik):
{{
    "active_topic": "Şu an tartışılan ana konu (tek cümle)",
    "assumptions": [
        {{"id": 1, "text": "Varsayım metni", "confidence": "HIGH/MEDIUM/LOW", "introduced_at_turn": 1}}
    ],
    "open_questions": [
        "Henüz cevaplanmamış soru 1",
        "Henüz cevaplanmamış soru 2"
    ],
    "established_facts": [
        {{"text": "Notlardan doğrulanmış bilgi", "source": "Kaynak adı veya ID"}}
    ],
    "turn_count": {current_state.get('turn_count', 0) + len(messages) // 2}
}}

KURALLAR:
1. Varsayımlar (assumptions): Kullanıcının veya sistemin yaptığı yorumları/çıkarımları kaydet. Bunlar GERÇEK DEĞİL.
2. Yerleşik Gerçekler (established_facts): SADECE notlardan/kaynaklardan doğrulanmış bilgiler.
3. Açık Sorular (open_questions): Hala cevapsız kalan veya belirsiz konular.
4. Önceki durumu GÜNCELLE, silme. Geçerliliğini yitiren varsayımları kaldırabilirsin.

JSON ÇIKTISI:"""

        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        if response and response.text:
            # Parse the JSON response
            response_text = response.text.strip()
            
            # Clean potential markdown code blocks
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            try:
                new_state = json.loads(response_text)
                update_conversation_state(session_id, new_state)
                logger.info(f"Session {session_id} structured state extracted: {new_state.get('active_topic', 'N/A')}")
            except json.JSONDecodeError as je:
                logger.warning(f"Failed to parse state JSON: {je}. Raw: {response_text[:200]}")
                # Fallback: store raw response as legacy summary
                update_session_summary(session_id, response_text)
            
    except Exception as e:
        logger.error(f"Failed to extract structured state for session {session_id}: {e}")

# Keep old function for backward compatibility
def summarize_session_history(session_id: int):
    """
    Legacy function - now delegates to structured state extraction.
    Kept for backward compatibility with existing callers.
    """
    extract_structured_state(session_id)

