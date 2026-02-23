from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.db_manager import DatabaseManager, safe_read_clob

logger = logging.getLogger("change_event_service")


def _to_utc_dt_from_ms(ts_ms: int) -> datetime:
    safe_ms = max(int(ts_ms or 0), 0)
    return datetime.fromtimestamp(safe_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def emit_change_event(
    *,
    firebase_uid: str,
    item_id: Optional[str],
    entity_type: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    source_service: Optional[str] = None,
    status: str = "PENDING",
) -> Optional[int]:
    """
    Best-effort outbox insert for Phase 4 realtime polling.
    Returns event_id when available, otherwise None.
    """
    if not firebase_uid or not entity_type or not event_type:
        return None

    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                out_id = cursor.var(int)
                cursor.execute(
                    """
                    INSERT INTO TOMEHUB_CHANGE_EVENTS
                    (
                        FIREBASE_UID, ITEM_ID, ENTITY_TYPE, EVENT_TYPE, STATUS,
                        PAYLOAD_JSON, SOURCE_SERVICE
                    )
                    VALUES
                    (
                        :p_uid, :p_item, :p_entity, :p_event, :p_status,
                        :p_payload, :p_source
                    )
                    RETURNING EVENT_ID INTO :p_out_id
                    """,
                    {
                        "p_uid": str(firebase_uid).strip(),
                        "p_item": (str(item_id).strip() if item_id else None),
                        "p_entity": str(entity_type).strip().upper(),
                        "p_event": str(event_type).strip(),
                        "p_status": str(status or "PENDING").strip().upper(),
                        "p_payload": json.dumps(payload or {}, ensure_ascii=False),
                        "p_source": (str(source_service).strip() if source_service else None),
                        "p_out_id": out_id,
                    },
                )
                conn.commit()
                raw_id = out_id.getvalue()
                if isinstance(raw_id, list):
                    raw_id = raw_id[0] if raw_id else None
                return int(raw_id) if raw_id is not None else None
    except Exception as e:
        logger.warning("emit_change_event failed (non-critical): %s", e)
        return None


def fetch_change_events_since(
    *,
    firebase_uid: str,
    since_ms: int = 0,
    limit: int = 100,
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Read recent outbox events for polling.
    Returns (changes, last_event_id).
    """
    if not firebase_uid:
        return ([], None)

    safe_limit = max(1, min(int(limit or 100), 300))
    cutoff_dt = _to_utc_dt_from_ms(since_ms)
    rows: List[Any] = []

    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EVENT_ID, ITEM_ID, ENTITY_TYPE, EVENT_TYPE, PAYLOAD_JSON, CREATED_AT
                    FROM TOMEHUB_CHANGE_EVENTS
                    WHERE FIREBASE_UID = :p_uid
                      AND CREATED_AT > :p_cutoff
                    ORDER BY EVENT_ID DESC
                    FETCH FIRST :p_limit ROWS ONLY
                    """,
                    {
                        "p_uid": str(firebase_uid).strip(),
                        "p_cutoff": cutoff_dt,
                        "p_limit": safe_limit,
                    },
                )
                rows = cursor.fetchall() or []
    except Exception as e:
        logger.warning("fetch_change_events_since failed (non-critical): %s", e)
        return ([], None)

    changes: List[Dict[str, Any]] = []
    last_event_id: Optional[int] = None
    for row in rows:
        event_id = int(row[0]) if row and row[0] is not None else None
        item_id = str(row[1] or "") if row else ""
        entity_type = str(row[2] or "") if row else ""
        event_type = str(row[3] or "") if row else ""
        payload_raw = safe_read_clob(row[4]) if row and len(row) > 4 else None
        created_at = row[5] if row and len(row) > 5 else None
        created_ms = int(created_at.timestamp() * 1000) if created_at else int(datetime.now().timestamp() * 1000)
        payload: Dict[str, Any] = {}
        if payload_raw:
            try:
                parsed = json.loads(payload_raw)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}
        changes.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "entity_type": entity_type,
                "book_id": item_id,
                "item_id": item_id,
                "updated_at_ms": created_ms,
                "payload": payload,
            }
        )
        if event_id is not None and (last_event_id is None or event_id > last_event_id):
            last_event_id = event_id

    return (changes, last_event_id)
