from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.chunk_quality_audit_service import analyze_book_chunks


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit stored PDF chunk quality for one user/book.")
    parser.add_argument("--firebase-uid", required=True, help="Owner Firebase UID")
    parser.add_argument("--book-id", required=True, help="Target item/book id")
    parser.add_argument("--title", default="", help="Optional title hint for heuristics")
    parser.add_argument("--author", default="", help="Optional author hint for heuristics")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    rows = []

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, content_chunk, page_number
                FROM TOMEHUB_CONTENT_V2
                WHERE firebase_uid = :p_uid
                  AND item_id = :p_book
                  AND content_type IN ('PDF', 'PDF_CHUNK', 'EPUB', 'BOOK')
                ORDER BY NVL(page_number, 0), NVL(chunk_index, 0), id
                """,
                {"p_uid": args.firebase_uid, "p_book": args.book_id},
            )
            for row in cursor.fetchall():
                rows.append(
                    {
                        "id": row[0],
                        "content_chunk": safe_read_clob(row[1]),
                        "page_number": row[2],
                    }
                )

    report = analyze_book_chunks(rows, title=args.title, author=args.author)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
