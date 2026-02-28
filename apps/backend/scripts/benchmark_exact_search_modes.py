import argparse
import os
import sys
import time
from typing import List, Tuple, Dict, Any

# Add backend directory to sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager  # noqa: E402
from utils.text_utils import deaccent_text  # noqa: E402


def _escape_like_literal(value: str, escape_char: str = "\\") -> str:
    raw = str(value or "")
    esc = str(escape_char or "\\")
    raw = raw.replace(esc, esc + esc)
    raw = raw.replace("%", esc + "%")
    raw = raw.replace("_", esc + "_")
    return raw


def _contains_like_pattern(value: str, escape_char: str = "\\") -> str:
    return f"%{_escape_like_literal(value, escape_char=escape_char)}%"


def _build_oracle_text_query(raw_query: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in deaccent_text(raw_query or ""))
    tokens = [t for t in cleaned.split() if len(t) >= 2][:8]
    if not tokens:
        return ""
    return " AND ".join(tokens)


def _run_query(cursor, sql: str, params: Dict[str, Any]) -> Tuple[float, List[Tuple[Any, ...]]]:
    t0 = time.perf_counter()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return elapsed_ms, rows


def benchmark(uid: str, queries: List[str], item_id: str, limit: int) -> int:
    legacy_sql = """
        SELECT c.id, c.item_id, c.page_number
        FROM TOMEHUB_CONTENT_V2 c
        WHERE c.firebase_uid = :p_uid
          AND c.AI_ELIGIBLE = 1
          AND (:p_item_id IS NULL OR c.item_id = :p_item_id)
          AND c.normalized_content LIKE :p_like ESCAPE '\\'
        FETCH FIRST :p_limit ROWS ONLY
    """

    oracle_sql = """
        SELECT c.id, c.item_id, c.page_number, SCORE(1) AS score
        FROM TOMEHUB_CONTENT_V2 c
        WHERE c.firebase_uid = :p_uid
          AND c.AI_ELIGIBLE = 1
          AND (:p_item_id IS NULL OR c.item_id = :p_item_id)
          AND CONTAINS(c.content_chunk, :p_oracle_q, 1) > 0
        ORDER BY SCORE(1) DESC
        FETCH FIRST :p_limit ROWS ONLY
    """

    conn = None
    cursor = None
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        print("query | legacy_ms | legacy_hits | oracle_ms | oracle_hits")
        print("-" * 72)
        for q in queries:
            like_term = _contains_like_pattern(deaccent_text(q))
            oracle_term = _build_oracle_text_query(q)

            legacy_ms, legacy_rows = _run_query(
                cursor,
                legacy_sql,
                {
                    "p_uid": uid,
                    "p_item_id": item_id or None,
                    "p_like": like_term,
                    "p_limit": limit,
                },
            )

            if oracle_term:
                oracle_ms, oracle_rows = _run_query(
                    cursor,
                    oracle_sql,
                    {
                        "p_uid": uid,
                        "p_item_id": item_id or None,
                        "p_oracle_q": oracle_term,
                        "p_limit": limit,
                    },
                )
                oracle_hits = len(oracle_rows)
            else:
                oracle_ms, oracle_hits = 0.0, 0

            print(
                f"{q[:28]:28} | {legacy_ms:8.1f} | {len(legacy_rows):11d} | {oracle_ms:8.1f} | {oracle_hits:10d}"
            )
        return 0
    except Exception as exc:
        print(f"Benchmark failed: {exc}")
        return 2
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark legacy exact search vs Oracle Text exact search")
    parser.add_argument("--uid", required=True, help="firebase_uid")
    parser.add_argument("--item-id", default="", help="optional item_id scope")
    parser.add_argument("--queries", required=True, help="comma-separated query list")
    parser.add_argument("--limit", type=int, default=40, help="max rows per query")
    args = parser.parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    if not queries:
        print("No queries provided.")
        return 1
    return benchmark(args.uid, queries, args.item_id, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
