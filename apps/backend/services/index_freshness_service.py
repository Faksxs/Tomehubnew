import threading
import time
from typing import Any, Dict, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.graph_service import extract_concepts_and_relations, save_to_graph
from services.external_kb_service import get_external_meta
from services.monitoring import (
    GRAPH_ENRICH_JOBS_TOTAL,
    GRAPH_ENRICH_CHUNKS_TOTAL,
    GRAPH_ENRICH_DURATION_SECONDS,
)
from utils.logger import get_logger

logger = get_logger("index_freshness_service")


def get_index_freshness_state(book_id: Optional[str], firebase_uid: Optional[str]) -> Dict[str, Any]:
    """
    Computes vector/graph readiness for a given book and user.
    State values:
      - not_ready
      - vector_ready
      - graph_ready
      - fully_ready
    """
    if not book_id or not firebase_uid:
        return {
            "index_freshness_state": "not_ready",
            "vector_ready": False,
            "graph_ready": False,
            "fully_ready": False,
            "total_chunks": 0,
            "embedded_chunks": 0,
            "graph_linked_chunks": 0,
            "vector_coverage_ratio": 0.0,
            "graph_coverage_ratio": 0.0,
            "wikidata_ready": False,
            "openalex_ready": False,
            "dbpedia_ready": False,
            "orkg_ready": False,
            "academic_scope": False,
            "checked_at": int(time.time() * 1000),
        }

    total_chunks = 0
    embedded_chunks = 0
    graph_linked_chunks = 0

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_chunks,
                        SUM(CASE WHEN VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END) as embedded_chunks
                    FROM TOMEHUB_CONTENT_V2
                    WHERE ITEM_ID = :p_bid
                      AND FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row = cursor.fetchone()
                if row:
                    total_chunks = int(row[0] or 0)
                    embedded_chunks = int(row[1] or 0)

                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT cc.CONTENT_ID)
                    FROM TOMEHUB_CONCEPT_CHUNKS cc
                    JOIN TOMEHUB_CONTENT_V2 c ON c.ID = cc.CONTENT_ID
                    WHERE c.ITEM_ID = :p_bid
                      AND c.FIREBASE_UID = :p_uid
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid},
                )
                row2 = cursor.fetchone()
                if row2:
                    graph_linked_chunks = int(row2[0] or 0)
    except Exception as e:
        logger.error(
            "Failed to compute index freshness",
            extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)},
        )

    vector_ready = embedded_chunks > 0
    graph_ready = graph_linked_chunks > 0
    fully_ready = vector_ready and graph_ready

    if fully_ready:
        freshness_state = "fully_ready"
    elif vector_ready:
        freshness_state = "vector_ready"
    elif graph_ready:
        freshness_state = "graph_ready"
    else:
        freshness_state = "not_ready"

    vector_coverage_ratio = (float(embedded_chunks) / float(total_chunks)) if total_chunks > 0 else 0.0
    graph_coverage_ratio = (float(graph_linked_chunks) / float(total_chunks)) if total_chunks > 0 else 0.0
    external_meta = get_external_meta(book_id, firebase_uid)
    academic_scope = bool(external_meta.get("academic_scope"))
    wikidata_ready = bool(
        external_meta.get("wikidata_qid")
        or str(external_meta.get("wikidata_status") or "").upper() == "OK"
    )
    openalex_ready = bool(
        not academic_scope
        or external_meta.get("openalex_id")
        or str(external_meta.get("openalex_status") or "").upper() in {"OK", "SKIPPED_NON_ACADEMIC", "SKIPPED_BY_MODE"}
    )
    dbpedia_ready = bool(
        external_meta.get("dbpedia_uri")
        or str(external_meta.get("dbpedia_status") or "").upper() in {"OK", "SKIPPED_BY_MODE", "NO_MATCH"}
    )
    orkg_ready = bool(
        not academic_scope
        or external_meta.get("orkg_id")
        or str(external_meta.get("orkg_status") or "").upper() in {"OK", "SKIPPED_NON_ACADEMIC", "SKIPPED_BY_MODE", "NO_MATCH"}
    )

    return {
        "index_freshness_state": freshness_state,
        "vector_ready": vector_ready,
        "graph_ready": graph_ready,
        "fully_ready": fully_ready,
        "total_chunks": total_chunks,
        "embedded_chunks": embedded_chunks,
        "graph_linked_chunks": graph_linked_chunks,
        "vector_coverage_ratio": round(vector_coverage_ratio, 4),
        "graph_coverage_ratio": round(graph_coverage_ratio, 4),
        "wikidata_ready": wikidata_ready,
        "openalex_ready": openalex_ready,
        "dbpedia_ready": dbpedia_ready,
        "orkg_ready": orkg_ready,
        "academic_scope": academic_scope,
        "checked_at": int(time.time() * 1000),
    }


def enrich_graph_for_book(
    firebase_uid: str,
    book_id: str,
    max_items: Optional[int] = None,
    timeout_sec: Optional[int] = None,
    reason: str = "manual",
) -> Dict[str, Any]:
    """
    Best-effort graph enrichment for a specific book.
    Processes only chunks that are not yet linked in TOMEHUB_CONCEPT_CHUNKS.
    """
    max_items = int(max_items or settings.GRAPH_ENRICH_MAX_ITEMS)
    timeout_sec = int(timeout_sec or settings.GRAPH_ENRICH_TIMEOUT_SEC)
    start_ts = time.time()

    result = {
        "book_id": book_id,
        "firebase_uid": firebase_uid,
        "requested_max_items": max_items,
        "timeout_sec": timeout_sec,
        "eligible_chunks": 0,
        "attempted_chunks": 0,
        "linked_chunks": 0,
        "skipped_short_chunks": 0,
        "empty_concepts": 0,
        "errored_chunks": 0,
        "timeout_reached": False,
    }

    if not book_id or not firebase_uid:
        result["error"] = "book_id and firebase_uid are required"
        return result

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT c.ID, c.CONTENT_CHUNK
                    FROM TOMEHUB_CONTENT_V2 c
                    WHERE c.ITEM_ID = :p_bid
                      AND c.FIREBASE_UID = :p_uid
                      AND c.CONTENT_CHUNK IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1
                        FROM TOMEHUB_CONCEPT_CHUNKS cc
                        WHERE cc.CONTENT_ID = c.ID
                      )
                    ORDER BY c.ID
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {"p_bid": book_id, "p_uid": firebase_uid, "p_limit": max_items},
                )
                rows = cursor.fetchall()
    except Exception as e:
        result["error"] = str(e)
        logger.error(
            "Graph enrichment prefetch failed",
            extra={"book_id": book_id, "uid": firebase_uid, "error": str(e)},
        )
        return result

    result["eligible_chunks"] = len(rows)

    for row in rows:
        if time.time() - start_ts >= timeout_sec:
            result["timeout_reached"] = True
            break

        content_id = int(row[0])
        content_text = safe_read_clob(row[1]) if row[1] is not None else ""

        if not content_text or len(content_text.strip()) < 50:
            result["skipped_short_chunks"] += 1
            continue

        result["attempted_chunks"] += 1
        try:
            concepts, relations = extract_concepts_and_relations(content_text)
            if not concepts:
                result["empty_concepts"] += 1
                continue
            saved = save_to_graph(content_id, concepts, relations)
            if saved:
                result["linked_chunks"] += 1
            else:
                result["errored_chunks"] += 1
        except Exception as e:
            result["errored_chunks"] += 1
            logger.error(
                "Graph enrichment chunk failed",
                extra={"book_id": book_id, "uid": firebase_uid, "content_id": content_id, "error": str(e)},
            )

    duration_ms = int((time.time() - start_ts) * 1000)
    result["duration_ms"] = duration_ms
    result["post_freshness"] = get_index_freshness_state(book_id, firebase_uid)

    status = "success"
    if result.get("error"):
        status = "error"
    elif result.get("timeout_reached"):
        status = "timeout"

    try:
        GRAPH_ENRICH_JOBS_TOTAL.labels(status=status, reason=reason).inc()
        GRAPH_ENRICH_DURATION_SECONDS.labels(status=status).observe(duration_ms / 1000.0)
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="eligible").inc(result.get("eligible_chunks", 0))
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="attempted").inc(result.get("attempted_chunks", 0))
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="linked").inc(result.get("linked_chunks", 0))
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="skipped_short").inc(result.get("skipped_short_chunks", 0))
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="empty_concepts").inc(result.get("empty_concepts", 0))
        GRAPH_ENRICH_CHUNKS_TOTAL.labels(outcome="errored").inc(result.get("errored_chunks", 0))
    except Exception:
        # Metrics should never break the enrichment flow.
        pass
    return result


def maybe_trigger_graph_enrichment_async(
    firebase_uid: Optional[str],
    book_id: Optional[str],
    reason: str = "unspecified",
) -> bool:
    """
    Fire-and-forget graph enrichment trigger.
    Returns True only when worker thread is started.
    """
    if not settings.GRAPH_ENRICH_ON_INGEST:
        return False
    if not firebase_uid or not book_id:
        return False

    current = get_index_freshness_state(book_id, firebase_uid)
    if current.get("fully_ready"):
        return False

    def _runner():
        try:
            out = enrich_graph_for_book(
                firebase_uid=firebase_uid,
                book_id=book_id,
                reason=reason,
            )
            logger.info(
                "Graph enrichment worker finished",
                extra={
                    "reason": reason,
                    "book_id": book_id,
                    "uid": firebase_uid,
                    "linked_chunks": out.get("linked_chunks"),
                    "eligible_chunks": out.get("eligible_chunks"),
                    "duration_ms": out.get("duration_ms"),
                    "post_state": (out.get("post_freshness") or {}).get("index_freshness_state"),
                },
            )
        except Exception as e:
            logger.error(
                "Graph enrichment worker failed",
                extra={"reason": reason, "book_id": book_id, "uid": firebase_uid, "error": str(e)},
            )

    th = threading.Thread(target=_runner, daemon=True, name=f"graph-enrich-{book_id[:10]}")
    th.start()
    return True
