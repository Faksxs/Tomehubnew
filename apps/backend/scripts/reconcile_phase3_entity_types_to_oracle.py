#!/usr/bin/env python3
"""
Reconcile Oracle canonical item types against Firestore item types (Phase 3).

Scope:
- Updates `TOMEHUB_LIBRARY_ITEMS.ITEM_TYPE` for overlapping item keys when Firestore type differs.
- Supports BOOK / ARTICLE / WEBSITE / PERSONAL_NOTE only.

Safety:
- Dry-run by default.
- Does not create/delete rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager  # noqa: E402
from models.firestore_sync_models import normalize_and_validate_item  # noqa: E402


SUPPORTED = {"BOOK", "ARTICLE", "WEBSITE", "PERSONAL_NOTE"}


@dataclass
class UserFixSummary:
    uid: str
    scanned_fs_items: int
    comparable_keys: int
    mismatches: int
    updated: int
    failed_norm: int


def _list_uids(include_test_users: bool) -> list[str]:
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as c:
                c.execute("SELECT DISTINCT FIREBASE_UID FROM TOMEHUB_LIBRARY_ITEMS WHERE FIREBASE_UID IS NOT NULL ORDER BY FIREBASE_UID")
                rows = [str(r[0]) for r in c.fetchall() if r and r[0]]
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass
    return rows if include_test_users else [u for u in rows if not u.startswith("test_")]


def _load_firestore_items(uid: str) -> dict[str, str]:
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError("FIREBASE_READY is false")
    from firebase_admin import firestore

    db = firestore.client()
    docs = db.collection("users").document(uid).collection("items").stream()

    out: dict[str, str] = {}
    failed = 0
    total = 0
    for d in docs:
        total += 1
        try:
            item = normalize_and_validate_item(str(d.id), d.to_dict() or {})
        except Exception:
            failed += 1
            continue
        t = str(item.type).upper()
        if t in SUPPORTED:
            out[item.book_id] = t
    return out, total, failed


def _load_oracle_item_types(uid: str) -> dict[str, str]:
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    "SELECT ITEM_ID, ITEM_TYPE FROM TOMEHUB_LIBRARY_ITEMS WHERE FIREBASE_UID = :u",
                    {"u": uid},
                )
                return {str(r[0]): str(r[1] or "").upper() for r in c.fetchall()}
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def _apply_updates(uid: str, updates: list[tuple[str, str]]) -> int:
    if not updates:
        return 0
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as c:
                c.executemany(
                    """
                    UPDATE TOMEHUB_LIBRARY_ITEMS
                       SET ITEM_TYPE = :p_type,
                           UPDATED_AT = CURRENT_TIMESTAMP
                     WHERE FIREBASE_UID = :p_uid
                       AND ITEM_ID = :p_item_id
                    """,
                    [{"p_type": t, "p_uid": uid, "p_item_id": item_id} for item_id, t in updates],
                )
                rc = int(getattr(c, "rowcount", 0) or 0)
                conn.commit()
                return rc
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def run(execute: bool, include_test_users: bool) -> int:
    print(f"=== Phase 3 Entity Type Reconcile ({'EXECUTE' if execute else 'DRY-RUN'}) ===")
    uids = _list_uids(include_test_users=include_test_users)
    print(f"[INFO] users={len(uids)} include_test_users={include_test_users}")
    total_mismatches = 0
    total_updates = 0
    failed_users = 0
    for uid in uids:
        try:
            fs_types, fs_total, fs_failed = _load_firestore_items(uid)
            ora_types = _load_oracle_item_types(uid)
            comparable = sorted(set(fs_types.keys()) & set(ora_types.keys()))
            updates: list[tuple[str, str]] = []
            mismatch_counter = Counter()
            for item_id in comparable:
                fs_t = fs_types[item_id]
                ora_t = ora_types[item_id]
                if fs_t != ora_t:
                    updates.append((item_id, fs_t))
                    mismatch_counter[f"{ora_t}->{fs_t}"] += 1
            updated = _apply_updates(uid, updates) if execute else 0
            total_mismatches += len(updates)
            total_updates += updated
            print(
                f"[INFO] uid={uid} fs_total={fs_total} failed_norm={fs_failed} comparable={len(comparable)} "
                f"mismatches={len(updates)} updated={updated}"
            )
            if mismatch_counter:
                print(f"       transitions={dict(mismatch_counter)}")
        except Exception as e:
            failed_users += 1
            print(f"[FAIL] uid={uid} err={e}")
    if failed_users:
        print(f"[FAIL] failed_users={failed_users}")
        return 2
    print(f"[OK] total_mismatches={total_mismatches} total_updates={total_updates}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile Oracle item types from Firestore")
    parser.add_argument("--execute", action="store_true", help="Apply updates")
    parser.add_argument("--include-test-users", action="store_true", help="Include test_* users")
    args = parser.parse_args()
    return run(execute=bool(args.execute), include_test_users=bool(args.include_test_users))


if __name__ == "__main__":
    raise SystemExit(main())

