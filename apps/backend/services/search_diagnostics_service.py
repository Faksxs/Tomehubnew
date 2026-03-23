import json
import re
from typing import Any, Dict, Iterable, List, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.logger import get_logger

logger = get_logger("search_diagnostics")

_TRACE_QUERY_WS_RE = re.compile(r"\s+")
_TRACE_EMPTY_ANSWER_MARKERS = {
    "",
    "Cevap üretilemedi.",
    "Cevap Ã¼retilemedi.",
}


def _compact_query(query: Any, max_len: int = 160) -> str:
    text = _TRACE_QUERY_WS_RE.sub(" ", str(query or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bucket_count(retrieval_steps: Optional[Dict[str, Any]], *names: str) -> int:
    steps = retrieval_steps or {}
    total = 0
    for name in names:
        total += _int_value(steps.get(name))
    return total


def summarize_top_source_types(results: Optional[Iterable[Dict[str, Any]]], limit: int = 3) -> List[str]:
    source_types: List[str] = []
    seen = set()
    for row in results or []:
        source_type = str((row or {}).get("source_type") or "").strip().upper() or "UNKNOWN"
        if source_type in seen:
            continue
        seen.add(source_type)
        source_types.append(source_type)
        if len(source_types) >= limit:
            break
    return source_types


def build_search_diagnostic_trace(
    *,
    endpoint: str,
    query: Any,
    intent: Any,
    retrieval_mode: Any,
    selected_buckets: Optional[Iterable[str]],
    retrieval_steps: Optional[Dict[str, Any]],
    graph_used: Any,
    external_used: Any,
    typo_rescue_applied: Any,
    rerank_top1_flip: Any,
    results: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, Any]:
    exact_count = _bucket_count(retrieval_steps, "exact")
    lemma_count = _bucket_count(retrieval_steps, "lemma")
    semantic_count = _bucket_count(retrieval_steps, "semantic")
    top_source_types = summarize_top_source_types(results)
    compact_query = _compact_query(query)
    trace = {
        "version": "search_trace_v1",
        "endpoint": str(endpoint or "unknown"),
        "query": compact_query,
        "intent": str(intent or "").strip().upper() or "UNKNOWN",
        "retrieval_mode": str(retrieval_mode or "").strip() or "unknown",
        "selected_buckets": [str(bucket) for bucket in (selected_buckets or []) if str(bucket).strip()],
        "retrieval_counts": {
            "exact": exact_count,
            "lemma": lemma_count,
            "semantic": semantic_count,
        },
        "graph_used": _bool_value(graph_used),
        "external_used": _bool_value(external_used),
        "typo_rescue_applied": _bool_value(typo_rescue_applied),
        "rerank_top1_flip": _bool_value(rerank_top1_flip),
        "top_source_types": top_source_types,
    }
    line = (
        f"endpoint={trace['endpoint']} "
        f"query=\"{compact_query}\" "
        f"intent={trace['intent']} "
        f"retrieval={trace['retrieval_mode']} "
        f"buckets={','.join(trace['selected_buckets']) or 'none'} "
        f"counts=exact:{exact_count}|lemma:{lemma_count}|semantic:{semantic_count} "
        f"graph={int(trace['graph_used'])} "
        f"external={int(trace['external_used'])} "
        f"typo={int(trace['typo_rescue_applied'])} "
        f"rerank_flip={int(trace['rerank_top1_flip'])} "
        f"top3={','.join(top_source_types) or 'none'}"
    )
    return {
        "diagnostic_trace_v1": trace,
        "diagnostic_trace_line": line,
    }


def classify_search_failure_planes(
    metadata: Optional[Dict[str, Any]],
    *,
    answer: Optional[str] = None,
    sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    meta = metadata or {}
    source_count = len(list(sources or []))
    vector_count = _int_value(meta.get("vector_candidates_count"))
    graph_count = _int_value(meta.get("graph_candidates_count"))
    external_count = (
        _int_value(meta.get("external_graph_candidates_count"))
        + _int_value(meta.get("islamic_external_candidates_count"))
    )
    retrieval_supply = vector_count + graph_count + external_count

    if source_count == 0 and retrieval_supply == 0:
        retrieval_state = "no_evidence"
    elif source_count == 0 and retrieval_supply > 0:
        retrieval_state = "filtered_or_pruned"
    elif source_count <= 2 and retrieval_supply <= 2:
        retrieval_state = "sparse_evidence"
    else:
        retrieval_state = "evidence_ready"

    if answer is None:
        generation_state = "not_applicable"
    else:
        status = str(meta.get("status") or "").strip().lower()
        answer_text = str(answer or "").strip()
        if status in {"error", "failed"} or meta.get("error"):
            generation_state = "generation_error"
        elif answer_text in _TRACE_EMPTY_ANSWER_MARKERS:
            generation_state = "empty_answer"
        elif len(answer_text) < 120 and source_count >= 2:
            generation_state = "underfilled_answer"
        else:
            generation_state = "answer_ready"

    retrieval_failed = retrieval_state in {"no_evidence", "filtered_or_pruned", "sparse_evidence"}
    generation_failed = generation_state in {"generation_error", "empty_answer", "underfilled_answer"}
    if retrieval_failed and generation_failed:
        failure_plane = "mixed"
    elif retrieval_failed:
        failure_plane = "retrieval"
    elif generation_failed:
        failure_plane = "generation"
    else:
        failure_plane = "none"

    return {
        "retrieval_failure_plane": retrieval_state,
        "generation_failure_plane": generation_state,
        "failure_plane": failure_plane,
    }


def build_operational_plane_signals(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    meta = metadata or {}
    freshness_state = str(meta.get("index_freshness_state") or "").strip().lower()
    if freshness_state in {"fully_ready", "graph_ready", "vector_ready"}:
        freshness_plane = "ready"
    elif freshness_state == "not_ready":
        freshness_plane = "not_ready"
    else:
        freshness_plane = "not_checked"

    failure_plane = str(meta.get("failure_plane") or "none").strip().lower() or "none"
    search_status = str(meta.get("status") or "").strip().lower()
    quality_plane = "needs_attention" if failure_plane != "none" or search_status in {"partial", "error", "failed"} else "healthy"
    return {
        "freshness_plane": freshness_plane,
        "search_quality_plane": quality_plane,
        "operational_plane_summary": {
            "freshness_plane": freshness_plane,
            "quality_plane": quality_plane,
            "index_freshness_state": meta.get("index_freshness_state"),
            "failure_plane": failure_plane,
        },
    }


def enrich_search_metadata(
    metadata: Optional[Dict[str, Any]],
    *,
    endpoint: str,
    query: Any,
    intent: Any,
    results: Optional[Iterable[Dict[str, Any]]],
    answer: Optional[str] = None,
    sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = dict(metadata or {})
    trace_bundle = build_search_diagnostic_trace(
        endpoint=endpoint,
        query=query,
        intent=intent,
        retrieval_mode=meta.get("retrieval_mode"),
        selected_buckets=meta.get("selected_buckets"),
        retrieval_steps=meta.get("retrieval_steps"),
        graph_used=(
            _bool_value(meta.get("graph_bridge_used"))
            or _int_value(meta.get("graph_candidates_count")) > 0
        ),
        external_used=(
            _bool_value(meta.get("external_kb_used"))
            or _bool_value(meta.get("islamic_external_used"))
            or _int_value(meta.get("external_graph_candidates_count")) > 0
            or _int_value(meta.get("islamic_external_candidates_count")) > 0
        ),
        typo_rescue_applied=meta.get("typo_rescue_applied"),
        rerank_top1_flip=meta.get("rerank_top1_changed"),
        results=results if results is not None else sources,
    )
    meta.update(trace_bundle)
    meta.update(classify_search_failure_planes(meta, answer=answer, sources=sources if sources is not None else results))
    meta.update(build_operational_plane_signals(meta))
    return meta


def _read_search_log_strategy_details_json(cursor, search_log_id: int) -> Dict[str, Any]:
    cursor.execute(
        """
        SELECT STRATEGY_DETAILS
        FROM TOMEHUB_SEARCH_LOGS
        WHERE ID = :p_id
        """,
        {"p_id": search_log_id},
    )
    row = cursor.fetchone()
    if not row:
        return {}

    raw = row[0]
    try:
        if raw is None:
            return {}
        if isinstance(raw, str):
            parsed = json.loads(raw or "{}")
            return parsed if isinstance(parsed, dict) else {}
        parsed = json.loads(safe_read_clob(raw) or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception as clob_err:
        if "ORA-22848" not in str(clob_err):
            raise

        chunks: List[str] = []
        step = 32767
        offset = 1
        while offset <= 1024 * 1024:
            cursor.execute(
                """
                SELECT DBMS_LOB.SUBSTR(STRATEGY_DETAILS, :p_len, :p_off)
                FROM TOMEHUB_SEARCH_LOGS
                WHERE ID = :p_id
                """,
                {"p_len": step, "p_off": offset, "p_id": search_log_id},
            )
            part_row = cursor.fetchone()
            if not part_row or part_row[0] is None:
                break
            part = part_row[0]
            chunks.append(part if isinstance(part, str) else safe_read_clob(part))
            offset += step

        parsed = json.loads("".join(chunks) or "{}")
        return parsed if isinstance(parsed, dict) else {}


def append_search_log_diagnostics(search_log_id: Optional[int], diagnostics: Dict[str, Any]) -> None:
    if not search_log_id:
        return
    if not bool(getattr(settings, "SEARCH_LOG_DIAGNOSTICS_PERSIST_ENABLED", False)):
        return
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                payload: Dict[str, Any] = {}
                try:
                    payload = _read_search_log_strategy_details_json(cursor, int(search_log_id))
                except Exception as col_err:
                    if "ORA-00904" in str(col_err):
                        return
                    payload = {}
                payload.update(diagnostics or {})
                cursor.execute(
                    """
                    UPDATE TOMEHUB_SEARCH_LOGS
                    SET STRATEGY_DETAILS = :p_payload
                    WHERE ID = :p_id
                    """,
                    {
                        "p_payload": json.dumps(payload, ensure_ascii=False),
                        "p_id": search_log_id,
                    },
                )
            conn.commit()
    except Exception as exc:
        logger.warning("Failed to append search log diagnostics id=%s: %s", search_log_id, exc)
