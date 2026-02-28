"""
Purge Firestore application data so Firebase remains Auth-only.

Default scope is `users` (users/* with all nested subcollections).

Usage:
  python scripts/purge_firestore_app_data.py --dry-run
  python scripts/purge_firestore_app_data.py --execute
  python scripts/purge_firestore_app_data.py --execute --scope all
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


def _collect_doc_refs(collection_ref, refs: list, summary: dict[str, Any]) -> None:
    docs = list(collection_ref.stream())
    summary["collections_scanned"] += 1
    summary["documents_scanned"] += len(docs)

    for doc in docs:
        for subcollection in doc.reference.collections():
            _collect_doc_refs(subcollection, refs, summary)
        refs.append(doc.reference)


def _commit_batch(batch, pending: int) -> int:
    if pending <= 0:
        return 0
    batch.commit()
    return 0


def purge_firestore(*, execute: bool, scope: str) -> dict[str, Any]:
    _init_firebase()
    db = firestore.client()

    summary: dict[str, Any] = {
        "scope": scope,
        "execute": execute,
        "collections_scanned": 0,
        "documents_scanned": 0,
        "documents_targeted": 0,
        "documents_deleted": 0,
    }

    refs: list = []

    if scope == "all":
        for root_collection in db.collections():
            _collect_doc_refs(root_collection, refs, summary)
    else:
        _collect_doc_refs(db.collection("users"), refs, summary)

    summary["documents_targeted"] = len(refs)

    if not execute or not refs:
        return summary

    batch = db.batch()
    pending = 0
    for ref in refs:
        batch.delete(ref)
        pending += 1
        summary["documents_deleted"] += 1
        if pending >= 400:
            pending = _commit_batch(batch, pending)
            batch = db.batch()

    if pending > 0:
        _commit_batch(batch, pending)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge Firestore application data (Auth-only posture)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Apply deletions")
    mode.add_argument("--dry-run", action="store_true", help="Report only (default)")
    parser.add_argument(
        "--scope",
        choices=["users", "all"],
        default="users",
        help="`users`: purge users/* tree only, `all`: purge every top-level Firestore collection",
    )
    args = parser.parse_args()

    execute = bool(args.execute)
    report = purge_firestore(execute=execute, scope=args.scope)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

