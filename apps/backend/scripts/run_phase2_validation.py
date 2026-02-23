#!/usr/bin/env python3
"""
Phase 2 validation verifier

Verifies Phase 2 backfill outputs:
- TOMEHUB_LIBRARY_ITEMS population and key parity
- TOMEHUB_CONTENT additive columns population + allowed values
- CONTENT_HASH format (and sampled recompute)
- TOMEHUB_ITEM_INDEX_STATE parity
- Compatibility view sanity
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402
from scripts.apply_phase2_backfill import _canonicalize_text, _sha256_hex  # noqa: E402


ALLOWED_CONTENT_TYPES = {
    "BOOK_CHUNK",
    "HIGHLIGHT",
    "INSIGHT",
    "NOTE",
    "ARTICLE_BODY",
    "WEBSITE_BODY",
    "ITEM_SUMMARY",
}

ALLOWED_INGESTION_TYPES = {"PDF", "EPUB", "WEB", "MANUAL", "SYNC"}
ALLOWED_VISIBILITY = {"DEFAULT", "EXCLUDED_BY_DEFAULT", "NEVER_RETRIEVE"}


def _ok(label: str, value=None):
    if value is None:
        print(f"[OK] {label}")
    else:
        print(f"[OK] {label}: {value}")


def _fail(label: str, value=None):
    if value is None:
        print(f"[FAIL] {label}")
    else:
        print(f"[FAIL] {label}: {value}")


def _count(cursor, sql: str, params: dict | None = None) -> int:
    cursor.execute(sql, params or {})
    row = cursor.fetchone()
    return int(row[0] or 0) if row else 0


def _ensure_tables_and_views(cursor) -> int:
    failures = 0
    needed_tables = {
        "TOMEHUB_CONTENT",
        "TOMEHUB_LIBRARY_ITEMS",
        "TOMEHUB_ITEM_INDEX_STATE",
    }
    needed_views = {
        "VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED",
        "VW_TOMEHUB_BOOKS_COMPAT",
        "VW_TOMEHUB_INGESTION_STATUS_BY_ITEM",
    }
    cursor.execute("SELECT TABLE_NAME FROM USER_TABLES")
    tables = {str(r[0]).upper() for r in cursor.fetchall()}
    cursor.execute("SELECT VIEW_NAME FROM USER_VIEWS")
    views = {str(r[0]).upper() for r in cursor.fetchall()}
    for t in sorted(needed_tables):
        if t in tables:
            _ok(f"Table exists `{t}`")
        else:
            _fail(f"Table exists `{t}`")
            failures += 1
    for v in sorted(needed_views):
        if v in views:
            _ok(f"View exists `{v}`")
        else:
            _fail(f"View exists `{v}`")
            failures += 1
    return failures


def _check_population(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    c_where = "WHERE FIREBASE_UID = :p_uid" if uid else ""
    li_where = "WHERE FIREBASE_UID = :p_uid" if uid else ""

    content_total = _count(cursor, f"SELECT COUNT(*) FROM TOMEHUB_CONTENT {c_where}", params)
    library_total = _count(cursor, f"SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS {li_where}", params)
    idx_total = _count(cursor, f"SELECT COUNT(*) FROM TOMEHUB_ITEM_INDEX_STATE {li_where}", params)
    _ok("CONTENT rows in scope", content_total)
    _ok("LIBRARY_ITEMS rows in scope", library_total)
    _ok("ITEM_INDEX_STATE rows in scope", idx_total)

    for col in ["CONTENT_TYPE", "INGESTION_TYPE", "SEARCH_VISIBILITY", "CONTENT_HASH"]:
        nulls = _count(
            cursor,
            f"SELECT COUNT(*) FROM TOMEHUB_CONTENT {c_where} "
            + ("AND " if uid else "WHERE ")
            + f"{col} IS NULL",
            params,
        )
        if nulls == 0:
            _ok(f"TOMEHUB_CONTENT.{col} null count", 0)
        else:
            _fail(f"TOMEHUB_CONTENT.{col} null count", nulls)
            failures += 1

    return failures


def _check_allowed_values(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    uid_clause = " WHERE FIREBASE_UID = :p_uid " if uid else ""

    checks = [
        ("TOMEHUB_CONTENT.CONTENT_TYPE", "CONTENT_TYPE", "TOMEHUB_CONTENT", ALLOWED_CONTENT_TYPES),
        ("TOMEHUB_CONTENT.INGESTION_TYPE", "INGESTION_TYPE", "TOMEHUB_CONTENT", ALLOWED_INGESTION_TYPES),
        ("TOMEHUB_CONTENT.SEARCH_VISIBILITY", "SEARCH_VISIBILITY", "TOMEHUB_CONTENT", ALLOWED_VISIBILITY),
        ("TOMEHUB_LIBRARY_ITEMS.SEARCH_VISIBILITY", "SEARCH_VISIBILITY", "TOMEHUB_LIBRARY_ITEMS", ALLOWED_VISIBILITY),
    ]
    for label, col, table, allowed in checks:
        cursor.execute(
            f"""
            SELECT {col}, COUNT(*)
            FROM {table}
            {uid_clause}
            GROUP BY {col}
            ORDER BY {col}
            """,
            params,
        )
        bad = []
        rows = cursor.fetchall()
        for value, count in rows:
            v = str(value) if value is not None else None
            if v is None:
                bad.append((v, int(count)))
            elif v not in allowed:
                bad.append((v, int(count)))
        if bad:
            _fail(label + " allowed values", bad)
            failures += 1
        else:
            _ok(label + " allowed values")
    return failures


def _check_mapping_sanity(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    uid_clause = " AND FIREBASE_UID = :p_uid " if uid else ""

    mapping_checks = [
        ("PDF/PDF_CHUNK -> PDF/BOOK_CHUNK",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE IN ('PDF','PDF_CHUNK')
           AND (INGESTION_TYPE <> 'PDF' OR CONTENT_TYPE <> 'BOOK_CHUNK')
         """),
        ("EPUB -> EPUB/BOOK_CHUNK",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'EPUB'
           AND (INGESTION_TYPE <> 'EPUB' OR CONTENT_TYPE <> 'BOOK_CHUNK')
         """),
        ("ARTICLE -> WEB/ARTICLE_BODY",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'ARTICLE'
           AND (INGESTION_TYPE <> 'WEB' OR CONTENT_TYPE <> 'ARTICLE_BODY')
         """),
        ("WEBSITE -> WEB/WEBSITE_BODY",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'WEBSITE'
           AND (INGESTION_TYPE <> 'WEB' OR CONTENT_TYPE <> 'WEBSITE_BODY')
         """),
        ("HIGHLIGHT -> MANUAL/HIGHLIGHT",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'HIGHLIGHT'
           AND (INGESTION_TYPE <> 'MANUAL' OR CONTENT_TYPE <> 'HIGHLIGHT')
         """),
        ("INSIGHT -> MANUAL/INSIGHT",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'INSIGHT'
           AND (INGESTION_TYPE <> 'MANUAL' OR CONTENT_TYPE <> 'INSIGHT')
         """),
        ("PERSONAL_NOTE -> MANUAL/NOTE",
         """
         SELECT COUNT(*)
         FROM TOMEHUB_CONTENT
         WHERE SOURCE_TYPE = 'PERSONAL_NOTE'
           AND (INGESTION_TYPE <> 'MANUAL' OR CONTENT_TYPE <> 'NOTE')
         """),
    ]

    for label, sql in mapping_checks:
        full_sql = sql.strip() + uid_clause
        bad = _count(cursor, full_sql, params)
        if bad == 0:
            _ok("Mapping " + label)
        else:
            _fail("Mapping " + label, bad)
            failures += 1
    return failures


def _check_hashes(cursor, uid: str | None, sample_size: int) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    uid_clause = " AND FIREBASE_UID = :p_uid " if uid else ""

    bad_format = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE CONTENT_HASH IS NULL
           OR LENGTH(CONTENT_HASH) <> 64
           OR NOT REGEXP_LIKE(CONTENT_HASH, '^[0-9a-f]{{64}}$')
           {uid_clause}
        """,
        params,
    )
    if bad_format == 0:
        _ok("CONTENT_HASH format check")
    else:
        _fail("CONTENT_HASH format check", bad_format)
        failures += 1

    cursor.execute(
        f"""
        SELECT ID, CONTENT_CHUNK, CONTENT_HASH
        FROM TOMEHUB_CONTENT
        WHERE CONTENT_HASH IS NOT NULL
          {uid_clause}
        FETCH FIRST {int(max(1, sample_size))} ROWS ONLY
        """,
        params,
    )
    mismatches = []
    for row in cursor.fetchall():
        rid = row[0]
        txt = safe_read_clob(row[1]) if row[1] is not None else ""
        stored = str(row[2] or "")
        recomputed = _sha256_hex(_canonicalize_text(txt))
        if stored != recomputed:
            mismatches.append(str(rid))
            if len(mismatches) >= 10:
                break
    if mismatches:
        _fail("CONTENT_HASH sampled recompute", mismatches)
        failures += 1
    else:
        _ok("CONTENT_HASH sampled recompute", f"{sample_size} rows")
    return failures


def _check_parity(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    c_uid = " AND c.FIREBASE_UID = :p_uid " if uid else ""
    li_uid = " AND li.FIREBASE_UID = :p_uid " if uid else ""
    t_uid = " AND t.FIREBASE_UID = :p_uid " if uid else ""

    # Content->Library missing
    content_missing_library = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM (
          SELECT DISTINCT c.FIREBASE_UID, TO_CHAR(c.BOOK_ID) AS ITEM_ID
          FROM TOMEHUB_CONTENT c
          WHERE c.BOOK_ID IS NOT NULL
            {c_uid}
        ) x
        LEFT JOIN TOMEHUB_LIBRARY_ITEMS li
          ON li.FIREBASE_UID = x.FIREBASE_UID
         AND li.ITEM_ID = x.ITEM_ID
        WHERE li.ITEM_ID IS NULL
        """,
        params,
    )
    if content_missing_library == 0:
        _ok("Content key parity -> missing library items", 0)
    else:
        _fail("Content key parity -> missing library items", content_missing_library)
        failures += 1

    # Library->Content missing (may indicate empty items; should be 0 after phase2 current scope)
    library_missing_content = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_LIBRARY_ITEMS li
        LEFT JOIN (
          SELECT DISTINCT c.FIREBASE_UID, TO_CHAR(c.BOOK_ID) AS ITEM_ID
          FROM TOMEHUB_CONTENT c
          WHERE c.BOOK_ID IS NOT NULL
            {c_uid}
        ) x
          ON x.FIREBASE_UID = li.FIREBASE_UID
         AND x.ITEM_ID = li.ITEM_ID
        WHERE 1=1
          {li_uid}
          AND x.ITEM_ID IS NULL
        """,
        params,
    )
    if library_missing_content == 0:
        _ok("Library key parity -> missing content roots", 0)
    else:
        _fail("Library key parity -> missing content roots", library_missing_content)
        failures += 1

    idx_missing = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_LIBRARY_ITEMS li
        LEFT JOIN TOMEHUB_ITEM_INDEX_STATE t
          ON t.FIREBASE_UID = li.FIREBASE_UID
         AND t.ITEM_ID = li.ITEM_ID
        WHERE 1=1
          {li_uid}
          AND t.ITEM_ID IS NULL
        """,
        params,
    )
    if idx_missing == 0:
        _ok("ITEM_INDEX_STATE missing rows for library items", 0)
    else:
        _fail("ITEM_INDEX_STATE missing rows for library items", idx_missing)
        failures += 1

    idx_extra = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_ITEM_INDEX_STATE t
        LEFT JOIN TOMEHUB_LIBRARY_ITEMS li
          ON li.FIREBASE_UID = t.FIREBASE_UID
         AND li.ITEM_ID = t.ITEM_ID
        WHERE 1=1
          {t_uid}
          AND li.ITEM_ID IS NULL
        """,
        params,
    )
    if idx_extra == 0:
        _ok("ITEM_INDEX_STATE orphan rows", 0)
    else:
        _fail("ITEM_INDEX_STATE orphan rows", idx_extra)
        failures += 1

    dup_li = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM (
          SELECT FIREBASE_UID, ITEM_ID, COUNT(*) c
          FROM TOMEHUB_LIBRARY_ITEMS
          WHERE 1=1 {(' AND FIREBASE_UID = :p_uid' if uid else '')}
          GROUP BY FIREBASE_UID, ITEM_ID
          HAVING COUNT(*) > 1
        )
        """,
        params,
    )
    if dup_li == 0:
        _ok("LIBRARY_ITEMS duplicate (uid,item_id)", 0)
    else:
        _fail("LIBRARY_ITEMS duplicate (uid,item_id)", dup_li)
        failures += 1
    return failures


def _check_views(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    where = " WHERE FIREBASE_UID = :p_uid " if uid else ""

    li_count = _count(cursor, f"SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS {where}", params)
    v_enriched = _count(cursor, f"SELECT COUNT(*) FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED {where}", params)
    v_books = _count(cursor, f"SELECT COUNT(*) FROM VW_TOMEHUB_BOOKS_COMPAT {where}", params)

    if v_enriched == li_count:
        _ok("VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED count parity", v_enriched)
    else:
        _fail("VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED count parity", f"view={v_enriched}, table={li_count}")
        failures += 1

    if v_books == li_count:
        _ok("VW_TOMEHUB_BOOKS_COMPAT count parity", v_books)
    else:
        _fail("VW_TOMEHUB_BOOKS_COMPAT count parity", f"view={v_books}, table={li_count}")
        failures += 1

    dup_enriched = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM (
          SELECT FIREBASE_UID, ITEM_ID, COUNT(*) c
          FROM VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED
          {where}
          GROUP BY FIREBASE_UID, ITEM_ID
          HAVING COUNT(*) > 1
        )
        """,
        params,
    )
    if dup_enriched == 0:
        _ok("VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED duplicate keys", 0)
    else:
        _fail("VW_TOMEHUB_LIBRARY_ITEMS_ENRICHED duplicate keys", dup_enriched)
        failures += 1
    return failures


def _check_policy_sanity(cursor, uid: str | None) -> int:
    failures = 0
    params = {"p_uid": uid} if uid else {}
    uid_clause = " AND FIREBASE_UID = :p_uid " if uid else ""

    # Current expected behavior after phase2: PERSONAL_NOTE content rows inherit EXCLUDED_BY_DEFAULT
    bad_personal_note_visibility = _count(
        cursor,
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE SOURCE_TYPE = 'PERSONAL_NOTE'
          AND NVL(SEARCH_VISIBILITY, 'DEFAULT') <> 'EXCLUDED_BY_DEFAULT'
          {uid_clause}
        """,
        params,
    )
    if bad_personal_note_visibility == 0:
        _ok("PERSONAL_NOTE content rows visibility policy", 0)
    else:
        _fail("PERSONAL_NOTE content rows visibility policy", bad_personal_note_visibility)
        failures += 1
    return failures


def run_validation(uid: str | None, sample_hash_rows: int) -> int:
    print("=== Phase 2 Validation ===")
    print(f"[INFO] Scope UID: {uid or 'ALL'}")
    failures = 0
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                failures += _ensure_tables_and_views(cursor)
                failures += _check_population(cursor, uid)
                failures += _check_allowed_values(cursor, uid)
                failures += _check_mapping_sanity(cursor, uid)
                failures += _check_hashes(cursor, uid, sample_hash_rows)
                failures += _check_parity(cursor, uid)
                failures += _check_views(cursor, uid)
                failures += _check_policy_sanity(cursor, uid)
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    if failures:
        print(f"\n[FAIL] Phase 2 validation completed with {failures} issue(s).")
        return 2
    print("\n[OK] Phase 2 validation passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 backfill validation checks")
    parser.add_argument("--uid", type=str, default=None, help="Limit checks to one FIREBASE_UID")
    parser.add_argument("--sample-hash-rows", type=int, default=25, help="Rows to recompute CONTENT_HASH for sample validation")
    args = parser.parse_args()
    return run_validation(uid=args.uid, sample_hash_rows=max(1, args.sample_hash_rows))


if __name__ == "__main__":
    raise SystemExit(main())

