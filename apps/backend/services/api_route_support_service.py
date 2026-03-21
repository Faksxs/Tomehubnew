import asyncio
import json
from datetime import datetime
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from fastapi import BackgroundTasks, HTTPException

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.analytics_service import (
    count_lemma_occurrences,
    extract_target_term,
    get_keyword_contexts,
    is_analytic_word_count,
    resolve_book_id_from_question,
)
from services.query_plan_service import looks_explicit_compare_query
from utils.logger import get_logger

logger = get_logger("api_route_support")

_HIGHLIGHT_FOCUS_TERMS = (
    "highlight",
    "highlights",
    "altini ciz",
    "altÄ±nÄ± Ã§iz",
    "notlarim",
    "notlarÄ±m",
    "notlar",
    "alinan not",
    "alÄ±ntÄ±",
    "alinti",
    "insight",
)


def _resolve_requested_domain_mode(request_obj: Any) -> str:
    """
    Keep route handlers compatible with older request models that may not
    define domain_mode yet while newer service code expects it.
    """
    value = getattr(request_obj, "domain_mode", "AUTO")
    text = str(value or "AUTO").strip().upper()
    return text or "AUTO"


def is_scope_policy_enabled_for_chat(firebase_uid: str, mode: str) -> bool:
    if not bool(getattr(settings, "SEARCH_SCOPE_POLICY_ENABLED", False)):
        return False

    enabled_modes = {
        str(m or "").strip().upper()
        for m in getattr(settings, "SEARCH_SCOPE_POLICY_CHAT_MODES", []) or []
    }
    if enabled_modes and str(mode or "STANDARD").strip().upper() not in enabled_modes:
        return False

    canary_uids = set(getattr(settings, "SEARCH_SCOPE_POLICY_CANARY_UIDS", set()) or set())
    if canary_uids and str(firebase_uid or "").strip() not in canary_uids:
        return False
    return True


def _looks_highlight_focused_query(message: str) -> bool:
    text = str(message or "").strip().lower()
    return any(term in text for term in _HIGHLIGHT_FOCUS_TERMS)


def resolve_chat_scope_policy(
    *,
    message: str,
    firebase_uid: str,
    requested_scope_mode: str,
    explicit_book_id: Optional[str],
    context_book_id: Optional[str],
    compare_mode: Optional[str] = None,
    target_book_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    requested = str(requested_scope_mode or "AUTO").strip().upper() or "AUTO"
    anchor_book_id = str(explicit_book_id or context_book_id or "").strip() or None
    requested_targets = [str(b or "").strip() for b in (target_book_ids or []) if str(b or "").strip()]
    compare_mode_effective = str(compare_mode or "EXPLICIT_ONLY").strip().upper() or "EXPLICIT_ONLY"
    compare_query_explicit = looks_explicit_compare_query(message)

    if requested in {"AUTO", "BOOK_FIRST"}:
        if len(requested_targets) >= 2:
            return {
                "scope_mode": "GLOBAL",
                "resolved_book_id": anchor_book_id,
                "scope_decision": "COMPARE_GLOBAL_OVERRIDE_TARGETS",
            }
        if compare_query_explicit and compare_mode_effective in {"EXPLICIT_ONLY", "AUTO"}:
            return {
                "scope_mode": "GLOBAL",
                "resolved_book_id": anchor_book_id,
                "scope_decision": "COMPARE_GLOBAL_OVERRIDE_QUERY",
            }

    chosen_book_id = anchor_book_id
    if not chosen_book_id and requested in {"AUTO", "BOOK_FIRST"}:
        try:
            chosen_book_id = resolve_book_id_from_question(firebase_uid, message)
        except Exception:
            chosen_book_id = None

    if requested == "GLOBAL":
        return {
            "scope_mode": "GLOBAL",
            "resolved_book_id": None,
            "scope_decision": "GLOBAL_FORCED",
        }
    if requested == "HIGHLIGHT_FIRST":
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": chosen_book_id,
            "scope_decision": "HIGHLIGHT_FIRST_FORCED",
        }
    if requested == "BOOK_FIRST":
        if chosen_book_id:
            return {
                "scope_mode": "BOOK_FIRST",
                "resolved_book_id": chosen_book_id,
                "scope_decision": "BOOK_FIRST_FORCED",
            }
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": None,
            "scope_decision": "BOOK_FIRST_FALLBACK_NO_BOOK",
        }

    if chosen_book_id:
        return {
            "scope_mode": "BOOK_FIRST",
            "resolved_book_id": chosen_book_id,
            "scope_decision": "AUTO_RESOLVED_BOOK",
        }
    if _looks_highlight_focused_query(message):
        return {
            "scope_mode": "HIGHLIGHT_FIRST",
            "resolved_book_id": None,
            "scope_decision": "AUTO_HIGHLIGHT_FOCUS",
        }
    return {
        "scope_mode": "HIGHLIGHT_FIRST",
        "resolved_book_id": None,
        "scope_decision": "AUTO_DEFAULT_HIGHLIGHT_FIRST",
    }


def fetch_realtime_poll_payload(
    *,
    firebase_uid: str,
    since_ms: int,
    limit: int,
) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit), 300))
    cutoff_ms = max(int(since_ms or 0), 0)
    events: list[dict[str, Any]] = []

    try:
        from services.change_event_service import fetch_change_events_since

        changes, last_event_id = fetch_change_events_since(
            firebase_uid=firebase_uid,
            since_ms=cutoff_ms,
            limit=safe_limit,
        )
        if changes:
            server_time_ms = int(datetime.now().timestamp() * 1000)
            return {
                "success": True,
                "server_time_ms": server_time_ms,
                "server_time": datetime.now().isoformat(),
                "last_event_id": last_event_id,
                "changes": changes,
                "events": changes,
                "count": len(changes),
                "source": "outbox",
            }
    except Exception as exc:
        logger.warning("Realtime polling outbox read failed (fallback to legacy query): %s", exc)

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ITEM_ID, TITLE, COALESCE(UPDATED_AT, CREATED_AT)
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE FIREBASE_UID = :p_uid
                    ORDER BY COALESCE(UPDATED_AT, CREATED_AT) DESC
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_uid": firebase_uid, "p_limit": safe_limit},
                )
                for row in cursor.fetchall():
                    ts = row[2]
                    ts_ms = int(ts.timestamp() * 1000) if ts else int(datetime.now().timestamp() * 1000)
                    if ts_ms <= cutoff_ms:
                        continue
                    events.append(
                        {
                            "event_type": "book.updated",
                            "book_id": str(row[0]),
                            "title": str(row[1] or ""),
                            "updated_at_ms": ts_ms,
                        }
                    )

                cursor.execute(
                    """
                    SELECT ITEM_ID, CONTENT_TYPE, MAX(CREATED_AT)
                    FROM TOMEHUB_CONTENT_V2
                    WHERE FIREBASE_UID = :p_uid
                      AND CONTENT_TYPE IN ('HIGHLIGHT', 'INSIGHT', 'PERSONAL_NOTE')
                    GROUP BY ITEM_ID, CONTENT_TYPE
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_uid": firebase_uid, "p_limit": safe_limit},
                )
                for row in cursor.fetchall():
                    source_type = str(row[1] or "").upper()
                    ts = row[2]
                    if not ts:
                        continue
                    ts_ms = int(ts.timestamp() * 1000)
                    if ts_ms <= cutoff_ms:
                        continue
                    event_type = "highlight.synced" if source_type in {"HIGHLIGHT", "INSIGHT"} else "note.synced"
                    events.append(
                        {
                            "event_type": event_type,
                            "book_id": str(row[0] or ""),
                            "source_type": source_type,
                            "updated_at_ms": ts_ms,
                        }
                    )
    except Exception as exc:
        logger.error("Realtime polling query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Realtime polling failed")

    events.sort(key=lambda item: int(item.get("updated_at_ms") or 0), reverse=True)
    if len(events) > safe_limit:
        events = events[:safe_limit]

    server_time_ms = int(datetime.now().timestamp() * 1000)
    return {
        "success": True,
        "server_time_ms": server_time_ms,
        "server_time": datetime.now().isoformat(),
        "last_event_id": None,
        "changes": events,
        "events": events,
        "count": len(events),
        "source": "legacy_aggregate",
    }


def build_search_analytic_response(
    *,
    firebase_uid: str,
    question: str,
    book_id: Optional[str],
    context_book_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not is_analytic_word_count(question):
        return None

    term = extract_target_term(question)
    resolved_book_id = book_id or context_book_id
    if not resolved_book_id:
        resolved_book_id = resolve_book_id_from_question(firebase_uid, question)

    if not resolved_book_id and not term:
        return {
            "answer": "Analitik sayÄ±m iÃ§in kitap ve kelime gerekli. Ã–rn: \"Mahur Beste kitabÄ±nda zaman kelimesi kaÃ§ defa geÃ§iyor?\"",
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "book_and_term_missing"},
                "search_variant": "search",
                "graph_capability": "enabled",
            },
        }
    if not resolved_book_id:
        return {
            "answer": "Analitik sayÄ±m iÃ§in hangi kitabÄ± soruyorsun? Ã–rn: \"Mahur Beste kitabÄ±nda zaman kelimesi kaÃ§ defa geÃ§iyor?\"",
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "book_id_required"},
                "search_variant": "search",
                "graph_capability": "enabled",
            },
        }
    if not term:
        return {
            "answer": "SayÄ±lacak kelimeyi belirtir misin?",
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "term_missing"},
                "search_variant": "search",
                "graph_capability": "enabled",
            },
        }

    count = count_lemma_occurrences(firebase_uid, resolved_book_id, term)
    contexts = get_keyword_contexts(firebase_uid, resolved_book_id, term, limit=10)
    metadata_dict = {
        "status": "analytic",
        "analytics": {
            "type": "word_count",
            "term": term,
            "count": count,
            "match": "lemma",
            "scope": "book_chunks",
            "resolved_book_id": resolved_book_id,
            "contexts": contexts if count > 0 else [],
            "debug": {"cache": "disabled"},
        },
        "search_variant": "search",
        "graph_capability": "enabled",
    }
    logger.debug("Analytic search context count", extra={"count": len(metadata_dict["analytics"]["contexts"])})
    return {
        "answer": f"\"{term}\" kelimesi bu kitapta toplam {count} kez geÃ§iyor.",
        "sources": [],
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata_dict,
    }


def resolve_scope_context(
    *,
    firebase_uid: str,
    message: str,
    mode: str,
    requested_scope_mode: str,
    explicit_book_id: Optional[str],
    context_book_id: Optional[str],
    requested_resource_type: Optional[str],
    compare_mode: Optional[str],
    target_book_ids: Optional[List[str]],
) -> Dict[str, Any]:
    scope_policy_active = is_scope_policy_enabled_for_chat(firebase_uid, mode)
    effective_book_id = explicit_book_id
    effective_resource_type = requested_resource_type
    effective_scope_mode = "GLOBAL"
    scope_decision = "LEGACY_SCOPE_POLICY_DISABLED"
    if scope_policy_active:
        scope_state = resolve_chat_scope_policy(
            message=message,
            firebase_uid=firebase_uid,
            requested_scope_mode=requested_scope_mode,
            explicit_book_id=explicit_book_id,
            context_book_id=context_book_id,
            compare_mode=compare_mode,
            target_book_ids=target_book_ids,
        )
        effective_scope_mode = scope_state["scope_mode"]
        scope_decision = scope_state["scope_decision"]
        effective_book_id = scope_state.get("resolved_book_id")

        if effective_scope_mode == "BOOK_FIRST":
            effective_resource_type = "BOOK"
        elif effective_scope_mode == "HIGHLIGHT_FIRST":
            effective_resource_type = "ALL_NOTES"

    return {
        "scope_policy_active": scope_policy_active,
        "scope_decision": scope_decision,
        "scope_mode": effective_scope_mode,
        "resolved_book_id": effective_book_id,
        "effective_resource_type": effective_resource_type,
    }


async def execute_search_request(
    *,
    search_request: Any,
    firebase_uid: str,
    generate_answer_fn: Callable[..., Any],
) -> Dict[str, Any]:
    visibility_scope = "all" if search_request.include_private_notes else search_request.visibility_scope
    requested_domain_mode = _resolve_requested_domain_mode(search_request)

    analytic_payload = build_search_analytic_response(
        firebase_uid=firebase_uid,
        question=search_request.question,
        book_id=search_request.book_id,
        context_book_id=search_request.context_book_id,
    )
    if analytic_payload is not None:
        return analytic_payload

    scope_ctx = resolve_scope_context(
        firebase_uid=firebase_uid,
        message=search_request.question,
        mode=search_request.mode,
        requested_scope_mode=search_request.scope_mode,
        explicit_book_id=search_request.book_id,
        context_book_id=search_request.context_book_id,
        requested_resource_type=search_request.resource_type,
        compare_mode=search_request.compare_mode,
        target_book_ids=search_request.target_book_ids,
    )

    loop = asyncio.get_running_loop()
    answer, sources, metadata = await loop.run_in_executor(
        None,
        partial(
            generate_answer_fn,
            search_request.question,
            firebase_uid,
            scope_ctx["resolved_book_id"],
            None,
            "",
            search_request.limit,
            search_request.offset,
            None,
            scope_ctx["effective_resource_type"],
            scope_ctx["scope_mode"],
            scope_ctx["scope_policy_active"],
            search_request.compare_mode,
            search_request.target_book_ids,
            visibility_scope,
            search_request.content_type,
            search_request.ingestion_type,
            requested_domain_mode,
        ),
    )

    logger.info(
        "Search finished successfully",
        extra={
            "answer_length": len(answer),
            "source_count": len(sources) if sources else 0,
            "first_source_title": sources[0].get("title") if sources else None,
            "first_source_score": sources[0].get("similarity_score") if sources else None,
            "metadata": metadata,
        },
    )

    if isinstance(metadata, dict):
        metadata.setdefault("search_variant", "search")
        metadata.setdefault("graph_capability", "enabled")
        metadata.setdefault("scope_policy_active", scope_ctx["scope_policy_active"])
        metadata.setdefault("scope_decision", scope_ctx["scope_decision"])
        metadata.setdefault("scope_mode", scope_ctx["scope_mode"])
        metadata.setdefault("resolved_book_id", scope_ctx["resolved_book_id"])
        metadata.setdefault("visibility_scope", visibility_scope)
        metadata.setdefault("content_type_filter", search_request.content_type)
        metadata.setdefault("ingestion_type_filter", search_request.ingestion_type)
        metadata.setdefault("requested_domain_mode", requested_domain_mode)

    return {
        "answer": answer,
        "sources": sources or [],
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata,
    }


async def _prepare_chat_session_context(
    *,
    loop: asyncio.AbstractEventLoop,
    firebase_uid: str,
    session_id: Optional[int],
    message: str,
    create_session_fn: Callable[..., Any],
    get_session_context_fn: Callable[..., Any],
    get_memory_context_snippet_fn: Callable[..., Any],
) -> tuple[int, Dict[str, Any], str]:
    effective_session_id = session_id
    if not effective_session_id:
        new_title = f"Chat: {message[:40]}..."
        effective_session_id = await loop.run_in_executor(None, create_session_fn, firebase_uid, new_title)
        if not effective_session_id:
            raise HTTPException(status_code=500, detail="Failed to create session")

    ctx_data = await loop.run_in_executor(None, get_session_context_fn, effective_session_id)
    memory_context_snippet = await loop.run_in_executor(None, get_memory_context_snippet_fn, firebase_uid)
    return effective_session_id, ctx_data, memory_context_snippet


async def maybe_execute_chat_analytic_response(
    *,
    loop: asyncio.AbstractEventLoop,
    firebase_uid: str,
    session_id: int,
    message: str,
    book_id: Optional[str],
    add_message_fn: Callable[..., Any],
    summarize_session_history_fn: Callable[..., Any],
    background_tasks: BackgroundTasks,
) -> Optional[Dict[str, Any]]:
    if not is_analytic_word_count(message):
        return None

    term = extract_target_term(message)
    resolved_book_id = book_id
    if not resolved_book_id:
        resolved_book_id = resolve_book_id_from_question(firebase_uid, message)

    if not resolved_book_id and not term:
        answer = "Analitik sayÄ±m iÃ§in kitap ve kelime gerekli. Ã–rn: \"Mahur Beste kitabÄ±nda zaman kelimesi kaÃ§ defa geÃ§iyor?\""
        await loop.run_in_executor(None, add_message_fn, session_id, "assistant", answer, [])
        background_tasks.add_task(summarize_session_history_fn, session_id)
        return {
            "answer": answer,
            "session_id": session_id,
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "conversation_state": {},
            "thinking_history": [],
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "book_and_term_missing"},
            },
        }
    if not resolved_book_id:
        answer = "Analitik sayÄ±m iÃ§in hangi kitabÄ± soruyorsun? Ã–rn: \"Mahur Beste kitabÄ±nda zaman kelimesi kaÃ§ defa geÃ§iyor?\""
        await loop.run_in_executor(None, add_message_fn, session_id, "assistant", answer, [])
        background_tasks.add_task(summarize_session_history_fn, session_id)
        return {
            "answer": answer,
            "session_id": session_id,
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "conversation_state": {},
            "thinking_history": [],
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "book_id_required"},
            },
        }
    if not term:
        answer = "SayÄ±lacak kelimeyi belirtir misin?"
        await loop.run_in_executor(None, add_message_fn, session_id, "assistant", answer, [])
        background_tasks.add_task(summarize_session_history_fn, session_id)
        return {
            "answer": answer,
            "session_id": session_id,
            "sources": [],
            "timestamp": datetime.now().isoformat(),
            "conversation_state": {},
            "thinking_history": [],
            "metadata": {
                "status": "analytic",
                "analytics": {"type": "word_count", "error": "term_missing"},
            },
        }

    try:
        count = count_lemma_occurrences(firebase_uid, resolved_book_id, term)
    except Exception as exc:
        logger.error("Primary count failed: %s", exc)
        count = 0

    answer = f"\"{term}\" kelimesi bu kitapta toplam **{count}** kez geÃ§iyor."
    logger.info("Final Narrative Answer: %s", answer)
    contexts = get_keyword_contexts(firebase_uid, resolved_book_id, term, limit=10)

    await loop.run_in_executor(None, add_message_fn, session_id, "assistant", answer, [])
    background_tasks.add_task(summarize_session_history_fn, session_id)
    return {
        "answer": answer,
        "session_id": session_id,
        "sources": [],
        "timestamp": datetime.now().isoformat(),
        "conversation_state": {},
        "thinking_history": [],
        "metadata": {
            "status": "analytic",
            "analytics": {
                "type": "word_count",
                "term": term,
                "count": count,
                "match": "lemma",
                "scope": "book_chunks",
                "resolved_book_id": resolved_book_id,
                "contexts": contexts,
            },
        },
    }


async def execute_chat_request(
    *,
    chat_request: Any,
    firebase_uid: str,
    background_tasks: BackgroundTasks,
    generate_answer_fn: Callable[..., Any],
    get_rag_context_fn: Callable[..., Any],
    generate_evaluated_answer_fn: Callable[..., Any],
    create_session_fn: Callable[..., Any],
    add_message_fn: Callable[..., Any],
    get_session_context_fn: Callable[..., Any],
    summarize_session_history_fn: Callable[..., Any],
    get_memory_context_snippet_fn: Callable[..., Any],
    refresh_memory_profile_fn: Callable[..., Any],
) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    requested_domain_mode = _resolve_requested_domain_mode(chat_request)
    session_id, ctx_data, memory_context_snippet = await _prepare_chat_session_context(
        loop=loop,
        firebase_uid=firebase_uid,
        session_id=chat_request.session_id,
        message=chat_request.message,
        create_session_fn=create_session_fn,
        get_session_context_fn=get_session_context_fn,
        get_memory_context_snippet_fn=get_memory_context_snippet_fn,
    )

    await loop.run_in_executor(None, add_message_fn, session_id, "user", chat_request.message)

    analytic_payload = await maybe_execute_chat_analytic_response(
        loop=loop,
        firebase_uid=firebase_uid,
        session_id=session_id,
        message=chat_request.message,
        book_id=chat_request.book_id,
        add_message_fn=add_message_fn,
        summarize_session_history_fn=summarize_session_history_fn,
        background_tasks=background_tasks,
    )
    if analytic_payload is not None:
        return analytic_payload

    scope_ctx = resolve_scope_context(
        firebase_uid=firebase_uid,
        message=chat_request.message,
        mode=chat_request.mode,
        requested_scope_mode=chat_request.scope_mode,
        explicit_book_id=chat_request.book_id,
        context_book_id=chat_request.context_book_id,
        requested_resource_type=chat_request.resource_type,
        compare_mode=chat_request.compare_mode,
        target_book_ids=chat_request.target_book_ids,
    )

    use_explorer_mode = chat_request.mode == "EXPLORER"
    answer = "ÃœzgÃ¼nÃ¼m, ilgili iÃ§erik bulunamadÄ±."
    sources: List[Dict[str, Any]] = []
    conversation_state = None
    thinking_history: List[Any] = []
    final_metadata: Dict[str, Any] = {}

    retrieval_limit = int(chat_request.limit or 20)
    retrieval_limit = max(20, retrieval_limit) if use_explorer_mode else max(10, retrieval_limit)
    retrieval_limit = min(100, retrieval_limit)

    if use_explorer_mode:
        state_payload = str((ctx_data or {}).get("conversation_state_json") or "").strip()
        summary_payload = str((ctx_data or {}).get("summary") or "").strip()
        conversation_state = {
            "active_topic": "",
            "assumptions": [],
            "open_questions": [],
            "established_facts": [],
            "turn_count": 0,
        }
        raw_state_payload = state_payload or summary_payload
        if raw_state_payload:
            if raw_state_payload.startswith("{"):
                try:
                    parsed_state = json.loads(raw_state_payload)
                    if isinstance(parsed_state, dict):
                        conversation_state.update(parsed_state)
                except Exception:
                    conversation_state["legacy_summary"] = raw_state_payload
                    conversation_state["active_topic"] = raw_state_payload[:100]
            else:
                conversation_state["legacy_summary"] = raw_state_payload
                conversation_state["active_topic"] = raw_state_payload[:100]
        if memory_context_snippet:
            conversation_state["memory_profile"] = memory_context_snippet[:1000]

        rag_ctx = await loop.run_in_executor(
            None,
            partial(
                get_rag_context_fn,
                chat_request.message,
                firebase_uid,
                scope_ctx["resolved_book_id"],
                chat_history=ctx_data["recent_messages"],
                mode="EXPLORER",
                resource_type=scope_ctx["effective_resource_type"],
                scope_mode=scope_ctx["scope_mode"],
                apply_scope_policy=scope_ctx["scope_policy_active"],
                compare_mode=chat_request.compare_mode,
                target_book_ids=chat_request.target_book_ids,
                limit=retrieval_limit,
                offset=chat_request.offset,
                domain_mode=requested_domain_mode,
            ),
        )

        if rag_ctx:
            final_result = await generate_evaluated_answer_fn(
                question=chat_request.message,
                chunks=rag_ctx["chunks"],
                answer_mode="EXPLORER",
                confidence_score=rag_ctx["confidence"],
                network_status=rag_ctx.get("network_status", "IN_NETWORK"),
                conversation_state=conversation_state,
                source_diversity_count=int(rag_ctx.get("source_diversity_count") or 0),
            )

            answer = final_result["final_answer"]
            thinking_history = final_result["metadata"].get("history", [])
            rag_meta = rag_ctx.get("metadata", {})
            if rag_meta:
                if "degradations" in rag_meta:
                    if "degradations" not in final_result["metadata"]:
                        final_result["metadata"]["degradations"] = []
                    final_result["metadata"]["degradations"].extend(rag_meta["degradations"])
                for key in (
                    "retrieval_fusion_mode",
                    "retrieval_path",
                    "resolved_domain_mode",
                    "domain_confidence",
                    "domain_reason",
                    "provider_policy_applied",
                    "graph_candidates_count",
                    "external_graph_candidates_count",
                    "islamic_external_candidates_count",
                    "vector_candidates_count",
                    "source_diversity_count",
                    "source_type_diversity_count",
                    "academic_scope",
                    "external_kb_used",
                    "islamic_external_used",
                    "islamic_provider_counts",
                    "quran_external_used",
                    "hadith_external_used",
                    "wikidata_qid",
                    "openalex_used",
                    "dbpedia_used",
                    "orkg_used",
                    "search_log_id",
                    "graph_bridge_attempted",
                    "quote_target_count",
                    "compare_applied",
                    "target_books_used",
                    "target_books_truncated",
                    "unauthorized_target_book_ids",
                    "evidence_policy",
                    "per_book_evidence_count",
                    "latency_budget_hit",
                    "compare_degrade_reason",
                    "compare_mode",
                ):
                    if key in rag_meta:
                        final_result["metadata"][key] = rag_meta[key]

            final_metadata = final_result["metadata"]
            used_chunks = final_result["metadata"].get("used_chunks", [])
            for index, chunk in enumerate(used_chunks, 1):
                sources.append(
                    {
                        "id": index,
                        "title": chunk.get("title", "Unknown"),
                        "score": chunk.get("answerability_score", 0),
                        "page_number": chunk.get("page_number", 0),
                        "content": str(chunk.get("content_chunk", ""))[:500],
                        "source_type": chunk.get("source_type"),
                        "provider": chunk.get("provider"),
                        "source_url": chunk.get("source_url"),
                        "reference": chunk.get("reference"),
                        "religious_source_kind": chunk.get("religious_source_kind"),
                        "canonical_reference": chunk.get("canonical_reference"),
                        "is_exact_match": chunk.get("is_exact_match"),
                    }
                )
    else:
        answer_result, sources_result, meta_result = await loop.run_in_executor(
            None,
            partial(
                generate_answer_fn,
                chat_request.message,
                firebase_uid,
                scope_ctx["resolved_book_id"],
                ctx_data["recent_messages"],
                "\n\n".join(part for part in [memory_context_snippet, ctx_data["summary"] or ""] if part).strip(),
                retrieval_limit,
                chat_request.offset,
                session_id,
                scope_ctx["effective_resource_type"],
                scope_ctx["scope_mode"],
                scope_ctx["scope_policy_active"],
                chat_request.compare_mode,
                chat_request.target_book_ids,
                "default",
                None,
                None,
                requested_domain_mode,
            ),
        )
        if answer_result:
            answer = answer_result
            sources = sources_result or []
            final_metadata = meta_result or {}

    if isinstance(final_metadata, dict):
        final_metadata.setdefault("effective_retrieval_limit", retrieval_limit)
        final_metadata.setdefault("scope_policy_active", scope_ctx["scope_policy_active"])
        final_metadata.setdefault("scope_decision", scope_ctx["scope_decision"])
        final_metadata.setdefault("scope_mode", scope_ctx["scope_mode"])
        final_metadata.setdefault("resolved_book_id", scope_ctx["resolved_book_id"])
        final_metadata.setdefault("memory_profile_loaded", bool(memory_context_snippet))
        final_metadata.setdefault("requested_domain_mode", requested_domain_mode)

    await loop.run_in_executor(None, add_message_fn, session_id, "assistant", answer, sources)
    background_tasks.add_task(summarize_session_history_fn, session_id)
    background_tasks.add_task(refresh_memory_profile_fn, firebase_uid)

    return {
        "answer": answer,
        "session_id": session_id,
        "sources": sources or [],
        "timestamp": datetime.now().isoformat(),
        "conversation_state": conversation_state,
        "thinking_history": thinking_history,
        "metadata": final_metadata,
    }
