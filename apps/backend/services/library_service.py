from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

import oracledb

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.ingestion_service import purge_item_content
from utils.logger import get_logger

logger = get_logger("library_service")

_TABLE_COLUMNS_CACHE: dict[str, set[str]] = {}

_ITEM_TYPES = {"BOOK", "ARTICLE", "WEBSITE", "PERSONAL_NOTE"}
_CONTENT_TYPE_CANDIDATES = ("CONTENT_TYPE", "SOURCE_TYPE")
_ITEM_ID_CANDIDATES = ("ITEM_ID", "BOOK_ID")
_LIBRARY_TABLE = "TOMEHUB_LIBRARY_ITEMS"


def _columns_for(table_name: str, *, force_refresh: bool = False) -> set[str]:
    key = table_name.upper()
    if key in _TABLE_COLUMNS_CACHE and not force_refresh:
        return _TABLE_COLUMNS_CACHE[key]
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COLUMN_NAME
                FROM USER_TAB_COLUMNS
                WHERE TABLE_NAME = :p_table
                """,
                {"p_table": key},
            )
            cols = {str(r[0]).upper() for r in cur.fetchall()}
    _TABLE_COLUMNS_CACHE[key] = cols
    return cols


def _table_exists(table_name: str) -> bool:
    return bool(_columns_for(table_name))


def _pick_existing_table(candidates: Iterable[str]) -> Optional[str]:
    for name in candidates:
        if _table_exists(name):
            return name
    return None


def _library_cols() -> set[str]:
    return _columns_for(_LIBRARY_TABLE)


def _lib_select_expr(col: str, alias: str | None = None) -> str:
    alias = alias or col
    if col.upper() in _library_cols():
        return f"li.{col} AS {alias}"
    return f"NULL AS {alias}"


def resolve_active_content_table() -> Optional[str]:
    # Prefer V2 if present.
    return _pick_existing_table(("TOMEHUB_CONTENT_V2", "TOMEHUB_CONTENT"))


def _content_table_shape(table_name: str) -> dict[str, Optional[str]]:
    cols = _columns_for(table_name)
    item_col = next((c for c in _ITEM_ID_CANDIDATES if c in cols), None)
    type_col = next((c for c in _CONTENT_TYPE_CANDIDATES if c in cols), None)
    title_col = "TITLE" if "TITLE" in cols else None
    content_col = "CONTENT_CHUNK" if "CONTENT_CHUNK" in cols else None
    comment_col = "COMMENT" if "COMMENT" in cols else None
    # COMMENT is quoted in some schemas but USER_TAB_COLUMNS returns without quotes.
    tags_col = "TAGS" if "TAGS" in cols else None
    page_col = "PAGE_NUMBER" if "PAGE_NUMBER" in cols else None
    chunk_idx_col = "CHUNK_INDEX" if "CHUNK_INDEX" in cols else None
    id_col = "ID" if "ID" in cols else None
    return {
        "item_col": item_col,
        "type_col": type_col,
        "title_col": title_col,
        "content_col": content_col,
        "comment_col": comment_col,
        "tags_col": tags_col,
        "page_col": page_col,
        "chunk_idx_col": chunk_idx_col,
        "id_col": id_col,
    }


def _ts_to_ms(value: Any) -> int:
    if value is None:
        return int(datetime.utcnow().timestamp() * 1000)
    if isinstance(value, (int, float)):
        iv = int(value)
        return iv if iv > 0 else int(datetime.utcnow().timestamp() * 1000)
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    try:
        text = str(value)
        dt = datetime.fromisoformat(text)
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(datetime.utcnow().timestamp() * 1000)


def _safe_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = safe_read_clob(value) if not isinstance(value, str) else value
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            out: list[str] = []
            for item in data:
                text = str(item or "").strip()
                if text:
                    out.append(text)
            return out
    except Exception:
        pass
    return []


def _to_int_or_none(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _decode_cursor(cursor: Optional[str]) -> Optional[tuple[int, str]]:
    if not cursor:
        return None
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        data = json.loads(payload)
        ts = int(data.get("updatedAtMs"))
        item_id = str(data.get("itemId") or "").strip()
        if not item_id:
            return None
        return ts, item_id
    except Exception:
        return None


def _encode_cursor(updated_at_ms: int, item_id: str) -> str:
    payload = json.dumps({"updatedAtMs": int(updated_at_ms), "itemId": item_id}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def ensure_personal_note_folders_table() -> None:
    if _table_exists("TOMEHUB_PERSONAL_NOTE_FOLDERS"):
        return
    ddl = """
    CREATE TABLE TOMEHUB_PERSONAL_NOTE_FOLDERS (
        ID VARCHAR2(255) NOT NULL,
        FIREBASE_UID VARCHAR2(255) NOT NULL,
        CATEGORY VARCHAR2(50) NOT NULL,
        NAME VARCHAR2(255) NOT NULL,
        DISPLAY_ORDER NUMBER DEFAULT 0 NOT NULL,
        CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
        IS_DELETED NUMBER(1) DEFAULT 0 NOT NULL,
        DELETED_AT TIMESTAMP NULL,
        CONSTRAINT PK_TH_PNF PRIMARY KEY (ID),
        CONSTRAINT UQ_TH_PNF_UID_ID UNIQUE (FIREBASE_UID, ID),
        CONSTRAINT CHK_TH_PNF_CATEGORY CHECK (CATEGORY IN ('PRIVATE','DAILY','IDEAS')),
        CONSTRAINT CHK_TH_PNF_DELETED CHECK (IS_DELETED IN (0,1))
    )
    """
    idx_sql = [
        "CREATE INDEX IDX_TH_PNF_UID_CAT_ORD ON TOMEHUB_PERSONAL_NOTE_FOLDERS(FIREBASE_UID, CATEGORY, DISPLAY_ORDER)",
        "CREATE INDEX IDX_TH_PNF_UID_UPD ON TOMEHUB_PERSONAL_NOTE_FOLDERS(FIREBASE_UID, UPDATED_AT)",
    ]
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(ddl)
            except Exception as e:
                msg = str(e).lower()
                if "name is already used" not in msg and "ora-00955" not in msg:
                    raise
            for sql in idx_sql:
                try:
                    cur.execute(sql)
                except Exception as e:
                    msg = str(e).lower()
                    if "already" in msg or "ora-00955" in msg:
                        continue
                    raise
        conn.commit()
    _TABLE_COLUMNS_CACHE.pop("TOMEHUB_PERSONAL_NOTE_FOLDERS", None)


def _canonical_item_type(value: Optional[str]) -> str:
    st = str(value or "BOOK").strip().upper()
    if st == "PDF":
        return "BOOK"
    if st in _ITEM_TYPES:
        return st
    return "BOOK"


def list_library_items(
    firebase_uid: str,
    *,
    limit: int = 1000,
    cursor: Optional[str] = None,
    types: Optional[list[str]] = None,
) -> dict:
    limit = max(1, min(int(limit or 1000), 2000))
    decoded_cursor = _decode_cursor(cursor)
    item_types = [_canonical_item_type(t) for t in (types or []) if str(t or "").strip()]
    item_types = [t for t in item_types if t in _ITEM_TYPES]

    rows: list[dict[str, Any]] = []
    next_cursor: Optional[str] = None

    where_parts = ["li.FIREBASE_UID = :p_uid", "NVL(li.IS_DELETED, 0) = 0"]
    binds: dict[str, Any] = {"p_uid": firebase_uid, "p_limit": limit + 1}

    if item_types:
        type_placeholders = []
        for i, t in enumerate(item_types):
            k = f"p_type_{i}"
            binds[k] = t
            type_placeholders.append(f":{k}")
        where_parts.append(f"li.ITEM_TYPE IN ({', '.join(type_placeholders)})")

    if decoded_cursor:
        ts_ms, item_id = decoded_cursor
        cursor_dt = datetime.utcfromtimestamp(ts_ms / 1000.0)
        binds["p_cursor_ts"] = cursor_dt
        binds["p_cursor_item"] = item_id
        where_parts.append(
            "(li.UPDATED_AT < :p_cursor_ts OR (li.UPDATED_AT = :p_cursor_ts AND li.ITEM_ID < :p_cursor_item))"
        )

    sql = f"""
        SELECT
            li.ITEM_ID,
            li.ITEM_TYPE,
            li.TITLE,
            li.AUTHOR,
            {_lib_select_expr('TRANSLATOR')},
            {_lib_select_expr('PUBLISHER')},
            {_lib_select_expr('PUBLICATION_YEAR')},
            {_lib_select_expr('ISBN')},
            {_lib_select_expr('SOURCE_URL')},
            {_lib_select_expr('INVENTORY_STATUS')},
            {_lib_select_expr('READING_STATUS')},
            {_lib_select_expr('TAGS_JSON')},
            {_lib_select_expr('GENERAL_NOTES')},
            {_lib_select_expr('CONTENT_LANGUAGE_MODE')},
            {_lib_select_expr('CONTENT_LANGUAGE_RESOLVED')},
            {_lib_select_expr('SOURCE_LANGUAGE_HINT')},
            {_lib_select_expr('LANGUAGE_DECISION_REASON')},
            {_lib_select_expr('LANGUAGE_DECISION_CONFIDENCE')},
            {_lib_select_expr('PERSONAL_NOTE_CATEGORY')},
            {_lib_select_expr('PERSONAL_FOLDER_ID')},
            {_lib_select_expr('FOLDER_PATH')},
            {_lib_select_expr('COVER_URL')},
            {_lib_select_expr('CREATED_AT')},
            {_lib_select_expr('IS_FAVORITE')},
            {_lib_select_expr('PAGE_COUNT')},
            {_lib_select_expr('UPDATED_AT')}
        FROM {_LIBRARY_TABLE} li
        WHERE {' AND '.join(where_parts)}
        ORDER BY li.UPDATED_AT DESC, li.ITEM_ID DESC
        FETCH FIRST :p_limit ROWS ONLY
    """

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, binds)
            fetched = cur.fetchall()

            has_more = len(fetched) > limit
            visible = fetched[:limit]

            item_ids: list[str] = []
            for r in visible:
                item_id = str(r[0])
                updated_ms = _ts_to_ms(r[25] or r[22])
                item = {
                    "id": item_id,
                    "type": _canonical_item_type(r[1]),
                    "title": str(r[2] or "").strip() or "Untitled",
                    "author": str(r[3] or "").strip() or "Unknown Author",
                    "translator": str(r[4] or "").strip() or None,
                    "publisher": str(r[5] or "").strip() or None,
                    "publicationYear": str(r[6]) if r[6] is not None else None,
                    "isbn": str(r[7] or "").strip() or None,
                    "url": str(r[8] or "").strip() or None,
                    "status": str(r[9] or "On Shelf"),
                    "readingStatus": str(r[10] or "To Read"),
                    "tags": _safe_json_list(r[11]),
                    "generalNotes": safe_read_clob(r[12]) if r[12] is not None else "",
                    "contentLanguageMode": str(r[13] or "AUTO"),
                    "contentLanguageResolved": str(r[14]).lower() if r[14] else None,
                    "sourceLanguageHint": str(r[15]).lower() if r[15] else None,
                    "languageDecisionReason": str(r[16] or "").strip() or None,
                    "languageDecisionConfidence": float(r[17]) if r[17] is not None else None,
                    "personalNoteCategory": str(r[18] or "").strip() or None,
                    "personalFolderId": str(r[19] or "").strip() or None,
                    "folderPath": safe_read_clob(r[20]) if r[20] is not None else None,
                    "coverUrl": str(r[21] or "").strip() or None,
                    "addedAt": _ts_to_ms(r[22]),
                    "isFavorite": bool(int(r[23])) if r[23] is not None else False,
                    "pageCount": int(r[24]) if r[24] is not None else None,
                    "highlights": [],
                    "isIngested": False,
                    "_updatedAtMs": updated_ms,
                }
                rows.append(item)
                item_ids.append(item_id)

            # Ingestion status (best-effort)
            if item_ids and _table_exists("TOMEHUB_INGESTED_FILES"):
                phs = []
                b2 = {"p_uid": firebase_uid}
                for i, iid in enumerate(item_ids):
                    k = f"p_i_{i}"
                    phs.append(f":{k}")
                    b2[k] = iid
                try:
                    cur.execute(
                        f"""
                        SELECT BOOK_ID, STATUS
                        FROM TOMEHUB_INGESTED_FILES
                        WHERE FIREBASE_UID = :p_uid
                          AND BOOK_ID IN ({', '.join(phs)})
                        """,
                        b2,
                    )
                    ing_map = {str(r[0]): str(r[1] or "").upper() for r in cur.fetchall()}
                    for item in rows:
                        item["isIngested"] = ing_map.get(item["id"]) == "COMPLETED"
                except Exception as e:
                    logger.warning(f"list_library_items ingestion-status join failed: {e}")

            # Highlights / insights from active content table (best-effort)
            content_table = resolve_active_content_table()
            if item_ids and content_table:
                shape = _content_table_shape(content_table)
                item_col = shape["item_col"]
                type_col = shape["type_col"]
                if item_col and type_col and shape["content_col"]:
                    phs = []
                    b3 = {"p_uid": firebase_uid}
                    for i, iid in enumerate(item_ids):
                        k = f"p_h_{i}"
                        phs.append(f":{k}")
                        b3[k] = iid

                    # Build comment column safely
                    comment_expr = f'"{shape["comment_col"]}"' if shape["comment_col"] == "COMMENT" else (shape["comment_col"] or "NULL")
                    page_expr = shape["page_col"] or "NULL"
                    idx_expr = shape["chunk_idx_col"] or "NULL"
                    id_expr = shape["id_col"] or "NULL"
                    tags_expr = shape["tags_col"] or "NULL"
                    sql_h = f"""
                        SELECT
                            {item_col} AS item_id,
                            {id_expr} AS row_id,
                            {type_col} AS src_type,
                            {shape['content_col']} AS content_chunk,
                            {page_expr} AS page_number,
                            {idx_expr} AS chunk_index,
                            {comment_expr} AS comment_text,
                            {tags_expr} AS tags_json
                        FROM {content_table}
                        WHERE FIREBASE_UID = :p_uid
                          AND {item_col} IN ({', '.join(phs)})
                          AND UPPER({type_col}) IN ('HIGHLIGHT','INSIGHT','NOTES')
                        ORDER BY {item_col}, {page_expr if shape['page_col'] else '1'}, {idx_expr if shape['chunk_idx_col'] else '1'}
                    """
                    try:
                        cur.execute(sql_h, b3)
                        agg: dict[str, list[dict[str, Any]]] = {}
                        for hr in cur.fetchall():
                            iid = str(hr[0] or "").strip()
                            if not iid:
                                continue
                            src_type = str(hr[2] or "").upper()
                            h_type = "insight" if src_type in {"INSIGHT", "NOTES"} else "highlight"
                            text = safe_read_clob(hr[3]) if hr[3] is not None else ""
                            if not text:
                                continue
                            agg.setdefault(iid, []).append(
                                {
                                    "id": str(hr[1]) if hr[1] is not None else f"{iid}-{len(agg.get(iid, []))}",
                                    "text": text,
                                    "type": h_type,
                                    "pageNumber": int(hr[4]) if hr[4] is not None else None,
                                    "comment": safe_read_clob(hr[6]) if hr[6] is not None else None,
                                    "createdAt": None,
                                    "tags": _safe_json_list(hr[7]),
                                    "isFavorite": False,
                                }
                            )
                        for item in rows:
                            item["highlights"] = agg.get(item["id"], [])
                    except Exception as e:
                        logger.warning(f"list_library_items highlight query failed: {e}")

            if has_more and visible:
                last = rows[-1]
                next_cursor = _encode_cursor(int(last["_updatedAtMs"]), str(last["id"]))

    for item in rows:
        item.pop("_updatedAtMs", None)
    return {"items": rows, "next_cursor": next_cursor, "count": len(rows)}


def _clean_folder_payload(payload: dict[str, Any]) -> dict[str, Any]:
    category = str(payload.get("category") or "PRIVATE").strip().upper()
    if category not in {"PRIVATE", "DAILY", "IDEAS"}:
        category = "PRIVATE"
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("folder name required")
    order = payload.get("order", payload.get("display_order", 0))
    try:
        order = int(order)
    except Exception:
        order = 0
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    created_at = payload.get("createdAt", now_ms)
    updated_at = payload.get("updatedAt", now_ms)
    return {
        "id": str(payload.get("id") or "").strip(),
        "category": category,
        "name": name[:255],
        "order": order,
        "createdAt": int(created_at) if str(created_at).isdigit() else now_ms,
        "updatedAt": int(updated_at) if str(updated_at).isdigit() else now_ms,
    }


def list_personal_note_folders(firebase_uid: str) -> list[dict[str, Any]]:
    ensure_personal_note_folders_table()
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ID, CATEGORY, NAME, DISPLAY_ORDER, CREATED_AT, UPDATED_AT
                FROM TOMEHUB_PERSONAL_NOTE_FOLDERS
                WHERE FIREBASE_UID = :p_uid
                  AND NVL(IS_DELETED, 0) = 0
                ORDER BY CATEGORY, DISPLAY_ORDER, NAME
                """,
                {"p_uid": firebase_uid},
            )
            out = []
            for r in cur.fetchall():
                out.append(
                    {
                        "id": str(r[0]),
                        "category": str(r[1]),
                        "name": str(r[2]),
                        "order": int(r[3] or 0),
                        "createdAt": _ts_to_ms(r[4]),
                        "updatedAt": _ts_to_ms(r[5]),
                    }
                )
            return out


def upsert_personal_note_folder(firebase_uid: str, folder_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_personal_note_folders_table()
    clean = _clean_folder_payload({**payload, "id": folder_id})
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                MERGE INTO TOMEHUB_PERSONAL_NOTE_FOLDERS f
                USING (SELECT :p_id AS id, :p_uid AS firebase_uid FROM DUAL) src
                ON (f.ID = src.id AND f.FIREBASE_UID = src.firebase_uid)
                WHEN MATCHED THEN
                  UPDATE SET
                    CATEGORY = :p_category,
                    NAME = :p_name,
                    DISPLAY_ORDER = :p_order,
                    UPDATED_AT = CURRENT_TIMESTAMP,
                    IS_DELETED = 0,
                    DELETED_AT = NULL
                WHEN NOT MATCHED THEN
                  INSERT (ID, FIREBASE_UID, CATEGORY, NAME, DISPLAY_ORDER, CREATED_AT, UPDATED_AT, IS_DELETED)
                  VALUES (:p_id, :p_uid, :p_category, :p_name, :p_order, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0)
                """,
                {
                    "p_id": clean["id"],
                    "p_uid": firebase_uid,
                    "p_category": clean["category"],
                    "p_name": clean["name"],
                    "p_order": clean["order"],
                },
            )
        conn.commit()
    return clean


def patch_personal_note_folder(firebase_uid: str, folder_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_personal_note_folders_table()
    sets = ["UPDATED_AT = CURRENT_TIMESTAMP"]
    binds: dict[str, Any] = {"p_uid": firebase_uid, "p_id": folder_id}
    if "name" in patch:
        binds["p_name"] = str(patch.get("name") or "").strip()[:255]
        sets.append("NAME = :p_name")
    if "category" in patch:
        category = str(patch.get("category") or "PRIVATE").strip().upper()
        if category not in {"PRIVATE", "DAILY", "IDEAS"}:
            category = "PRIVATE"
        binds["p_category"] = category
        sets.append("CATEGORY = :p_category")
    if "order" in patch:
        try:
            binds["p_order"] = int(patch.get("order"))
            sets.append("DISPLAY_ORDER = :p_order")
        except Exception:
            pass
    if len(sets) == 1:
        return {"id": folder_id}
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE TOMEHUB_PERSONAL_NOTE_FOLDERS
                SET {', '.join(sets)}
                WHERE FIREBASE_UID = :p_uid
                  AND ID = :p_id
                  AND NVL(IS_DELETED,0) = 0
                """,
                binds,
            )
            if (cur.rowcount or 0) == 0:
                raise ValueError("folder not found")
        conn.commit()
    # Return full row for UI consistency.
    for row in list_personal_note_folders(firebase_uid):
        if row["id"] == folder_id:
            return row
    raise ValueError("folder not found")


def delete_personal_note_folder(firebase_uid: str, folder_id: str) -> dict:
    ensure_personal_note_folders_table()
    affected_notes = 0
    lib_cols = _library_cols()
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            if "PERSONAL_FOLDER_ID" in lib_cols and "ITEM_TYPE" in lib_cols and "FIREBASE_UID" in lib_cols:
                sets = ["PERSONAL_FOLDER_ID = NULL"]
                if "FOLDER_PATH" in lib_cols:
                    sets.append("FOLDER_PATH = NULL")
                if "UPDATED_AT" in lib_cols:
                    sets.append("UPDATED_AT = CURRENT_TIMESTAMP")
                cur.execute(
                    f"""
                    UPDATE {_LIBRARY_TABLE}
                    SET {', '.join(sets)}
                    WHERE FIREBASE_UID = :p_uid
                      AND ITEM_TYPE = 'PERSONAL_NOTE'
                      AND PERSONAL_FOLDER_ID = :p_id
                    """,
                    {"p_uid": firebase_uid, "p_id": folder_id},
                )
                affected_notes = cur.rowcount or 0
            cur.execute(
                """
                UPDATE TOMEHUB_PERSONAL_NOTE_FOLDERS
                SET IS_DELETED = 1,
                    DELETED_AT = CURRENT_TIMESTAMP,
                    UPDATED_AT = CURRENT_TIMESTAMP
                WHERE FIREBASE_UID = :p_uid
                  AND ID = :p_id
                  AND NVL(IS_DELETED,0) = 0
                """,
                {"p_uid": firebase_uid, "p_id": folder_id},
            )
            folder_deleted = cur.rowcount or 0
        conn.commit()
    return {"success": True, "folder_deleted": folder_deleted, "affected_notes": affected_notes}


def upsert_library_item(firebase_uid: str, item_id: str, payload: dict[str, Any]) -> dict:
    lib_cols = _library_cols()
    if not lib_cols:
        raise RuntimeError("TOMEHUB_LIBRARY_ITEMS table not found")

    item_type = _canonical_item_type(payload.get("type"))
    title = str(payload.get("title") or "Untitled").strip() or "Untitled"
    author = str(payload.get("author") or "Unknown Author").strip() or "Unknown Author"

    field_map: list[tuple[str, Any, str]] = [
        ("ITEM_TYPE", item_type, "scalar"),
        ("TITLE", title, "scalar"),
        ("AUTHOR", author, "scalar"),
        ("TRANSLATOR", payload.get("translator"), "scalar"),
        ("PUBLISHER", payload.get("publisher"), "scalar"),
        ("PUBLICATION_YEAR", _to_int_or_none(payload.get("publicationYear")), "scalar"),
        ("ISBN", payload.get("isbn"), "scalar"),
        ("SOURCE_URL", payload.get("url"), "scalar"),
        ("PAGE_COUNT", _to_int_or_none(payload.get("pageCount")), "scalar"),
        ("COVER_URL", payload.get("coverUrl"), "scalar"),
        ("INVENTORY_STATUS", payload.get("status"), "scalar"),
        ("READING_STATUS", payload.get("readingStatus"), "scalar"),
        ("IS_FAVORITE", 1 if bool(payload.get("isFavorite")) else 0, "scalar"),
        ("GENERAL_NOTES", payload.get("generalNotes"), "clob"),
        ("PERSONAL_NOTE_CATEGORY", payload.get("personalNoteCategory"), "scalar"),
        ("PERSONAL_FOLDER_ID", payload.get("personalFolderId"), "scalar"),
        ("FOLDER_PATH", payload.get("folderPath"), "clob"),
        ("CONTENT_LANGUAGE_MODE", payload.get("contentLanguageMode"), "scalar"),
        ("CONTENT_LANGUAGE_RESOLVED", payload.get("contentLanguageResolved"), "scalar"),
        ("SOURCE_LANGUAGE_HINT", payload.get("sourceLanguageHint"), "scalar"),
        ("LANGUAGE_DECISION_REASON", payload.get("languageDecisionReason"), "scalar"),
        ("LANGUAGE_DECISION_CONFIDENCE", payload.get("languageDecisionConfidence"), "scalar"),
        ("TAGS_JSON", json.dumps(payload.get("tags") or [], ensure_ascii=False), "clob"),
    ]

    binds: dict[str, Any] = {"p_id": item_id, "p_uid": firebase_uid}
    update_sets: list[str] = []
    insert_cols: list[str] = ["ITEM_ID", "FIREBASE_UID"]
    insert_vals: list[str] = [":p_id", ":p_uid"]

    for idx, (col, raw_value, kind) in enumerate(field_map):
        if col not in lib_cols:
            continue
        bind = f"p_f{idx}"
        binds[bind] = raw_value
        expr = f"TO_CLOB(:{bind})" if kind == "clob" else f":{bind}"
        update_sets.append(f"{col} = {expr}")
        insert_cols.append(col)
        insert_vals.append(expr)

    if "UPDATED_AT" in lib_cols:
        update_sets.append("UPDATED_AT = CURRENT_TIMESTAMP")
        insert_cols.append("UPDATED_AT")
        insert_vals.append("CURRENT_TIMESTAMP")
    if "CREATED_AT" in lib_cols:
        insert_cols.append("CREATED_AT")
        insert_vals.append("CURRENT_TIMESTAMP")
    if "IS_DELETED" in lib_cols:
        update_sets.append("IS_DELETED = 0")
        insert_cols.append("IS_DELETED")
        insert_vals.append("0")
    if "DELETED_AT" in lib_cols:
        update_sets.append("DELETED_AT = NULL")
        insert_cols.append("DELETED_AT")
        insert_vals.append("NULL")
    if "ROW_VERSION" in lib_cols:
        # Preserve existing increment semantics if available; otherwise seed on insert.
        update_sets.append("ROW_VERSION = NVL(ROW_VERSION, 0) + 1")
        insert_cols.append("ROW_VERSION")
        insert_vals.append("1")
    if not update_sets:
        update_sets.append("ITEM_ID = li.ITEM_ID")

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                MERGE INTO {_LIBRARY_TABLE} li
                USING (SELECT :p_id AS item_id, :p_uid AS firebase_uid FROM DUAL) src
                ON (li.ITEM_ID = src.item_id AND li.FIREBASE_UID = src.firebase_uid)
                WHEN MATCHED THEN
                  UPDATE SET {', '.join(update_sets)}
                WHEN NOT MATCHED THEN
                  INSERT ({', '.join(insert_cols)})
                  VALUES ({', '.join(insert_vals)})
                """,
                binds,
            )
        conn.commit()
    return {"success": True, "item_id": item_id}


def patch_library_item(firebase_uid: str, item_id: str, patch: dict[str, Any]) -> dict:
    lib_cols = _library_cols()
    allowlist_map = {
        "title": ("TITLE", "str"),
        "author": ("AUTHOR", "str"),
        "translator": ("TRANSLATOR", "str"),
        "publisher": ("PUBLISHER", "str"),
        "publicationYear": ("PUBLICATION_YEAR", "int"),
        "isbn": ("ISBN", "str"),
        "url": ("SOURCE_URL", "str"),
        "status": ("INVENTORY_STATUS", "str"),
        "readingStatus": ("READING_STATUS", "str"),
        "isFavorite": ("IS_FAVORITE", "bool"),
        "generalNotes": ("GENERAL_NOTES", "clob"),
        "contentLanguageMode": ("CONTENT_LANGUAGE_MODE", "str"),
        "contentLanguageResolved": ("CONTENT_LANGUAGE_RESOLVED", "str"),
        "sourceLanguageHint": ("SOURCE_LANGUAGE_HINT", "str"),
        "languageDecisionReason": ("LANGUAGE_DECISION_REASON", "str"),
        "languageDecisionConfidence": ("LANGUAGE_DECISION_CONFIDENCE", "float"),
        "personalNoteCategory": ("PERSONAL_NOTE_CATEGORY", "str"),
        "personalFolderId": ("PERSONAL_FOLDER_ID", "str"),
        "folderPath": ("FOLDER_PATH", "clob"),
        "coverUrl": ("COVER_URL", "str"),
        "pageCount": ("PAGE_COUNT", "int"),
        "tags": ("TAGS_JSON", "json"),
    }
    sets = ["UPDATED_AT = CURRENT_TIMESTAMP"] if "UPDATED_AT" in lib_cols else []
    binds: Dict[str, Any] = {"p_uid": firebase_uid, "p_item": item_id}

    for key, value in (patch or {}).items():
        if key not in allowlist_map:
            continue
        col, kind = allowlist_map[key]
        if col not in lib_cols:
            continue
        bind_name = f"p_{key}"
        if kind == "bool":
            binds[bind_name] = 1 if bool(value) else 0
            sets.append(f"{col} = :{bind_name}")
        elif kind == "int":
            if value in (None, ""):
                binds[bind_name] = None
            else:
                binds[bind_name] = int(value)
            sets.append(f"{col} = :{bind_name}")
        elif kind == "float":
            binds[bind_name] = float(value) if value is not None else None
            sets.append(f"{col} = :{bind_name}")
        elif kind == "json":
            binds[bind_name] = json.dumps(value or [], ensure_ascii=False)
            sets.append(f"{col} = TO_CLOB(:{bind_name})")
        elif kind == "clob":
            binds[bind_name] = None if value is None else str(value)
            sets.append(f"{col} = CASE WHEN :{bind_name} IS NOT NULL THEN TO_CLOB(:{bind_name}) ELSE NULL END")
        else:
            binds[bind_name] = None if value is None else str(value)
            sets.append(f"{col} = :{bind_name}")

    if not sets or (len(sets) == 1 and sets[0] == "UPDATED_AT = CURRENT_TIMESTAMP"):
        return {"success": True, "item_id": item_id, "updated": False}

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {_LIBRARY_TABLE}
                SET {', '.join(sets)}
                WHERE FIREBASE_UID = :p_uid
                  AND ITEM_ID = :p_item
                  AND NVL(IS_DELETED, 0) = 0
                """,
                binds,
            )
            if (cur.rowcount or 0) == 0:
                raise ValueError("item not found")
        conn.commit()
    return {"success": True, "item_id": item_id, "updated": True}


def delete_library_item(firebase_uid: str, item_id: str) -> dict:
    return purge_item_content(firebase_uid=firebase_uid, book_id=item_id)


def bulk_delete_library_items(firebase_uid: str, item_ids: list[str]) -> dict:
    requested = [str(i or "").strip() for i in (item_ids or []) if str(i or "").strip()]
    results = []
    deleted = 0
    failed = 0
    for item_id in requested:
        res = delete_library_item(firebase_uid, item_id)
        ok = bool(res.get("success"))
        if ok:
            deleted += 1
        else:
            failed += 1
        results.append({"item_id": item_id, **res})
    return {
        "success": failed == 0,
        "requested": len(requested),
        "deleted": deleted,
        "failed": failed,
        "results": results,
    }
