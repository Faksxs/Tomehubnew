import io
import os
import sys
import json
from dotenv import load_dotenv

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)
load_dotenv(os.path.join(backend_dir, ".env"))

from infrastructure.db_manager import DatabaseManager
from utils.text_utils import normalize_text, deaccent_text, get_lemmas

BATCH_SIZE = 150


def _count_placeholders(cursor, column_name: str) -> int:
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE DBMS_LOB.INSTR({column_name}, 'highlight from') > 0
        """
    )
    return cursor.fetchone()[0]


def _count_lemma_empty(cursor) -> int:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE DBMS_LOB.INSTR(LEMMA_TOKENS, '[]') > 0
        """
    )
    return cursor.fetchone()[0]


def backfill_all():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Pre-checks
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
                total_rows = cursor.fetchone()[0]
                print(f"TOTAL_ROWS={total_rows}")
                print(f"PRE_PLACEHOLDER_NORMALIZED={_count_placeholders(cursor, 'NORMALIZED_CONTENT')}")
                print(f"PRE_PLACEHOLDER_DEACCENTED={_count_placeholders(cursor, 'TEXT_DEACCENTED')}")
                print(f"PRE_LEMMA_EMPTY={_count_lemma_empty(cursor)}")

                processed = 0
                last_rowid = None
                while True:
                    if last_rowid:
                        cursor.execute(
                            f"""
                            SELECT ROWID, content_chunk
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
                            SELECT ROWID, content_chunk
                            FROM TOMEHUB_CONTENT
                            ORDER BY ROWID
                            FETCH FIRST {BATCH_SIZE} ROWS ONLY
                            """
                        )
                    rows = cursor.fetchall()
                    if not rows:
                        break

                    batch_updates = []
                    for rid, content_clob in rows:
                        content = content_clob.read() if content_clob else ""
                        norm = normalize_text(content)
                        deacc = deaccent_text(content)
                        lemmas = json.dumps(get_lemmas(content), ensure_ascii=False)
                        batch_updates.append((norm, deacc, lemmas, rid))

                    cursor.executemany(
                        """
                        UPDATE TOMEHUB_CONTENT
                        SET normalized_content = :1,
                            text_deaccented = :2,
                            lemma_tokens = :3
                        WHERE ROWID = :4
                        """,
                        batch_updates,
                    )
                    conn.commit()
                    processed += len(batch_updates)
                    last_rowid = rows[-1][0]
                    print(f"PROCESSED={processed}")

                # Post-checks
                print(f"POST_PLACEHOLDER_NORMALIZED={_count_placeholders(cursor, 'NORMALIZED_CONTENT')}")
                print(f"POST_PLACEHOLDER_DEACCENTED={_count_placeholders(cursor, 'TEXT_DEACCENTED')}")
                print(f"POST_LEMMA_EMPTY={_count_lemma_empty(cursor)}")
                print("BACKFILL_COMPLETE")
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    backfill_all()
