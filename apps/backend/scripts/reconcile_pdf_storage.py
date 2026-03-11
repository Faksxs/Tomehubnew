from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager
from services.object_storage_service import get_bucket_context, list_objects


def _fetch_db_rows(firebase_uid: str | None) -> list[Dict[str, Any]]:
    binds: Dict[str, Any] = {}
    where = [
        "NVL(OBJECT_KEY, '') <> ''",
        "NVL(STORAGE_STATUS, 'STORED') NOT IN ('DELETE_PENDING', 'DELETED')",
    ]
    if firebase_uid:
        where.append("FIREBASE_UID = :p_uid")
        binds["p_uid"] = firebase_uid

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT FIREBASE_UID, BOOK_ID, BUCKET_NAME, OBJECT_KEY, NVL(SIZE_BYTES, 0), NVL(PARSE_STATUS, '')
                FROM TOMEHUB_INGESTED_FILES
                WHERE {" AND ".join(where)}
                ORDER BY FIREBASE_UID, BOOK_ID
                """,
                binds,
            )
            return [
                {
                    "firebase_uid": str(row[0] or ""),
                    "book_id": str(row[1] or ""),
                    "bucket_name": str(row[2] or ""),
                    "object_key": str(row[3] or ""),
                    "size_bytes": int(row[4] or 0),
                    "parse_status": str(row[5] or ""),
                }
                for row in cursor.fetchall()
            ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile PDF storage rows against OCI Object Storage")
    parser.add_argument("--firebase-uid", dest="firebase_uid", help="Filter to a single user")
    args = parser.parse_args()

    rows = _fetch_db_rows(args.firebase_uid)
    ctx = get_bucket_context(rows[0]["bucket_name"] if rows else None)
    prefix = f"users/{args.firebase_uid}/" if args.firebase_uid else "users/"
    bucket_objects = list_objects(ctx["bucket_name"], prefix)

    db_by_key = {str(row["object_key"]): row for row in rows if row.get("object_key")}
    bucket_by_key = {str(obj["name"]): obj for obj in bucket_objects if obj.get("name")}

    missing_in_bucket = [db_by_key[key] for key in sorted(set(db_by_key) - set(bucket_by_key))]
    missing_in_db = [bucket_by_key[key] for key in sorted(set(bucket_by_key) - set(db_by_key)) if "/source/" in key]

    result = {
        "firebase_uid": args.firebase_uid,
        "bucket_name": ctx["bucket_name"],
        "prefix": prefix,
        "db_object_count": len(db_by_key),
        "db_total_bytes": sum(int(row.get("size_bytes") or 0) for row in rows),
        "bucket_object_count": len([name for name in bucket_by_key if "/source/" in name]),
        "bucket_total_bytes": sum(int(obj.get("size") or 0) for obj in bucket_objects if "/source/" in str(obj.get("name") or "")),
        "missing_in_bucket": missing_in_bucket[:50],
        "missing_in_db": missing_in_db[:50],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
