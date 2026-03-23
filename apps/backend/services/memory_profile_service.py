from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.chat_history_service import get_session_history
from services.library_service import _content_table_shape, resolve_active_content_table  # pragmatic reuse
from services.llm_client import MODEL_TIER_LITE, generate_text, get_model_for_tier

logger = logging.getLogger("memory_profile_service")

_PROFILE_TABLE = "TOMEHUB_USER_MEMORY_PROFILES"


def _table_exists(table_name: str) -> bool:
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM USER_TABLES
                    WHERE TABLE_NAME = :p_table
                    """,
                    {"p_table": table_name.upper()},
                )
                row = cursor.fetchone()
                return bool(row and int(row[0] or 0) > 0)
    except Exception:
        return False


def ensure_memory_profile_table() -> None:
    if _table_exists(_PROFILE_TABLE):
        return
    ddl_statements = [
        f"""
        CREATE TABLE {_PROFILE_TABLE} (
            ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            FIREBASE_UID VARCHAR2(255) NOT NULL,
            PROFILE_SUMMARY CLOB,
            ACTIVE_THEMES CLOB CHECK (ACTIVE_THEMES IS JSON),
            RECURRING_SOURCES CLOB CHECK (RECURRING_SOURCES IS JSON),
            OPEN_QUESTIONS CLOB CHECK (OPEN_QUESTIONS IS JSON),
            EVIDENCE_COUNTS CLOB CHECK (EVIDENCE_COUNTS IS JSON),
            LAST_REFRESHED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT UQ_TH_MEMORY_PROFILE_UID UNIQUE (FIREBASE_UID)
        )
        """,
        f"CREATE INDEX IDX_TH_MEMORY_PROFILE_UID ON {_PROFILE_TABLE}(FIREBASE_UID)",
    ]
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                for ddl in ddl_statements:
                    try:
                        cursor.execute(ddl)
                    except Exception as inner:
                        msg = str(inner).lower()
                        if "ora-00955" in msg or "already" in msg:
                            continue
                        raise
                conn.commit()
    except Exception as exc:
        logger.warning("Could not ensure memory profile table: %s", exc)


def _safe_json_loads(raw: Any, default: Any) -> Any:
    text = safe_read_clob(raw) if raw is not None and not isinstance(raw, str) else raw
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def get_memory_profile(firebase_uid: str) -> Optional[Dict[str, Any]]:
    ensure_memory_profile_table()
    if not _table_exists(_PROFILE_TABLE):
        return None
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT PROFILE_SUMMARY, ACTIVE_THEMES, RECURRING_SOURCES, OPEN_QUESTIONS,
                           EVIDENCE_COUNTS, LAST_REFRESHED_AT, UPDATED_AT
                    FROM {_PROFILE_TABLE}
                    WHERE FIREBASE_UID = :p_uid
                    """,
                    {"p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "firebase_uid": firebase_uid,
                    "profile_summary": safe_read_clob(row[0]) or "",
                    "active_themes": _safe_json_loads(row[1], []),
                    "recurring_sources": _safe_json_loads(row[2], []),
                    "open_questions": _safe_json_loads(row[3], []),
                    "evidence_counts": _safe_json_loads(row[4], {}),
                    "last_refreshed_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None,
                    "status": "ready",
                }
    except Exception as exc:
        logger.warning("Failed to load memory profile for %s: %s", firebase_uid, exc)
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:
        return None


def should_refresh_profile(
    existing_profile: Optional[Dict[str, Any]],
    *,
    min_refresh_minutes: int,
    force: bool = False,
    now: Optional[datetime] = None,
) -> bool:
    if force or not existing_profile:
        return True
    refreshed_at = _parse_iso_datetime(existing_profile.get("last_refreshed_at"))
    if refreshed_at is None:
        return True
    current = now or datetime.now(UTC)
    return refreshed_at <= current - timedelta(minutes=max(1, int(min_refresh_minutes)))


def _fetch_recent_chat_summaries(firebase_uid: str, limit: int = 5) -> List[Dict[str, Any]]:
    rows_out: List[Dict[str, Any]] = []
    safe_limit = max(1, min(int(limit), 10))
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT ID, TITLE, RUNNING_SUMMARY, UPDATED_AT
                    FROM TOMEHUB_CHAT_SESSIONS
                    WHERE FIREBASE_UID = :p_uid
                    ORDER BY UPDATED_AT DESC NULLS LAST
                    FETCH FIRST {safe_limit} ROWS ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                for row in cursor.fetchall():
                    rows_out.append(
                        {
                            "session_id": int(row[0]),
                            "title": str(row[1] or "").strip(),
                            "summary": safe_read_clob(row[2]) or "",
                            "updated_at": row[3].isoformat() if row[3] else None,
                        }
                    )
    except Exception as exc:
        logger.warning("Failed to fetch chat summaries for %s: %s", firebase_uid, exc)
    return rows_out


def _fetch_recent_messages(firebase_uid: str, session_limit: int = 2, message_limit: int = 6) -> List[Dict[str, Any]]:
    sessions = _fetch_recent_chat_summaries(firebase_uid, limit=session_limit)
    items: List[Dict[str, Any]] = []
    for session in sessions:
        session_id = session.get("session_id")
        if not session_id:
            continue
        try:
            for msg in get_session_history(int(session_id), limit=message_limit):
                content = str(msg.get("content") or "").strip()
                if not content:
                    continue
                items.append(
                    {
                        "session_id": int(session_id),
                        "role": str(msg.get("role") or "").strip(),
                        "content": content[:400],
                    }
                )
        except Exception as exc:
            logger.warning(
                "Failed to fetch session history for memory profile uid=%s session_id=%s: %s",
                firebase_uid,
                session_id,
                exc,
            )
            continue
    return items[: max(2, session_limit * message_limit)]


def _fetch_recent_notes(firebase_uid: str, limit: int = 18) -> List[Dict[str, Any]]:
    table_name = resolve_active_content_table()
    if not table_name:
        return []
    shape = _content_table_shape(table_name)
    content_col = shape.get("content_col")
    type_col = shape.get("type_col")
    title_col = shape.get("title_col")
    created_at_col = shape.get("created_at_col") or "ID"
    if not content_col or not type_col:
        return []
    safe_limit = max(1, min(int(limit), 40))
    items: List[Dict[str, Any]] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {title_col or "NULL"}, {content_col}, {type_col}, {created_at_col}
                    FROM {table_name}
                    WHERE FIREBASE_UID = :p_uid
                      AND UPPER({type_col}) IN ('HIGHLIGHT', 'INSIGHT', 'PERSONAL_NOTE', 'ARTICLE')
                    ORDER BY {created_at_col} DESC NULLS LAST
                    FETCH FIRST {safe_limit} ROWS ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                for row in cursor.fetchall():
                    items.append(
                        {
                            "title": str(row[0] or "").strip(),
                            "content_type": str(row[2] or "").strip().upper(),
                            "content": (safe_read_clob(row[1]) or "")[:500],
                            "updated_at": row[3].isoformat() if hasattr(row[3], "isoformat") else None,
                        }
                    )
    except Exception as exc:
        logger.warning("Failed to fetch notes for %s: %s", firebase_uid, exc)
    return items


def _fetch_recent_reports(firebase_uid: str, limit: int = 6) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 12))
    items: List[Dict[str, Any]] = []
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT BOOK_ID, SUMMARY_TEXT, KEY_TOPICS, UPDATED_AT
                    FROM TOMEHUB_FILE_REPORTS
                    WHERE FIREBASE_UID = :p_uid
                    ORDER BY UPDATED_AT DESC NULLS LAST
                    FETCH FIRST {safe_limit} ROWS ONLY
                    """,
                    {"p_uid": firebase_uid},
                )
                for row in cursor.fetchall():
                    items.append(
                        {
                            "book_id": str(row[0] or "").strip(),
                            "summary_text": (safe_read_clob(row[1]) or "")[:600],
                            "key_topics": _safe_json_loads(row[2], []),
                            "updated_at": row[3].isoformat() if row[3] else None,
                        }
                    )
    except Exception as exc:
        logger.warning("Failed to fetch reports for %s: %s", firebase_uid, exc)
    return items


def collect_memory_evidence(firebase_uid: str) -> Dict[str, Any]:
    sessions = _fetch_recent_chat_summaries(firebase_uid)
    messages = _fetch_recent_messages(firebase_uid)
    notes = _fetch_recent_notes(firebase_uid)
    reports = _fetch_recent_reports(firebase_uid)
    counts = {
        "sessions": len(sessions),
        "messages": len(messages),
        "notes": len(notes),
        "reports": len(reports),
    }
    logger.info(
        "Memory evidence collected for %s: sessions=%d messages=%d notes=%d reports=%d",
        firebase_uid, counts["sessions"], counts["messages"], counts["notes"], counts["reports"],
    )
    return {
        "sessions": sessions,
        "messages": messages,
        "notes": notes,
        "reports": reports,
        "counts": counts,
    }


def _strip_code_fences(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def parse_profile_payload(text: str, fallback_counts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        payload = json.loads(_strip_code_fences(text))
    except Exception as exc:
        logger.warning("Failed to parse LLM profile JSON: %s – raw (first 300 chars): %s", exc, str(text or "")[:300])
        payload = {}
        
    def _ensure_list(val: Any) -> List[str]:
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
        if isinstance(val, str):
            return [x.strip() for x in val.split(",") if x.strip()]
        return []

    result = {
        "profile_summary": str(payload.get("profile_summary") or "").strip(),
        "active_themes": _ensure_list(payload.get("active_themes")),
        "recurring_sources": _ensure_list(payload.get("recurring_sources")),
        "open_questions": _ensure_list(payload.get("open_questions")),
        "evidence_counts": fallback_counts or {},
    }
    if result["profile_summary"] and not result["active_themes"] and not result["recurring_sources"] and not result["open_questions"]:
        logger.warning("LLM returned profile_summary but all structured arrays are empty – raw (first 500 chars): %s", str(text or "")[:500])
    return result


def _build_profile_prompt(evidence: Dict[str, Any]) -> str:
    return f"""
You are building a compact long-term memory profile for a TomeHub user.

Use the evidence below to infer:
- profile_summary: 4-6 sentences on recurring interests and current focus
- active_themes: an array of strings (up to 6 recurring themes or concepts)
- recurring_sources: an array of strings (up to 6 recurring authors, books, or source names)
- open_questions: an array of strings (up to 5 unresolved questions or tensions)

Return JSON only. DO NOT include evidence_counts in the JSON.

RECENT_CHAT_SUMMARIES:
{json.dumps(evidence.get("sessions", []), ensure_ascii=False)}

RECENT_CHAT_MESSAGES:
{json.dumps(evidence.get("messages", []), ensure_ascii=False)}

RECENT_NOTES:
{json.dumps(evidence.get("notes", []), ensure_ascii=False)}

RECENT_FILE_REPORTS:
{json.dumps(evidence.get("reports", []), ensure_ascii=False)}
""".strip()


def _store_memory_profile(firebase_uid: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_memory_profile_table()
    if not _table_exists(_PROFILE_TABLE):
        raise RuntimeError("Memory profile table is unavailable.")
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                MERGE INTO {_PROFILE_TABLE} target
                USING (SELECT :p_uid AS firebase_uid FROM DUAL) src
                ON (target.FIREBASE_UID = src.firebase_uid)
                WHEN MATCHED THEN
                  UPDATE SET
                    PROFILE_SUMMARY = :p_summary,
                    ACTIVE_THEMES = :p_themes,
                    RECURRING_SOURCES = :p_sources,
                    OPEN_QUESTIONS = :p_questions,
                    EVIDENCE_COUNTS = :p_counts,
                    LAST_REFRESHED_AT = CURRENT_TIMESTAMP,
                    UPDATED_AT = CURRENT_TIMESTAMP
                WHEN NOT MATCHED THEN
                  INSERT (
                    FIREBASE_UID, PROFILE_SUMMARY, ACTIVE_THEMES, RECURRING_SOURCES,
                    OPEN_QUESTIONS, EVIDENCE_COUNTS, LAST_REFRESHED_AT
                  )
                  VALUES (
                    :p_uid, :p_summary, :p_themes, :p_sources,
                    :p_questions, :p_counts, CURRENT_TIMESTAMP
                  )
                """,
                {
                    "p_uid": firebase_uid,
                    "p_summary": payload.get("profile_summary", ""),
                    "p_themes": json.dumps(payload.get("active_themes", []), ensure_ascii=False),
                    "p_sources": json.dumps(payload.get("recurring_sources", []), ensure_ascii=False),
                    "p_questions": json.dumps(payload.get("open_questions", []), ensure_ascii=False),
                    "p_counts": json.dumps(payload.get("evidence_counts", {}), ensure_ascii=False),
                },
            )
            conn.commit()
    profile = get_memory_profile(firebase_uid) or {}
    profile["status"] = "ready"
    return profile


def _build_degraded_profile(
    firebase_uid: str,
    *,
    existing_profile: Optional[Dict[str, Any]],
    evidence_counts: Optional[Dict[str, Any]],
    exc: Exception,
) -> Dict[str, Any]:
    error_text = str(exc or "").strip() or "memory_profile_refresh_failed"
    if existing_profile:
        cached = dict(existing_profile)
        cached["status"] = "cached"
        cached["refresh_error"] = error_text
        return cached
    return {
        "firebase_uid": firebase_uid,
        "profile_summary": "",
        "active_themes": [],
        "recurring_sources": [],
        "open_questions": [],
        "evidence_counts": evidence_counts or {},
        "status": "empty",
        "refresh_error": error_text,
    }


def refresh_memory_profile(firebase_uid: str, *, force: bool = False) -> Dict[str, Any]:
    existing = get_memory_profile(firebase_uid)
    min_refresh_minutes = int(getattr(settings, "MEMORY_PROFILE_MIN_REFRESH_MINUTES", 30) or 30)
    if not should_refresh_profile(existing, min_refresh_minutes=min_refresh_minutes, force=force):
        cached = dict(existing or {})
        cached["status"] = "cached"
        return cached

    evidence = collect_memory_evidence(firebase_uid)
    total_evidence = sum(int(v or 0) for v in evidence.get("counts", {}).values())
    if total_evidence == 0:
        logger.info("No evidence found for %s – storing empty profile.", firebase_uid)
        empty = {
            "firebase_uid": firebase_uid,
            "profile_summary": "",
            "active_themes": [],
            "recurring_sources": [],
            "open_questions": [],
            "evidence_counts": evidence.get("counts", {}),
            "status": "empty",
        }
        return _store_memory_profile(firebase_uid, empty)

    model = get_model_for_tier(MODEL_TIER_LITE)
    try:
        result = generate_text(
            model=model,
            prompt=_build_profile_prompt(evidence),
            task="memory_profile_refresh",
            model_tier=MODEL_TIER_LITE,
            timeout_s=45.0,
            response_mime_type="application/json",
        )
        raw_text = result.text if result else ""
        logger.info("LLM profile response for %s (len=%d): %s", firebase_uid, len(raw_text), raw_text[:400])
        payload = parse_profile_payload(raw_text, fallback_counts=evidence.get("counts", {}))
        logger.info(
            "Parsed profile for %s: summary_len=%d themes=%d sources=%d questions=%d counts=%s",
            firebase_uid,
            len(payload.get("profile_summary", "")),
            len(payload.get("active_themes", [])),
            len(payload.get("recurring_sources", [])),
            len(payload.get("open_questions", [])),
            payload.get("evidence_counts"),
        )
        if not payload.get("profile_summary"):
            payload["profile_summary"] = "User memory profile is available but the profile summary could not be synthesized."
        return _store_memory_profile(firebase_uid, payload)
    except Exception as exc:
        logger.warning(
            "Memory profile refresh degraded for %s: %s",
            firebase_uid,
            exc,
            exc_info=True,
        )
        return _build_degraded_profile(
            firebase_uid,
            existing_profile=existing,
            evidence_counts=evidence.get("counts", {}),
            exc=exc,
        )


def build_memory_context_snippet(profile: Optional[Dict[str, Any]], *, max_chars: int = 1200) -> str:
    if not profile:
        return ""
    parts: List[str] = []
    summary = str(profile.get("profile_summary") or "").strip()
    if summary:
        parts.append(f"### USER MEMORY PROFILE\n{summary}")
    themes = profile.get("active_themes") or []
    if themes:
        parts.append("Active themes: " + ", ".join(str(x).strip() for x in themes[:6] if str(x).strip()))
    open_questions = profile.get("open_questions") or []
    if open_questions:
        parts.append("Open questions: " + "; ".join(str(x).strip() for x in open_questions[:4] if str(x).strip()))
    snippet = "\n".join(parts).strip()
    return snippet[:max_chars].strip()


def get_memory_context_snippet(firebase_uid: str, *, max_chars: int = 1200) -> str:
    return build_memory_context_snippet(get_memory_profile(firebase_uid), max_chars=max_chars)
