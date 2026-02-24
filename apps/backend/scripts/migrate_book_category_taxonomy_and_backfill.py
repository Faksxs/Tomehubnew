"""
One-time Oracle migration:
- Create/seed TOMEHUB_BOOK_CATEGORY_TAXONOMY (12 canonical UI categories)
- Rename legacy category tag "Siyaset Bilimi" -> "İnceleme ve Araştırma" in TOMEHUB_LIBRARY_ITEMS.TAGS_JSON
- Recompute CATEGORY_JSON from TAGS_JSON using canonical category taxonomy (BOOK items)

Safe defaults:
- Dry-run by default
- Apply only with --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from infrastructure.db_manager import DatabaseManager, safe_read_clob  # noqa: E402
from services.category_taxonomy_service import (  # noqa: E402
    BOOK_CATEGORIES,
    extract_book_categories_from_tags,
    replace_legacy_category_tag,
)

LIB_TABLE = "TOMEHUB_LIBRARY_ITEMS"
TAX_TABLE = "TOMEHUB_BOOK_CATEGORY_TAXONOMY"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed book category taxonomy and backfill CATEGORY_JSON from TAGS_JSON")
    p.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    p.add_argument("--report", help="Optional JSON report path")
    return p.parse_args()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _default_report_path(dry_run: bool) -> str:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    mode = "DRY_RUN" if dry_run else "APPLY"
    return os.path.join(
        ROOT,
        "..",
        "..",
        "documentation",
        "reports",
        f"BOOK_CATEGORY_TAXONOMY_BACKFILL_{mode}_{date_str}.json",
    )


def _columns(cur, table_name: str) -> set[str]:
    cur.execute(
        """
        SELECT COLUMN_NAME
        FROM USER_TAB_COLUMNS
        WHERE TABLE_NAME = :p_table
        """,
        {"p_table": table_name.upper()},
    )
    return {str(r[0]).upper() for r in cur.fetchall()}


def _table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT 1 FROM USER_TABLES WHERE TABLE_NAME = :t", {"t": table_name.upper()})
    return cur.fetchone() is not None


def _scalar(cur, sql: str, binds: dict[str, Any] | None = None) -> int:
    cur.execute(sql, binds or {})
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    return str(v)


def _parse_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = safe_read_clob(value) if not isinstance(value, str) else value
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for x in data:
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out


def _normalize_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for t in tags:
        fixed = replace_legacy_category_tag(t)
        key = fixed.lower()
        if not fixed or key in seen:
            continue
        seen.add(key)
        out.append(fixed)
    return out


def _ensure_tax_table(cur) -> bool:
    created = False
    if _table_exists(cur, TAX_TABLE):
        return created
    cur.execute(
        f"""
        CREATE TABLE {TAX_TABLE} (
            CATEGORY_NAME VARCHAR2(100) NOT NULL,
            DISPLAY_ORDER NUMBER NOT NULL,
            IS_ACTIVE NUMBER(1) DEFAULT 1 NOT NULL,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            CONSTRAINT PK_TH_BOOK_CAT_TAX PRIMARY KEY (CATEGORY_NAME),
            CONSTRAINT CHK_TH_BOOK_CAT_ACTIVE CHECK (IS_ACTIVE IN (0,1))
        )
        """
    )
    created = True
    return created


def main() -> int:
    args = _parse_args()
    dry_run = not bool(args.execute)
    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "dry_run": dry_run,
        "steps": [],
        "precheck": {},
        "actions": {},
        "postcheck": {},
        "errors": [],
    }

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            lib_cols = _columns(cur, LIB_TABLE)
            report["precheck"]["library_columns"] = sorted(lib_cols)
            report["precheck"]["has_tags_json"] = "TAGS_JSON" in lib_cols
            report["precheck"]["has_category_json"] = "CATEGORY_JSON" in lib_cols
            report["precheck"]["legacy_siyaset_tag_rows_like"] = 0
            if "TAGS_JSON" in lib_cols:
                report["precheck"]["legacy_siyaset_tag_rows_like"] = _scalar(
                    cur,
                    f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE ITEM_TYPE='BOOK' AND TAGS_JSON IS NOT NULL AND INSTR(TAGS_JSON, 'Siyaset Bilimi') > 0",
                )

            if not {"TAGS_JSON", "CATEGORY_JSON"}.issubset(lib_cols):
                raise RuntimeError("TAGS_JSON and CATEGORY_JSON columns are required in TOMEHUB_LIBRARY_ITEMS.")

            created_tax = False
            if not dry_run:
                created_tax = _ensure_tax_table(cur)
                report["actions"]["taxonomy_table_created"] = created_tax
                for idx, category in enumerate(BOOK_CATEGORIES, start=1):
                    cur.execute(
                        f"""
                        MERGE INTO {TAX_TABLE} t
                        USING (SELECT :p_name AS CATEGORY_NAME FROM DUAL) src
                        ON (t.CATEGORY_NAME = src.CATEGORY_NAME)
                        WHEN MATCHED THEN
                          UPDATE SET DISPLAY_ORDER = :p_ord, IS_ACTIVE = 1, UPDATED_AT = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                          INSERT (CATEGORY_NAME, DISPLAY_ORDER, IS_ACTIVE, CREATED_AT, UPDATED_AT)
                          VALUES (:p_name, :p_ord, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                        {"p_name": category, "p_ord": idx},
                    )

            cur.execute(
                f"""
                SELECT ITEM_ID, FIREBASE_UID, TAGS_JSON, CATEGORY_JSON
                FROM {LIB_TABLE}
                WHERE ITEM_TYPE = 'BOOK'
                  AND NVL(IS_DELETED, 0) = 0
                """
            )
            rows = cur.fetchall()
            report["precheck"]["book_rows_scanned"] = len(rows)

            planned = []
            for item_id, uid, tags_json, category_json in rows:
                tags = _parse_json_list(tags_json)
                current_categories = _parse_json_list(category_json)
                norm_tags = _normalize_tags(tags)
                derived_categories = extract_book_categories_from_tags(norm_tags)
                if norm_tags != tags or derived_categories != current_categories:
                    planned.append(
                        {
                            "item_id": str(item_id),
                            "firebase_uid": str(uid),
                            "old_tags": tags,
                            "new_tags": norm_tags,
                            "old_categories": current_categories,
                            "new_categories": derived_categories,
                        }
                    )

            report["precheck"]["rows_needing_update"] = len(planned)
            report["precheck"]["sample_updates"] = planned[:10]

            if dry_run:
                report["steps"].append("Dry-run only; no DDL/DML committed.")
                conn.rollback()
            else:
                updated_rows = 0
                legacy_tag_renamed_rows = 0
                for row in planned:
                    old_tags = row["old_tags"]
                    new_tags = row["new_tags"]
                    if old_tags != new_tags and any(t == "Siyaset Bilimi" for t in old_tags):
                        legacy_tag_renamed_rows += 1
                    cur.execute(
                        f"""
                        UPDATE {LIB_TABLE}
                        SET TAGS_JSON = TO_CLOB(:p_tags),
                            CATEGORY_JSON = TO_CLOB(:p_cats),
                            UPDATED_AT = CURRENT_TIMESTAMP
                        WHERE ITEM_ID = :p_item_id
                          AND FIREBASE_UID = :p_uid
                        """,
                        {
                            "p_tags": json.dumps(new_tags, ensure_ascii=False),
                            "p_cats": json.dumps(row["new_categories"], ensure_ascii=False),
                            "p_item_id": row["item_id"],
                            "p_uid": row["firebase_uid"],
                        },
                    )
                    updated_rows += int(cur.rowcount or 0)

                conn.commit()
                report["actions"]["rows_updated"] = updated_rows
                report["actions"]["legacy_siyaset_tag_renamed_rows"] = legacy_tag_renamed_rows
                report["steps"].append("Seeded taxonomy table and backfilled TAGS_JSON/CATEGORY_JSON for BOOK rows.")

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            report["postcheck"]["taxonomy_exists"] = _table_exists(cur, TAX_TABLE)
            if report["postcheck"]["taxonomy_exists"]:
                report["postcheck"]["taxonomy_count"] = _scalar(cur, f"SELECT COUNT(*) FROM {TAX_TABLE} WHERE NVL(IS_ACTIVE,1)=1")
                cur.execute(f"SELECT CATEGORY_NAME, DISPLAY_ORDER FROM {TAX_TABLE} ORDER BY DISPLAY_ORDER")
                report["postcheck"]["taxonomy_rows"] = [[str(r[0]), int(r[1])] for r in cur.fetchall()]

            report["postcheck"]["legacy_siyaset_tag_rows_like"] = _scalar(
                cur,
                f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE ITEM_TYPE='BOOK' AND TAGS_JSON IS NOT NULL AND INSTR(TAGS_JSON, 'Siyaset Bilimi') > 0",
            )
            report["postcheck"]["new_inceleme_tag_rows_like"] = _scalar(
                cur,
                f"SELECT COUNT(*) FROM {LIB_TABLE} WHERE ITEM_TYPE='BOOK' AND TAGS_JSON IS NOT NULL AND INSTR(TAGS_JSON, 'İnceleme ve Araştırma') > 0",
            )

    report["finished_at"] = _now_iso()
    out_path = args.report or _default_report_path(dry_run=dry_run)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(report), f, ensure_ascii=False, indent=2)

    print(f"[OK] Report written: {out_path}")
    print(json.dumps(_json_safe(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
