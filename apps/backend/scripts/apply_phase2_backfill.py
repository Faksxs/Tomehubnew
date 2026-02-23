#!/usr/bin/env python3
"""
Phase 2 backfill (idempotent)

Backfills:
- TOMEHUB_LIBRARY_ITEMS (base + inferred metadata/policy)
- TOMEHUB_CONTENT.INGESTION_TYPE / CONTENT_TYPE / SEARCH_VISIBILITY
- TOMEHUB_CONTENT.CONTENT_HASH (SHA-256 on canonicalized text)
- TOMEHUB_ITEM_INDEX_STATE initial summary population

Default mode is dry-run.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import uuid
from datetime import datetime, timezone

import oracledb

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_id() -> str:
    return f"phase2_backfill_{_utc_now_str()}_{uuid.uuid4().hex[:8]}"


def _canonicalize_text(text: str) -> str:
    """
    Canonicalization for CONTENT_HASH (documented rule for phase-2 backfill):
    - normalize CRLF/CR -> LF
    - strip leading/trailing whitespace
    - collapse all whitespace runs to a single space
    """
    raw = str(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :t", {"t": table_name.upper()})
    return cursor.fetchone() is not None


def _preflight(cursor) -> None:
    required = [
        "TOMEHUB_CONTENT",
        "TOMEHUB_LIBRARY_ITEMS",
        "TOMEHUB_ITEM_INDEX_STATE",
    ]
    missing = [t for t in required if not _table_exists(cursor, t)]
    if missing:
        raise RuntimeError(f"Phase 2 preflight failed. Missing tables: {', '.join(missing)}")


def _insert_run_row(cursor, run_id: str, execute: bool) -> None:
    try:
        cursor.execute(
            """
            INSERT INTO TOMEHUB_INGESTION_RUNS
                (RUN_ID, RUN_TYPE, STATUS, STARTED_AT, METADATA_JSON)
            VALUES
                (:p_run, 'PHASE2_BACKFILL', :p_status, CURRENT_TIMESTAMP, :p_meta)
            """,
            {
                "p_run": run_id,
                "p_status": "RUNNING" if execute else "DRY_RUN",
                "p_meta": '{"phase":"2","job":"apply_phase2_backfill"}',
            },
        )
    except Exception:
        # Non-critical tracking table usage
        pass


def _finish_run_row(cursor, run_id: str, status: str, processed: int = 0, success: int = 0, failed: int = 0) -> None:
    try:
        cursor.execute(
            """
            UPDATE TOMEHUB_INGESTION_RUNS
               SET STATUS = :p_status,
                   FINISHED_AT = CURRENT_TIMESTAMP,
                   PROCESSED_ITEMS = :p_proc,
                   SUCCESS_COUNT = :p_ok,
                   FAILED_COUNT = :p_fail
             WHERE RUN_ID = :p_run
            """,
            {"p_status": status, "p_proc": processed, "p_ok": success, "p_fail": failed, "p_run": run_id},
        )
    except Exception:
        pass


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _backfill_library_items(cursor, uid: str | None, run_id: str) -> int:
    uid_filter = ""
    params = {"p_run_id": run_id}
    if uid:
        uid_filter = " AND c.FIREBASE_UID = :p_uid "
        params["p_uid"] = uid

    # Aggregate from content first, then enrich with BOOKS registry when available.
    sql = f"""
    MERGE INTO TOMEHUB_LIBRARY_ITEMS li
    USING (
        WITH content_agg AS (
            SELECT
                c.FIREBASE_UID,
                c.BOOK_ID AS ITEM_ID,
                MAX(c.TITLE) KEEP (
                    DENSE_RANK LAST ORDER BY NVL(c.UPDATED_AT, c.CREATED_AT), c.ID
                ) AS REP_TITLE,
                CAST(NULL AS VARCHAR2(500)) AS REP_AUTHOR,
                MIN(c.CREATED_AT) AS MIN_CREATED_AT,
                MAX(c.UPDATED_AT) AS MAX_UPDATED_AT,
                MAX(CASE WHEN c.SOURCE_TYPE IN ('PDF','EPUB','PDF_CHUNK','BOOK','HIGHLIGHT','NOTES') THEN 1 ELSE 0 END) AS HAS_BOOKISH,
                MAX(CASE WHEN c.SOURCE_TYPE = 'ARTICLE' THEN 1 ELSE 0 END) AS HAS_ARTICLE,
                MAX(CASE WHEN c.SOURCE_TYPE = 'WEBSITE' THEN 1 ELSE 0 END) AS HAS_WEBSITE,
                SUM(CASE WHEN c.SOURCE_TYPE = 'PERSONAL_NOTE' THEN 1 ELSE 0 END) AS CNT_PERSONAL_NOTE,
                SUM(CASE WHEN c.SOURCE_TYPE = 'INSIGHT' THEN 1 ELSE 0 END) AS CNT_INSIGHT
            FROM TOMEHUB_CONTENT c
            WHERE c.BOOK_ID IS NOT NULL
              {uid_filter}
            GROUP BY c.FIREBASE_UID, c.BOOK_ID
        ),
        src_base AS (
            SELECT
                ca.ITEM_ID,
                ca.FIREBASE_UID,
                CASE
                    WHEN ca.HAS_BOOKISH = 1 THEN 'BOOK'
                    WHEN ca.HAS_ARTICLE = 1 THEN 'ARTICLE'
                    WHEN ca.HAS_WEBSITE = 1 THEN 'WEBSITE'
                    WHEN ca.CNT_PERSONAL_NOTE > 0 OR ca.CNT_INSIGHT > 0 THEN 'PERSONAL_NOTE'
                    ELSE 'BOOK'
                END AS ITEM_TYPE,
                COALESCE(b.TITLE, ca.REP_TITLE) AS TITLE,
                COALESCE(NULLIF(TRIM(b.AUTHOR), ''), ca.REP_AUTHOR) AS AUTHOR,
                CAST(NULL AS VARCHAR2(2000)) AS SOURCE_URL,
                COALESCE(b.CREATED_AT, ca.MIN_CREATED_AT, CURRENT_TIMESTAMP) AS CREATED_AT_SRC,
                COALESCE(b.LAST_UPDATED, ca.MAX_UPDATED_AT, CURRENT_TIMESTAMP) AS UPDATED_AT_SRC,
                ca.CNT_PERSONAL_NOTE,
                ca.CNT_INSIGHT
            FROM content_agg ca
            LEFT JOIN TOMEHUB_BOOKS b
              ON b.ID = ca.ITEM_ID
             AND b.FIREBASE_UID = ca.FIREBASE_UID
        )
        SELECT
            sb.ITEM_ID,
            sb.FIREBASE_UID,
            sb.ITEM_TYPE,
            sb.TITLE,
            sb.AUTHOR,
            sb.SOURCE_URL,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE > 0 THEN 'EXCLUDED_BY_DEFAULT'
                ELSE 'DEFAULT'
            END AS SEARCH_VISIBILITY,
            CASE
                WHEN sb.ITEM_TYPE = 'PERSONAL_NOTE' AND sb.CNT_PERSONAL_NOTE = 0 AND sb.CNT_INSIGHT > 0 THEN 'IDEAS'
                ELSE NULL
            END AS PERSONAL_NOTE_CATEGORY,
            sb.CREATED_AT_SRC,
            sb.UPDATED_AT_SRC
        FROM src_base sb
    ) src
    ON (li.ITEM_ID = src.ITEM_ID AND li.FIREBASE_UID = src.FIREBASE_UID)
    WHEN NOT MATCHED THEN
        INSERT (
            ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, SOURCE_URL,
            SEARCH_VISIBILITY, PERSONAL_NOTE_CATEGORY, ORIGIN_SYSTEM, ORIGIN_COLLECTION, SYNC_RUN_ID,
            CREATED_AT, UPDATED_AT
        )
        VALUES (
            src.ITEM_ID, src.FIREBASE_UID, src.ITEM_TYPE, src.TITLE, src.AUTHOR, src.SOURCE_URL,
            src.SEARCH_VISIBILITY, src.PERSONAL_NOTE_CATEGORY, 'ORACLE_NATIVE', 'TOMEHUB_CONTENT_AGG', :p_run_id,
            src.CREATED_AT_SRC, src.UPDATED_AT_SRC
        )
    WHEN MATCHED THEN
        UPDATE SET
            li.ITEM_TYPE = COALESCE(li.ITEM_TYPE, src.ITEM_TYPE),
            li.TITLE = COALESCE(li.TITLE, src.TITLE),
            li.AUTHOR = COALESCE(li.AUTHOR, src.AUTHOR),
            li.SOURCE_URL = COALESCE(li.SOURCE_URL, src.SOURCE_URL),
            li.PERSONAL_NOTE_CATEGORY = COALESCE(li.PERSONAL_NOTE_CATEGORY, src.PERSONAL_NOTE_CATEGORY),
            li.SEARCH_VISIBILITY = COALESCE(li.SEARCH_VISIBILITY, src.SEARCH_VISIBILITY),
            li.ORIGIN_SYSTEM = COALESCE(li.ORIGIN_SYSTEM, 'ORACLE_NATIVE'),
            li.ORIGIN_COLLECTION = COALESCE(li.ORIGIN_COLLECTION, 'TOMEHUB_CONTENT_AGG'),
            li.SYNC_RUN_ID = COALESCE(li.SYNC_RUN_ID, :p_run_id),
            li.UPDATED_AT = COALESCE(li.UPDATED_AT, src.UPDATED_AT_SRC)
    """
    cursor.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


def _backfill_content_type_and_ingestion_type(cursor, uid: str | None) -> int:
    uid_clause = " AND FIREBASE_UID = :p_uid " if uid else ""
    params = {"p_uid": uid} if uid else {}
    sql = f"""
    UPDATE TOMEHUB_CONTENT
       SET INGESTION_TYPE = CASE
            WHEN SOURCE_TYPE IN ('PDF', 'PDF_CHUNK') THEN 'PDF'
            WHEN SOURCE_TYPE = 'EPUB' THEN 'EPUB'
            WHEN SOURCE_TYPE IN ('ARTICLE', 'WEBSITE') THEN 'WEB'
            WHEN SOURCE_TYPE = 'BOOK' THEN 'SYNC'
            WHEN SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT', 'NOTES', 'PERSONAL_NOTE') THEN 'MANUAL'
            ELSE INGESTION_TYPE
       END,
           CONTENT_TYPE = CASE
            WHEN SOURCE_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK') THEN 'BOOK_CHUNK'
            WHEN SOURCE_TYPE = 'HIGHLIGHT' THEN 'HIGHLIGHT'
            WHEN SOURCE_TYPE = 'INSIGHT' THEN 'INSIGHT'
            WHEN SOURCE_TYPE = 'NOTES' THEN 'HIGHLIGHT'
            WHEN SOURCE_TYPE = 'PERSONAL_NOTE' THEN 'NOTE'
            WHEN SOURCE_TYPE = 'ARTICLE' THEN 'ARTICLE_BODY'
            WHEN SOURCE_TYPE = 'WEBSITE' THEN 'WEBSITE_BODY'
            WHEN SOURCE_TYPE = 'BOOK' THEN 'ITEM_SUMMARY'
            ELSE CONTENT_TYPE
       END
     WHERE 1=1
       {uid_clause}
       AND (
            INGESTION_TYPE IS NULL
         OR CONTENT_TYPE IS NULL
       )
    """
    cursor.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


def _backfill_content_visibility(cursor, uid: str | None) -> int:
    total = 0

    uid_clause = " AND c.FIREBASE_UID = :p_uid " if uid else ""
    params = {"p_uid": uid} if uid else {}

    # Default fill
    sql_default = f"""
    UPDATE TOMEHUB_CONTENT c
       SET SEARCH_VISIBILITY = 'DEFAULT'
     WHERE c.SEARCH_VISIBILITY IS NULL
       {uid_clause}
    """
    cursor.execute(sql_default, params)
    total += int(getattr(cursor, "rowcount", 0) or 0)

    # Inherit from canonical items when available (important for PERSONAL_NOTE rows)
    sql_inherit = f"""
    MERGE INTO TOMEHUB_CONTENT c
    USING (
        SELECT FIREBASE_UID, ITEM_ID, SEARCH_VISIBILITY
        FROM TOMEHUB_LIBRARY_ITEMS
        WHERE SEARCH_VISIBILITY IS NOT NULL
        {"AND FIREBASE_UID = :p_uid" if uid else ""}
    ) li
    ON (c.FIREBASE_UID = li.FIREBASE_UID AND c.BOOK_ID = li.ITEM_ID)
    WHEN MATCHED THEN
      UPDATE SET c.SEARCH_VISIBILITY = li.SEARCH_VISIBILITY
    """
    cursor.execute(sql_inherit, params)
    total += int(getattr(cursor, "rowcount", 0) or 0)

    return total


def _backfill_content_hash(cursor, uid: str | None, batch_size: int = 500) -> tuple[int, int]:
    """
    Returns (scanned, updated).
    """
    scanned = 0
    updated = 0
    params = {"p_uid": uid} if uid else {}
    uid_clause = " AND FIREBASE_UID = :p_uid " if uid else ""

    read_cursor = cursor.connection.cursor()
    write_cursor = cursor.connection.cursor()

    read_cursor.execute(
        f"""
        SELECT ID, CONTENT_CHUNK
        FROM TOMEHUB_CONTENT
        WHERE CONTENT_HASH IS NULL
          {uid_clause}
        ORDER BY ID
        """,
        params,
    )

    try:
        while True:
            rows = read_cursor.fetchmany(batch_size)
            if not rows:
                break
            updates = []
            for r in rows:
                scanned += 1
                rid = int(r[0])
                txt = safe_read_clob(r[1]) if r[1] is not None else ""
                canonical = _canonicalize_text(txt)
                digest = _sha256_hex(canonical)
                updates.append({"p_hash": digest, "p_id": rid})
            if updates:
                write_cursor.executemany(
                    """
                    UPDATE TOMEHUB_CONTENT
                       SET CONTENT_HASH = :p_hash
                     WHERE ID = :p_id
                       AND CONTENT_HASH IS NULL
                    """,
                    updates,
                )
                updated += int(getattr(write_cursor, "rowcount", 0) or 0)
    finally:
        try:
            read_cursor.close()
        except Exception:
            pass
        try:
            write_cursor.close()
        except Exception:
            pass
    return scanned, updated


def _backfill_item_index_state(cursor, uid: str | None) -> int:
    uid_filter_li = " WHERE li.FIREBASE_UID = :p_uid " if uid else ""
    uid_filter_c = " AND c.FIREBASE_UID = :p_uid " if uid else ""
    uid_filter_c2 = " AND c.FIREBASE_UID = :p_uid " if uid else ""
    params = {"p_uid": uid} if uid else {}

    sql = f"""
    MERGE INTO TOMEHUB_ITEM_INDEX_STATE t
    USING (
        WITH content_agg AS (
            SELECT
                c.FIREBASE_UID,
                c.BOOK_ID AS ITEM_ID,
                COUNT(*) AS TOTAL_CHUNKS,
                SUM(CASE WHEN c.VEC_EMBEDDING IS NOT NULL THEN 1 ELSE 0 END) AS EMBEDDED_CHUNKS,
                MAX(NVL(c.UPDATED_AT, c.CREATED_AT)) AS SOURCE_UPDATED_AT
            FROM TOMEHUB_CONTENT c
            WHERE c.BOOK_ID IS NOT NULL
              {uid_filter_c}
            GROUP BY c.FIREBASE_UID, c.BOOK_ID
        ),
        graph_agg AS (
            SELECT
                c.FIREBASE_UID,
                c.BOOK_ID AS ITEM_ID,
                COUNT(DISTINCT cc.CONTENT_ID) AS GRAPH_LINKED_CHUNKS
            FROM TOMEHUB_CONCEPT_CHUNKS cc
            JOIN TOMEHUB_CONTENT c ON c.ID = cc.CONTENT_ID
            WHERE c.BOOK_ID IS NOT NULL
              {uid_filter_c2}
            GROUP BY c.FIREBASE_UID, c.BOOK_ID
        ),
        src AS (
            SELECT
                li.FIREBASE_UID,
                li.ITEM_ID,
                NVL(ca.TOTAL_CHUNKS, 0) AS TOTAL_CHUNKS,
                NVL(ca.EMBEDDED_CHUNKS, 0) AS EMBEDDED_CHUNKS,
                NVL(ga.GRAPH_LINKED_CHUNKS, 0) AS GRAPH_LINKED_CHUNKS,
                ca.SOURCE_UPDATED_AT
            FROM TOMEHUB_LIBRARY_ITEMS li
            LEFT JOIN content_agg ca
              ON ca.FIREBASE_UID = li.FIREBASE_UID
             AND ca.ITEM_ID = li.ITEM_ID
            LEFT JOIN graph_agg ga
              ON ga.FIREBASE_UID = li.FIREBASE_UID
             AND ga.ITEM_ID = li.ITEM_ID
            {uid_filter_li}
        )
        SELECT
            s.FIREBASE_UID,
            s.ITEM_ID,
            CASE
              WHEN s.EMBEDDED_CHUNKS > 0 AND s.GRAPH_LINKED_CHUNKS > 0 THEN 'fully_ready'
              WHEN s.EMBEDDED_CHUNKS > 0 THEN 'vector_ready'
              WHEN s.GRAPH_LINKED_CHUNKS > 0 THEN 'graph_ready'
              ELSE 'not_ready'
            END AS INDEX_FRESHNESS_STATE,
            s.TOTAL_CHUNKS,
            s.EMBEDDED_CHUNKS,
            s.GRAPH_LINKED_CHUNKS,
            CASE WHEN s.EMBEDDED_CHUNKS > 0 THEN 1 ELSE 0 END AS VECTOR_READY,
            CASE WHEN s.GRAPH_LINKED_CHUNKS > 0 THEN 1 ELSE 0 END AS GRAPH_READY,
            CASE WHEN s.EMBEDDED_CHUNKS > 0 AND s.GRAPH_LINKED_CHUNKS > 0 THEN 1 ELSE 0 END AS FULLY_READY,
            CASE WHEN s.TOTAL_CHUNKS > 0 THEN ROUND(s.EMBEDDED_CHUNKS / s.TOTAL_CHUNKS, 4) ELSE 0 END AS VECTOR_COVERAGE_RATIO,
            CASE WHEN s.TOTAL_CHUNKS > 0 THEN ROUND(s.GRAPH_LINKED_CHUNKS / s.TOTAL_CHUNKS, 4) ELSE 0 END AS GRAPH_COVERAGE_RATIO,
            s.SOURCE_UPDATED_AT
        FROM src s
    ) src
    ON (t.FIREBASE_UID = src.FIREBASE_UID AND t.ITEM_ID = src.ITEM_ID)
    WHEN NOT MATCHED THEN
      INSERT (
        FIREBASE_UID, ITEM_ID, INDEX_FRESHNESS_STATE, TOTAL_CHUNKS, EMBEDDED_CHUNKS, GRAPH_LINKED_CHUNKS,
        VECTOR_READY, GRAPH_READY, FULLY_READY, VECTOR_COVERAGE_RATIO, GRAPH_COVERAGE_RATIO,
        LAST_CHECKED_AT, SOURCE_UPDATED_AT, UPDATED_AT
      )
      VALUES (
        src.FIREBASE_UID, src.ITEM_ID, src.INDEX_FRESHNESS_STATE, src.TOTAL_CHUNKS, src.EMBEDDED_CHUNKS, src.GRAPH_LINKED_CHUNKS,
        src.VECTOR_READY, src.GRAPH_READY, src.FULLY_READY, src.VECTOR_COVERAGE_RATIO, src.GRAPH_COVERAGE_RATIO,
        CURRENT_TIMESTAMP, src.SOURCE_UPDATED_AT, CURRENT_TIMESTAMP
      )
    WHEN MATCHED THEN
      UPDATE SET
        t.INDEX_FRESHNESS_STATE = src.INDEX_FRESHNESS_STATE,
        t.TOTAL_CHUNKS = src.TOTAL_CHUNKS,
        t.EMBEDDED_CHUNKS = src.EMBEDDED_CHUNKS,
        t.GRAPH_LINKED_CHUNKS = src.GRAPH_LINKED_CHUNKS,
        t.VECTOR_READY = src.VECTOR_READY,
        t.GRAPH_READY = src.GRAPH_READY,
        t.FULLY_READY = src.FULLY_READY,
        t.VECTOR_COVERAGE_RATIO = src.VECTOR_COVERAGE_RATIO,
        t.GRAPH_COVERAGE_RATIO = src.GRAPH_COVERAGE_RATIO,
        t.LAST_CHECKED_AT = CURRENT_TIMESTAMP,
        t.SOURCE_UPDATED_AT = src.SOURCE_UPDATED_AT,
        t.UPDATED_AT = CURRENT_TIMESTAMP
    """
    cursor.execute(sql, params)
    return int(getattr(cursor, "rowcount", 0) or 0)


def _print_summary(cursor, uid: str | None) -> None:
    params = {"p_uid": uid} if uid else {}
    uid_clause_li = " WHERE FIREBASE_UID = :p_uid " if uid else ""
    uid_clause_c = " WHERE FIREBASE_UID = :p_uid " if uid else ""

    print("\n=== Phase 2 Backfill Summary ===")
    print(f"[INFO] Scope UID: {uid or 'ALL'}")
    print(f"[INFO] LIBRARY_ITEMS rows: {_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS {uid_clause_li}', params)}")
    print(f"[INFO] ITEM_INDEX_STATE rows: {_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_ITEM_INDEX_STATE {uid_clause_li}', params)}")
    print(
        f"[INFO] CONTENT rows with CONTENT_TYPE populated: "
        f"{_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_CONTENT {uid_clause_c} ' + ('AND ' if uid else 'WHERE ') + 'CONTENT_TYPE IS NOT NULL', params)}"
    )
    print(
        f"[INFO] CONTENT rows with INGESTION_TYPE populated: "
        f"{_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_CONTENT {uid_clause_c} ' + ('AND ' if uid else 'WHERE ') + 'INGESTION_TYPE IS NOT NULL', params)}"
    )
    print(
        f"[INFO] CONTENT rows with SEARCH_VISIBILITY populated: "
        f"{_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_CONTENT {uid_clause_c} ' + ('AND ' if uid else 'WHERE ') + 'SEARCH_VISIBILITY IS NOT NULL', params)}"
    )
    print(
        f"[INFO] CONTENT rows with CONTENT_HASH populated: "
        f"{_count(cursor, f'SELECT COUNT(*) FROM TOMEHUB_CONTENT {uid_clause_c} ' + ('AND ' if uid else 'WHERE ') + 'CONTENT_HASH IS NOT NULL', params)}"
    )


def run_backfill(execute: bool, uid: str | None, batch_size: int, skip_hash: bool) -> int:
    run_id = _run_id()
    print(f"=== Phase 2 Backfill {'EXECUTE' if execute else 'DRY-RUN'} ===")
    print(f"[INFO] run_id={run_id}")
    print("[INFO] CONTENT_HASH canonicalization: CRLF->LF, strip, collapse whitespace, SHA-256")

    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                _preflight(cursor)
                _insert_run_row(cursor, run_id, execute=execute)

                if not execute:
                    _print_summary(cursor, uid)
                    conn.rollback()
                    print("[OK] Dry-run complete (no changes committed).")
                    return 0

                stats = {}
                stats["library_items_merge"] = _backfill_library_items(cursor, uid=uid, run_id=run_id)
                conn.commit()
                print(f"[OK] Library items backfill merge rowcount={stats['library_items_merge']}")

                stats["content_type_ingestion"] = _backfill_content_type_and_ingestion_type(cursor, uid=uid)
                conn.commit()
                print(f"[OK] Content type/ingestion backfill rowcount={stats['content_type_ingestion']}")

                stats["content_visibility"] = _backfill_content_visibility(cursor, uid=uid)
                conn.commit()
                print(f"[OK] Content visibility backfill rowcount={stats['content_visibility']}")

                if skip_hash:
                    stats["hash_scanned"] = 0
                    stats["hash_updated"] = 0
                    print("[SKIP] CONTENT_HASH backfill skipped")
                else:
                    scanned, updated = _backfill_content_hash(cursor, uid=uid, batch_size=batch_size)
                    stats["hash_scanned"] = scanned
                    stats["hash_updated"] = updated
                    conn.commit()
                    print(f"[OK] Content hash backfill scanned={scanned} updated={updated}")

                stats["item_index_state_merge"] = _backfill_item_index_state(cursor, uid=uid)
                conn.commit()
                print(f"[OK] Item index state backfill rowcount={stats['item_index_state_merge']}")

                _print_summary(cursor, uid)
                _finish_run_row(
                    cursor,
                    run_id,
                    status="COMPLETED",
                    processed=int(stats.get("hash_scanned", 0)),
                    success=int(stats.get("hash_updated", 0)),
                    failed=0,
                )
                conn.commit()
                print("[OK] Phase 2 backfill completed.")
                return 0
    except Exception as e:
        print(f"[ERROR] Phase 2 backfill failed: {e}")
        try:
            with DatabaseManager.get_write_connection() as conn2:
                with conn2.cursor() as c2:
                    _finish_run_row(c2, run_id, status="FAILED", processed=0, success=0, failed=1)
                    conn2.commit()
        except Exception:
            pass
        return 2
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Phase 2 backfill")
    parser.add_argument("--execute", action="store_true", help="Commit backfill changes (default dry-run)")
    parser.add_argument("--uid", type=str, default=None, help="Limit to one FIREBASE_UID")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for CONTENT_HASH backfill")
    parser.add_argument("--skip-hash", action="store_true", help="Skip CONTENT_HASH backfill")
    args = parser.parse_args()
    return run_backfill(execute=args.execute, uid=args.uid, batch_size=max(50, args.batch_size), skip_hash=args.skip_hash)


if __name__ == "__main__":
    raise SystemExit(main())
