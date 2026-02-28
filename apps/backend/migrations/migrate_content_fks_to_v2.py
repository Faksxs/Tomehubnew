"""
Migration: move content-linked foreign keys from archived table to V2.

Applies:
1) Backup current TOMEHUB_CONTENT_TAGS and TOMEHUB_FLOW_SEEN tables (CTAS).
2) Backfill TOMEHUB_CONTENT_TAGS.CONTENT_ID by mapping archived rows to V2 rows.
3) Regenerate missing tags from TOMEHUB_CONTENT_V2.CATEGORIES.
4) Delete orphan rows that do not resolve to TOMEHUB_CONTENT_V2.
5) Re-point FK_CONTENT_TAGS_CONTENT and FK_FLOW_CHUNK to TOMEHUB_CONTENT_V2(ID).
"""

from __future__ import annotations

import os
import re
import sys
import json
import unicodedata
from datetime import datetime, UTC
from typing import Iterable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name=:p_name",
        {"p_name": table_name.upper()},
    )
    return int(cur.fetchone()[0]) > 0


def _constraint_parent_table(cur, table_name: str, constraint_name: str) -> str | None:
    cur.execute(
        """
        SELECT p.table_name
        FROM user_constraints c
        JOIN user_constraints p ON p.constraint_name = c.r_constraint_name
        WHERE c.table_name = :p_table
          AND c.constraint_name = :p_cons
          AND c.constraint_type = 'R'
        """,
        {"p_table": table_name.upper(), "p_cons": constraint_name.upper()},
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _constraint_exists(cur, table_name: str, constraint_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM user_constraints
        WHERE table_name = :p_table
          AND constraint_name = :p_cons
        """,
        {"p_table": table_name.upper(), "p_cons": constraint_name.upper()},
    )
    return int(cur.fetchone()[0]) > 0


def _create_backup_if_missing(cur, source_table: str, backup_table: str) -> None:
    if _table_exists(cur, backup_table):
        print(f"  - backup exists: {backup_table}")
        return
    cur.execute(f"CREATE TABLE {backup_table} AS SELECT * FROM {source_table}")
    print(f"  - backup created: {backup_table}")


def _normalize_tag(text: str) -> str:
    value = str(text or "").strip().lower()
    if not value:
        return ""
    value = (
        value.replace("ı", "i")
        .replace("İ", "i")
        .replace("â", "a")
        .replace("î", "i")
        .replace("û", "u")
    )
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9\s]+", " ", value)
    value = " ".join(value.split())
    return value


def _extract_tags_from_categories(raw_value: str) -> Iterable[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []

    tags: list[str] = []
    if text.startswith("[") and text.endswith("]"):
        try:
            payload = json.loads(text)
            if isinstance(payload, list):
                for item in payload:
                    token = str(item or "").strip()
                    if token:
                        tags.append(token)
                return tags
        except Exception:
            pass

    # Fallback for plain scalar or delimited strings.
    parts = re.split(r"[,\n;|/]+", text)
    for part in parts:
        token = str(part or "").strip()
        if token:
            tags.append(token)
    return tags


def _count(cur, sql: str, binds: dict | None = None) -> int:
    cur.execute(sql, binds or {})
    return int(cur.fetchone()[0])


def run_migration() -> None:
    today = datetime.now(UTC).strftime("%Y%m%d")
    backup_tags = f"TH_BKP_CTAGS_{today}"
    backup_flow = f"TH_BKP_FSEEN_{today}"

    DatabaseManager.init_pool()

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            print("Step 1/6: pre-check")
            tags_total_before = _count(cur, "SELECT COUNT(*) FROM TOMEHUB_CONTENT_TAGS")
            flow_total_before = _count(cur, "SELECT COUNT(*) FROM TOMEHUB_FLOW_SEEN")
            print(f"  - tags_before={tags_total_before}")
            print(f"  - flow_before={flow_total_before}")

            print("Step 2/6: backup tables")
            _create_backup_if_missing(cur, "TOMEHUB_CONTENT_TAGS", backup_tags)
            _create_backup_if_missing(cur, "TOMEHUB_FLOW_SEEN", backup_flow)
            conn.commit()

            print("Step 3/6: drop old content_tags fk and backfill archived -> v2 ids")
            if _constraint_exists(cur, "TOMEHUB_CONTENT_TAGS", "FK_CONTENT_TAGS_CONTENT"):
                cur.execute("ALTER TABLE TOMEHUB_CONTENT_TAGS DROP CONSTRAINT FK_CONTENT_TAGS_CONTENT")
                print("  - dropped FK_CONTENT_TAGS_CONTENT (old parent)")
            conn.commit()

            cur.execute(
                """
                MERGE INTO TOMEHUB_CONTENT_TAGS t
                USING (
                    SELECT t2.ID AS tag_row_id, MIN(v.ID) AS new_content_id
                    FROM TOMEHUB_CONTENT_TAGS t2
                    JOIN TOMEHUB_CONTENT_ARCHIVED a ON a.ID = t2.CONTENT_ID
                    JOIN TOMEHUB_CONTENT_V2 v
                      ON v.FIREBASE_UID = a.FIREBASE_UID
                     AND v.ITEM_ID = a.BOOK_ID
                     AND NVL(v.PAGE_NUMBER, -1) = NVL(a.PAGE_NUMBER, -1)
                     AND NVL(v.CHUNK_INDEX, -1) = NVL(a.CHUNK_INDEX, -1)
                     AND DBMS_LOB.SUBSTR(v.CONTENT_CHUNK, 500, 1) = DBMS_LOB.SUBSTR(a.CONTENT_CHUNK, 500, 1)
                    GROUP BY t2.ID
                ) m
                ON (t.ID = m.tag_row_id)
                WHEN MATCHED THEN
                  UPDATE SET t.CONTENT_ID = m.new_content_id
                """
            )
            print(f"  - mapped_rows={cur.rowcount or 0}")
            conn.commit()

            print("Step 4/6: regenerate tags from content_v2.categories")
            cur.execute(
                """
                SELECT ID, CATEGORIES
                FROM TOMEHUB_CONTENT_V2
                WHERE CATEGORIES IS NOT NULL
                  AND DBMS_LOB.GETLENGTH(CATEGORIES) > 0
                """
            )
            rows = cur.fetchall() or []
            inserted = 0
            skipped = 0
            for content_id, categories_value in rows:
                categories_text = safe_read_clob(categories_value)
                for tag in _extract_tags_from_categories(categories_text):
                    tag_norm = _normalize_tag(tag)
                    if not tag_norm:
                        continue
                    cur.execute(
                        """
                        MERGE INTO TOMEHUB_CONTENT_TAGS t
                        USING (
                            SELECT :p_cid AS content_id, :p_tag AS tag, :p_norm AS tag_norm
                            FROM DUAL
                        ) src
                        ON (t.CONTENT_ID = src.content_id AND t.TAG_NORM = src.tag_norm)
                        WHEN NOT MATCHED THEN
                          INSERT (CONTENT_ID, TAG, TAG_NORM, CREATED_AT)
                          VALUES (src.content_id, src.tag, src.tag_norm, CURRENT_TIMESTAMP)
                        """,
                        {"p_cid": int(content_id), "p_tag": str(tag).strip(), "p_norm": tag_norm},
                    )
                    if (cur.rowcount or 0) > 0:
                        inserted += 1
                    else:
                        skipped += 1
            print(f"  - regenerated_inserted={inserted}")
            print(f"  - regenerated_skipped_existing={skipped}")
            conn.commit()

            print("Step 5/6: delete orphan rows")
            cur.execute(
                """
                DELETE FROM TOMEHUB_CONTENT_TAGS t
                WHERE NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_CONTENT_V2 v
                    WHERE v.ID = t.CONTENT_ID
                )
                """
            )
            deleted_tags = cur.rowcount or 0
            cur.execute(
                """
                DELETE FROM TOMEHUB_FLOW_SEEN f
                WHERE NOT EXISTS (
                    SELECT 1 FROM TOMEHUB_CONTENT_V2 v
                    WHERE v.ID = f.CHUNK_ID
                )
                """
            )
            deleted_flow = cur.rowcount or 0
            print(f"  - deleted_orphan_tags={deleted_tags}")
            print(f"  - deleted_orphan_flow={deleted_flow}")
            conn.commit()

            print("Step 6/6: move foreign keys to content_v2")
            if _constraint_exists(cur, "TOMEHUB_CONTENT_TAGS", "FK_CONTENT_TAGS_CONTENT"):
                cur.execute("ALTER TABLE TOMEHUB_CONTENT_TAGS DROP CONSTRAINT FK_CONTENT_TAGS_CONTENT")
            cur.execute(
                """
                ALTER TABLE TOMEHUB_CONTENT_TAGS
                ADD CONSTRAINT FK_CONTENT_TAGS_CONTENT
                FOREIGN KEY (CONTENT_ID) REFERENCES TOMEHUB_CONTENT_V2(ID)
                """
            )

            if _constraint_exists(cur, "TOMEHUB_FLOW_SEEN", "FK_FLOW_CHUNK"):
                cur.execute("ALTER TABLE TOMEHUB_FLOW_SEEN DROP CONSTRAINT FK_FLOW_CHUNK")
            cur.execute(
                """
                ALTER TABLE TOMEHUB_FLOW_SEEN
                ADD CONSTRAINT FK_FLOW_CHUNK
                FOREIGN KEY (CHUNK_ID) REFERENCES TOMEHUB_CONTENT_V2(ID)
                """
            )
            conn.commit()

            tags_total_after = _count(cur, "SELECT COUNT(*) FROM TOMEHUB_CONTENT_TAGS")
            flow_total_after = _count(cur, "SELECT COUNT(*) FROM TOMEHUB_FLOW_SEEN")
            tags_fk_parent = _constraint_parent_table(cur, "TOMEHUB_CONTENT_TAGS", "FK_CONTENT_TAGS_CONTENT")
            flow_fk_parent = _constraint_parent_table(cur, "TOMEHUB_FLOW_SEEN", "FK_FLOW_CHUNK")

            print("Done.")
            print(f"  - tags_after={tags_total_after}")
            print(f"  - flow_after={flow_total_after}")
            print(f"  - FK_CONTENT_TAGS_CONTENT -> {tags_fk_parent}")
            print(f"  - FK_FLOW_CHUNK -> {flow_fk_parent}")


if __name__ == "__main__":
    run_migration()
