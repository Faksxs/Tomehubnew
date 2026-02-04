import io
import os
import sys

from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)
load_dotenv(os.path.join(backend_dir, ".env"))

import oracledb
from infrastructure.db_manager import DatabaseManager
from utils.tag_utils import prepare_labels

BATCH_SIZE = 200


def _read_clob(val) -> str:
    if val is None:
        return ""
    try:
        return val.read()
    except Exception:
        return str(val)


def backfill():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
                total = cursor.fetchone()[0]
                print(f"TOTAL_ROWS={total}")

                processed = 0
                last_rowid = None

                while True:
                    if last_rowid:
                        cursor.execute(
                            f"""
                            SELECT ROWID, id, categories, tags
                            FROM TOMEHUB_CONTENT
                            WHERE ROWID > :p_last
                            ORDER BY ROWID
                            FETCH FIRST {BATCH_SIZE} ROWS ONLY
                            """,
                            {"p_last": last_rowid},
                        )
                    else:
                        cursor.execute(
                            f"""
                            SELECT ROWID, id, categories, tags
                            FROM TOMEHUB_CONTENT
                            ORDER BY ROWID
                            FETCH FIRST {BATCH_SIZE} ROWS ONLY
                            """
                        )

                    rows = cursor.fetchall()
                    if not rows:
                        break

                    for rid, content_id, categories, tags in rows:
                        cat_list = prepare_labels(categories) if categories else []
                        tag_list = prepare_labels(_read_clob(tags)) if tags else []

                        for raw, norm in cat_list:
                            try:
                                cursor.execute(
                                    """
                                    INSERT INTO TOMEHUB_CONTENT_CATEGORIES (content_id, category, category_norm)
                                    VALUES (:p_cid, :p_cat, :p_norm)
                                    """,
                                    {"p_cid": content_id, "p_cat": raw, "p_norm": norm},
                                )
                            except oracledb.IntegrityError:
                                pass

                        for raw, norm in tag_list:
                            try:
                                cursor.execute(
                                    """
                                    INSERT INTO TOMEHUB_CONTENT_TAGS (content_id, tag, tag_norm)
                                    VALUES (:p_cid, :p_tag, :p_norm)
                                    """,
                                    {"p_cid": content_id, "p_tag": raw, "p_norm": norm},
                                )
                            except oracledb.IntegrityError:
                                pass

                        processed += 1
                        last_rowid = rid

                    conn.commit()
                    print(f"PROCESSED={processed}")

                print("BACKFILL_COMPLETE")
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    backfill()
