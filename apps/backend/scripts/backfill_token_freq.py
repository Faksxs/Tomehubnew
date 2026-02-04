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

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from utils.text_utils import get_lemma_frequencies

BATCH_SIZE = 150
SOURCE_TYPES = ("PDF", "EPUB", "PDF_CHUNK")


def _count_missing(cursor) -> int:
    placeholders = ",".join([f":st{i}" for i in range(len(SOURCE_TYPES))])
    params = {f"st{i}": st for i, st in enumerate(SOURCE_TYPES)}
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM TOMEHUB_CONTENT
        WHERE token_freq IS NULL
          AND source_type IN ({placeholders})
        """,
        params,
    )
    return cursor.fetchone()[0]


def backfill_token_freq():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                total_rows = _count_missing(cursor)
                print(f"TOTAL_MISSING={total_rows}")
                if total_rows == 0:
                    print("NO_ROWS_TO_UPDATE")
                    return

                processed = 0
                last_rowid = None
                placeholders = ",".join([f":st{i}" for i in range(len(SOURCE_TYPES))])
                params_st = {f"st{i}": st for i, st in enumerate(SOURCE_TYPES)}

                while True:
                    if last_rowid:
                        cursor.execute(
                            f"""
                            SELECT ROWID, content_chunk
                            FROM TOMEHUB_CONTENT
                            WHERE token_freq IS NULL
                              AND source_type IN ({placeholders})
                              AND ROWID > :p_last
                            ORDER BY ROWID
                            FETCH FIRST {BATCH_SIZE} ROWS ONLY
                            """,
                            {**params_st, "p_last": last_rowid},
                        )
                    else:
                        cursor.execute(
                            f"""
                            SELECT ROWID, content_chunk
                            FROM TOMEHUB_CONTENT
                            WHERE token_freq IS NULL
                              AND source_type IN ({placeholders})
                            ORDER BY ROWID
                            FETCH FIRST {BATCH_SIZE} ROWS ONLY
                            """,
                            params_st,
                        )
                    rows = cursor.fetchall()
                    if not rows:
                        break

                    batch_updates = []
                    for rid, content_clob in rows:
                        content = safe_read_clob(content_clob)
                        freqs = get_lemma_frequencies(content)
                        freqs_json = json.dumps(freqs, ensure_ascii=False) if freqs else "{}"
                        batch_updates.append((freqs_json, rid))

                    cursor.executemany(
                        """
                        UPDATE TOMEHUB_CONTENT
                        SET token_freq = :1
                        WHERE ROWID = :2
                        """,
                        batch_updates,
                    )
                    conn.commit()
                    processed += len(batch_updates)
                    last_rowid = rows[-1][0]
                    print(f"PROCESSED={processed}")

                print("BACKFILL_COMPLETE")
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    backfill_token_freq()
