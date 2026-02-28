"""
Purge ISBN values from Oracle + Firestore.

Usage:
  python scripts/purge_isbn_everywhere.py --execute
  python scripts/purge_isbn_everywhere.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager  # noqa: E402


def _init_firebase() -> None:
    if firebase_admin._apps:
        return

    cred_path = settings.FIREBASE_CREDENTIALS_PATH
    if cred_path and not os.path.isabs(cred_path):
        cred_path = str((ROOT_DIR / cred_path.lstrip("./\\")).resolve())

    if cred_path and os.path.exists(cred_path):
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    else:
        firebase_admin.initialize_app()


def purge_oracle_isbn(*, execute: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tables": [],
        "tables_scanned": 0,
        "rows_with_isbn_before": 0,
        "rows_cleared": 0,
        "rows_with_isbn_after": 0,
    }

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.TABLE_NAME
                FROM USER_TAB_COLUMNS c
                JOIN USER_TABLES t
                  ON t.TABLE_NAME = c.TABLE_NAME
                WHERE c.COLUMN_NAME = 'ISBN'
                ORDER BY c.TABLE_NAME
                """
            )
            tables = [str(r[0]) for r in cur.fetchall()]

            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE ISBN IS NOT NULL")
                before = int(cur.fetchone()[0] or 0)
                cleared = 0
                if execute and before > 0:
                    cur.execute(f"UPDATE {table} SET ISBN = NULL WHERE ISBN IS NOT NULL")
                    cleared = int(cur.rowcount or 0)

                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE ISBN IS NOT NULL")
                after = int(cur.fetchone()[0] or 0)

                summary["tables"].append(
                    {
                        "table": table,
                        "before": before,
                        "cleared": cleared,
                        "after": after,
                    }
                )
                summary["tables_scanned"] += 1
                summary["rows_with_isbn_before"] += before
                summary["rows_cleared"] += cleared
                summary["rows_with_isbn_after"] += after

        if execute:
            conn.commit()
        else:
            conn.rollback()

    return summary


def _commit_batch(batch, pending: int) -> int:
    if pending <= 0:
        return 0
    batch.commit()
    return 0


def purge_firestore_isbn(*, execute: bool) -> dict[str, Any]:
    _init_firebase()
    db = firestore.client()

    summary: dict[str, Any] = {
        "users_scanned": 0,
        "items_scanned": 0,
        "items_with_isbn_before": 0,
        "items_isbn_removed": 0,
        "items_with_isbn_after": 0,
    }

    users_iter = db.collection("users").stream()
    batch = db.batch()
    pending = 0

    for user_doc in users_iter:
        summary["users_scanned"] += 1
        items_iter = db.collection("users").document(user_doc.id).collection("items").stream()
        for item_doc in items_iter:
            summary["items_scanned"] += 1
            payload = item_doc.to_dict() or {}
            if "isbn" in payload and payload.get("isbn") is not None:
                summary["items_with_isbn_before"] += 1
                if execute:
                    batch.update(item_doc.reference, {"isbn": firestore.DELETE_FIELD})
                    pending += 1
                    summary["items_isbn_removed"] += 1
                    if pending >= 400:
                        pending = _commit_batch(batch, pending)
                        batch = db.batch()

    if execute and pending > 0:
        pending = _commit_batch(batch, pending)

    # Verify after-state
    for user_doc in db.collection("users").stream():
        items_iter = db.collection("users").document(user_doc.id).collection("items").stream()
        for item_doc in items_iter:
            payload = item_doc.to_dict() or {}
            if payload.get("isbn") is not None:
                summary["items_with_isbn_after"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge ISBN from Oracle and Firestore")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Apply changes")
    mode.add_argument("--dry-run", action="store_true", help="Report only (default)")
    args = parser.parse_args()

    execute = bool(args.execute)

    oracle_summary = purge_oracle_isbn(execute=execute)
    firestore_summary = purge_firestore_isbn(execute=execute)

    report = {
        "execute": execute,
        "oracle": oracle_summary,
        "firestore": firestore_summary,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
