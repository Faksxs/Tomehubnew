import argparse
import io
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.text_utils import get_lemmas


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill empty lemma_tokens in TOMEHUB_CONTENT_V2")
    parser.add_argument("--firebase-uid", type=str, default="", help="Optional UID scope")
    parser.add_argument(
        "--content-types",
        type=str,
        default="HIGHLIGHT,INSIGHT,BOOK_CHUNK",
        help="Comma-separated content types to target",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for DB updates")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit (0 = all)")
    parser.add_argument("--execute", action="store_true", help="Write updates (default: dry-run)")
    return parser.parse_args()


def _parse_types(raw: str) -> list[str]:
    out = []
    for part in (raw or "").split(","):
        value = part.strip().upper()
        if value:
            out.append(value)
    return out


def main() -> int:
    args = _parse_args()
    firebase_uid = (args.firebase_uid or "").strip()
    content_types = _parse_types(args.content_types)
    batch_size = max(20, int(args.batch_size or 200))
    limit = max(0, int(args.limit or 0))
    execute = bool(args.execute)

    if not content_types:
        print("No content types provided.")
        return 2

    placeholders = ", ".join(f":p_ct_{i}" for i in range(len(content_types)))
    sql = f"""
        SELECT ROWID, id, content_type, content_chunk
        FROM TOMEHUB_CONTENT_V2
        WHERE (lemma_tokens IS NULL OR DBMS_LOB.SUBSTR(lemma_tokens, 2, 1) = '[]')
          AND content_type IN ({placeholders})
    """
    params = {f"p_ct_{i}": ct for i, ct in enumerate(content_types)}
    if firebase_uid:
        sql += " AND firebase_uid = :p_uid"
        params["p_uid"] = firebase_uid
    sql += " ORDER BY id"
    if limit > 0:
        sql += " FETCH FIRST :p_limit ROWS ONLY"
        params["p_limit"] = limit

    print("=== V2 Lemma Backfill ===")
    print(f"uid_scope={firebase_uid or 'ALL'}")
    print(f"content_types={','.join(content_types)}")
    print(f"mode={'EXECUTE' if execute else 'DRY_RUN'}")

    DatabaseManager.init_pool()
    scanned = 0
    updatable = 0
    still_empty = 0
    updated = 0
    pending = []

    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                total = len(rows)
                print(f"rows_targeted={total}")

                update_sql = """
                    UPDATE TOMEHUB_CONTENT_V2
                    SET lemma_tokens = :1
                    WHERE ROWID = :2
                """

                for rid, row_id, ctype, content_clob in rows:
                    scanned += 1
                    text = safe_read_clob(content_clob)
                    lemma_list = get_lemmas(text)
                    if not lemma_list:
                        still_empty += 1
                        continue
                    updatable += 1
                    lemma_json = json.dumps(lemma_list, ensure_ascii=False)
                    if execute:
                        pending.append((lemma_json, rid))
                        if len(pending) >= batch_size:
                            cursor.executemany(update_sql, pending)
                            conn.commit()
                            updated += len(pending)
                            pending = []
                    if scanned % 500 == 0:
                        print(
                            f"progress scanned={scanned}/{total} updatable={updatable} "
                            f"updated={updated} still_empty={still_empty}"
                        )

                if execute and pending:
                    cursor.executemany(update_sql, pending)
                    conn.commit()
                    updated += len(pending)
                    pending = []

    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass

    print("=== Summary ===")
    print(f"scanned={scanned}")
    print(f"updatable={updatable}")
    print(f"still_empty={still_empty}")
    print(f"updated={updated if execute else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
