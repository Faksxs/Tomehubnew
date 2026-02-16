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
from config import settings
from services.llm_client import (
    MODEL_TIER_FLASH,
    MODEL_TIER_LITE,
    generate_text,
    get_model_for_tier,
)

logger = logging.getLogger("chat_history_service")
_CONV_STATE_COLUMN_AVAILABLE: Optional[bool] = None


def _conversation_state_column_available() -> bool:
    global _CONV_STATE_COLUMN_AVAILABLE
    if _CONV_STATE_COLUMN_AVAILABLE is not None:
        return bool(_CONV_STATE_COLUMN_AVAILABLE)
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM user_tab_columns
                    WHERE table_name = 'TOMEHUB_CHAT_SESSIONS'
                      AND column_name = 'CONVERSATION_STATE_JSON'
                    """
                )
                row = cursor.fetchone()
                _CONV_STATE_COLUMN_AVAILABLE = bool(row and int(row[0] or 0) > 0)
    except Exception:
        _CONV_STATE_COLUMN_AVAILABLE = False
    return bool(_CONV_STATE_COLUMN_AVAILABLE)


def _update_conversation_state_column(session_id: int, state_json: str) -> bool:
    if not _conversation_state_column_available():
        return False
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE TOMEHUB_CHAT_SESSIONS
                    SET CONVERSATION_STATE_JSON = :p_state, UPDATED_AT = CURRENT_TIMESTAMP
                    WHERE ID = :p_sid
                    """,
                    {"p_state": state_json, "p_sid": session_id},
                )
                conn.commit()
        return True
    except Exception as e:
        if "ORA-00904" in str(e):
            global _CONV_STATE_COLUMN_AVAILABLE
            _CONV_STATE_COLUMN_AVAILABLE = False
            return False
        logger.error(f"Failed to update conversation_state_json {session_id}: {e}")
        return False

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

def get_session_history(session_id: int, limit: Optional[int] = None) -> List[Dict]:
    """Retrieve last N messages for context."""
    messages = []
    if limit is None:
        limit = settings.CHAT_CONTEXT_LIMIT
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
        "conversation_state_json": "",
        "recent_messages": []
    }
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                if _conversation_state_column_available():
                    try:
                        cursor.execute(
                            "SELECT RUNNING_SUMMARY, CONVERSATION_STATE_JSON FROM TOMEHUB_CHAT_SESSIONS WHERE ID = :p_sid",
                            {"p_sid": session_id},
                        )
                        row = cursor.fetchone()
                        if row:
                            result["summary"] = safe_read_clob(row[0]) or ""
                            result["conversation_state_json"] = safe_read_clob(row[1]) or ""
                    except Exception as e:
                        if "ORA-00904" in str(e):
                            global _CONV_STATE_COLUMN_AVAILABLE
                            _CONV_STATE_COLUMN_AVAILABLE = False
                        else:
                            raise
                if not result["summary"]:
                    cursor.execute("SELECT RUNNING_SUMMARY FROM TOMEHUB_CHAT_SESSIONS WHERE ID = :p_sid", {"p_sid": session_id})
                    row = cursor.fetchone()
                    if row:
                        result["summary"] = safe_read_clob(row[0]) or ""
                    
        result["recent_messages"] = get_session_history(session_id, limit=settings.CHAT_CONTEXT_LIMIT)
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

def update_session_tags(session_id: int, tags: List[str]):
    """Update session tags as JSON array."""
    try:
        tags_json = json.dumps(tags, ensure_ascii=False)
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE TOMEHUB_CHAT_SESSIONS
                    SET TAGS = :p_tags, UPDATED_AT = CURRENT_TIMESTAMP
                    WHERE ID = :p_sid
                """, {"p_tags": tags_json, "p_sid": session_id})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to update session tags {session_id}: {e}")

def generate_and_update_session_tags(session_id: int):
    """
    Generate topic tags from recent messages and update TAGS JSON.
    """
    try:
        messages = get_session_history(session_id, limit=settings.CHAT_SUMMARY_LIMIT)
        if not messages or len(messages) < 2:
            return

        history_str = ""
        for msg in messages:
            role = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
            content = msg['content']
            if len(content) > 300:
                content = content[:300]
            history_str += f"{role}: {content}\n"

        # LLM-based tag generation
        try:
            prompt = f"""
Aşağıdaki konuşmadan 3-5 adet kısa etiket üret.
Kurallar:
- Sadece etiketleri JSON array olarak döndür (örn: ["Felsefe","Etik"])
- Kişisel veri veya özel isim kullanma
- Türkçe etiketler

KONUŞMA:
{history_str}
"""
            model = get_model_for_tier(MODEL_TIER_LITE)
            result = generate_text(
                model=model,
                prompt=prompt,
                task="chat_tags",
                model_tier=MODEL_TIER_LITE,
                timeout_s=20.0,
            )
            tags_text = result.text.strip() if result else "[]"
        except Exception as e:
            logger.error(f"Tag generation failed: {e}")
            tags_text = "[]"

        # Parse JSON array
        try:
            if tags_text.startswith('```'):
                tags_text = tags_text.split('```')[1]
                if tags_text.startswith('json'):
                    tags_text = tags_text[4:]
                tags_text = tags_text.strip()
            tags = json.loads(tags_text)
            if isinstance(tags, list):
                # Normalize and limit
                cleaned = []
                for t in tags:
                    if not isinstance(t, str):
                        continue
                    t = t.strip().lstrip('#')
                    if t:
                        cleaned.append(t[:40])
                tags = cleaned[:5]
            else:
                tags = []
        except Exception:
            tags = []

        if tags:
            update_session_tags(session_id, tags)
    except Exception as e:
        logger.error(f"Failed to generate/update session tags {session_id}: {e}")

def update_conversation_state(session_id: int, state: Dict):
    """Dual-write structured conversation state into dedicated JSON column and legacy summary."""
    try:
        state_json = json.dumps(state, ensure_ascii=False)
        _update_conversation_state_column(session_id, state_json)
        update_session_summary(session_id, state_json)
        logger.info(f"Session {session_id} conversation state updated.")
    except Exception as e:
        logger.error(f"Failed to update conversation state {session_id}: {e}")

def get_session_title(session_id: int) -> str:
    """Fetch current session title."""
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT TITLE FROM TOMEHUB_CHAT_SESSIONS WHERE ID = :p_sid", {"p_sid": session_id})
                row = cursor.fetchone()
                return row[0] if row else ""
    except Exception as e:
        logger.error(f"Failed to get session title {session_id}: {e}")
        return ""

def is_title_locked(session_id: int) -> bool:
    """Check if title generation is locked for this session."""
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT TITLE_LOCKED FROM TOMEHUB_CHAT_SESSIONS WHERE ID = :p_sid", {"p_sid": session_id})
                row = cursor.fetchone()
                return bool(row[0]) if row is not None else False
    except Exception as e:
        logger.error(f"Failed to check title lock {session_id}: {e}")
        return False

def lock_session_title(session_id: int):
    """Lock title generation for this session."""
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE TOMEHUB_CHAT_SESSIONS
                    SET TITLE_LOCKED = 1, UPDATED_AT = CURRENT_TIMESTAMP
                    WHERE ID = :p_sid
                """, {"p_sid": session_id})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to lock session title {session_id}: {e}")

def update_session_title(session_id: int, title: str):
    """Update session title."""
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE TOMEHUB_CHAT_SESSIONS
                    SET TITLE = :p_title, UPDATED_AT = CURRENT_TIMESTAMP
                    WHERE ID = :p_sid
                """, {"p_title": title, "p_sid": session_id})
                conn.commit()
    except Exception as e:
        logger.error(f"Failed to update session title {session_id}: {e}")

def _fallback_title_from_history(messages: List[Dict]) -> Optional[str]:
    """Heuristic fallback title using first user message."""
    first_user = None
    for msg in messages:
        if msg.get("role") == "user":
            first_user = msg.get("content", "")
            break
    if not first_user:
        return None
    words = first_user.strip().split()
    if not words:
        return None
    return " ".join(words[:8])[:settings.CHAT_TITLE_MAX_LENGTH].strip()

def generate_and_update_session_title(session_id: int):
    """
    Generate a short, descriptive title using recent messages.
    Only updates if current title is empty or default.
    """
    try:
        if is_title_locked(session_id):
            return

        current_title = (get_session_title(session_id) or "").strip()
        if current_title and current_title.lower() != "new chat":
            lock_session_title(session_id)
            return

        # Ensure minimum messages before generating
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM TOMEHUB_CHAT_MESSAGES WHERE SESSION_ID = :p_sid",
                    {"p_sid": session_id}
                )
                msg_count = cursor.fetchone()[0]
        if msg_count < settings.CHAT_TITLE_MIN_MESSAGES:
            return

        messages = get_session_history(session_id, limit=settings.CHAT_SUMMARY_LIMIT)
        if not messages:
            return

        history_str = ""
        for msg in messages:
            role = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
            content = msg['content']
            if len(content) > 280:
                content = content[:280]
            history_str += f"{role}: {content}\n"

        # LLM-based title generation
        try:
            prompt = f"""
Aşağıdaki konuşmayı özetleyen kısa ve açıklayıcı bir başlık üret.
Kurallar:
- 3-6 kelime
- En fazla {settings.CHAT_TITLE_MAX_LENGTH} karakter
- Kişisel veri veya özel isim kullanma
- Sadece başlığı döndür (tırnak, nokta, açıklama yok)

KONUŞMA:
{history_str}
"""
            model = get_model_for_tier(MODEL_TIER_LITE)
            result = generate_text(
                model=model,
                prompt=prompt,
                task="chat_title",
                model_tier=MODEL_TIER_LITE,
                timeout_s=20.0,
            )
            title = result.text.strip() if result else ""
        except Exception as e:
            logger.error(f"Title generation failed: {e}")
            title = ""

        if not title:
            title = _fallback_title_from_history(messages) or ""

        if not title:
            title = f"Chat {datetime.utcnow().strftime('%Y-%m-%d')}"

        update_session_title(session_id, title[:settings.CHAT_TITLE_MAX_LENGTH].strip())
        lock_session_title(session_id)
    except Exception as e:
        logger.error(f"Failed to generate/update session title {session_id}: {e}")

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
        state_json = str(ctx.get("conversation_state_json") or "").strip()
        if state_json.startswith("{"):
            try:
                parsed = json.loads(state_json)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
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
        
        # 1. Fetch Context
        current_state = get_conversation_state(session_id)
        messages = get_session_history(session_id, limit=settings.CHAT_SUMMARY_LIMIT)
        
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

        model = get_model_for_tier(MODEL_TIER_FLASH)
        result = generate_text(
            model=model,
            prompt=prompt,
            task="chat_structured_state",
            model_tier=MODEL_TIER_FLASH,
            timeout_s=30.0,
        )

        if result and result.text:
            # Parse the JSON response
            response_text = result.text.strip()
            
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
    generate_and_update_session_title(session_id)
    generate_and_update_session_tags(session_id)

