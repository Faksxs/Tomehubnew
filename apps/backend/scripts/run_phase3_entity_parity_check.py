#!/usr/bin/env python3
"""
Phase 3 entity parity check (Firestore items vs Oracle canonical items)

Compares per-user item keys and item-type counts:
- BOOK
- ARTICLE
- WEBSITE
- PERSONAL_NOTE

Uses Firestore as source of truth for parity checks in this phase.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
REPO_ROOT = CURRENT_FILE.parents[3]
BACKEND_DIR = CURRENT_FILE.parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from config import settings  # noqa: E402
from infrastructure.db_manager import DatabaseManager  # noqa: E402
from models.firestore_sync_models import normalize_and_validate_item  # noqa: E402


REPORT_PATH = REPO_ROOT / "documentation" / "reports" / "PHASE3_ENTITY_PARITY_CHECK_2026-02-22.md"
SUPPORTED_ITEM_TYPES = {"BOOK", "ARTICLE", "WEBSITE", "PERSONAL_NOTE"}


@dataclass
class UserParityRow:
    uid: str
    fs_total: int
    ora_total: int
    fs_supported_total: int
    ora_supported_total: int
    missing_in_oracle: int
    extra_in_oracle: int
    fs_by_type: dict[str, int]
    ora_by_type: dict[str, int]
    ora_by_type_on_fs_keys: dict[str, int]
    failed_items: int
    status: str
    note: str = ""


def _list_uids(include_test_users: bool) -> list[str]:
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT DISTINCT FIREBASE_UID
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE FIREBASE_UID IS NOT NULL
                    ORDER BY FIREBASE_UID
                    """
                )
                rows = [str(r[0]) for r in c.fetchall() if r and r[0]]
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass
    return rows if include_test_users else [u for u in rows if not u.startswith("test_")]


def _load_firestore_items(uid: str) -> dict[str, dict]:
    if not bool(getattr(settings, "FIREBASE_READY", False)):
        raise RuntimeError("FIREBASE_READY is false")
    from firebase_admin import firestore

    db = firestore.client()
    docs = db.collection("users").document(uid).collection("items").stream()
    return {str(d.id): (d.to_dict() or {}) for d in docs}


def _load_oracle_items(uid: str) -> dict[str, tuple[str, str]]:
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT ITEM_ID, ITEM_TYPE, ORIGIN_SYSTEM
                    FROM TOMEHUB_LIBRARY_ITEMS
                    WHERE FIREBASE_UID = :p_uid
                    """,
                    {"p_uid": uid},
                )
                return {
                    str(r[0]): (str(r[1] or "").upper(), str(r[2] or "").upper())
                    for r in c.fetchall()
                }
    finally:
        try:
            DatabaseManager.close_pool()
        except Exception:
            pass


def _compute_user_parity(uid: str) -> UserParityRow:
    raw_items = _load_firestore_items(uid)
    ora_items = _load_oracle_items(uid)

    fs_types: dict[str, str] = {}
    fs_counter = Counter()
    failed_items = 0

    for item_id, raw in raw_items.items():
        try:
            item = normalize_and_validate_item(item_id, raw)
        except Exception:
            failed_items += 1
            continue
        t = str(item.type).upper()
        fs_types[item.book_id] = t
        if t in SUPPORTED_ITEM_TYPES:
            fs_counter[t] += 1

    ora_counter = Counter()
    for item_id, (t, _origin) in ora_items.items():
        if t in SUPPORTED_ITEM_TYPES:
            ora_counter[t] += 1

    fs_keys_supported = {k for k, v in fs_types.items() if v in SUPPORTED_ITEM_TYPES}
    ora_keys_supported = {k for k, (v, _origin) in ora_items.items() if v in SUPPORTED_ITEM_TYPES}

    missing = len(fs_keys_supported - ora_keys_supported)
    extra = len(ora_keys_supported - fs_keys_supported)

    ora_counter_on_fs_keys = Counter()
    for item_id in (fs_keys_supported & ora_keys_supported):
        t = ora_items[item_id][0]
        if t in SUPPORTED_ITEM_TYPES:
            ora_counter_on_fs_keys[t] += 1

    extra_oracle_native = 0
    extra_non_native = 0
    for item_id in (ora_keys_supported - fs_keys_supported):
        _t, origin = ora_items[item_id]
        if origin == "ORACLE_NATIVE":
            extra_oracle_native += 1
        else:
            extra_non_native += 1

    status = "OK"
    note = ""
    if failed_items > 0:
        status = "WARN"
        note = f"firestore_validation_failed={failed_items}"
    type_mismatch_on_fs_keys = any(fs_counter.get(t, 0) != ora_counter_on_fs_keys.get(t, 0) for t in SUPPORTED_ITEM_TYPES)
    if missing > 0 or type_mismatch_on_fs_keys:
        status = "FAIL"
        note = (note + "; " if note else "") + "entity parity mismatch"
    elif extra > 0:
        if status == "OK":
            status = "WARN"
        note = (note + "; " if note else "") + (
            f"oracle_extra_items={extra} (oracle_native={extra_oracle_native}, non_native={extra_non_native})"
        )

    return UserParityRow(
        uid=uid,
        fs_total=len(raw_items),
        ora_total=len(ora_items),
        fs_supported_total=sum(fs_counter.values()),
        ora_supported_total=sum(ora_counter.values()),
        missing_in_oracle=missing,
        extra_in_oracle=extra,
        fs_by_type={t: int(fs_counter.get(t, 0)) for t in sorted(SUPPORTED_ITEM_TYPES)},
        ora_by_type={t: int(ora_counter.get(t, 0)) for t in sorted(SUPPORTED_ITEM_TYPES)},
        ora_by_type_on_fs_keys={t: int(ora_counter_on_fs_keys.get(t, 0)) for t in sorted(SUPPORTED_ITEM_TYPES)},
        failed_items=failed_items,
        status=status,
        note=note,
    )


def _write_report(rows: list[UserParityRow], include_test_users: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Phase 3 Entity Parity Check Report",
        "",
        f"- **Generated (UTC):** {ts}",
        f"- **Include test users:** {include_test_users}",
        "",
        "## Summary",
        "",
        "| UID | Status | FS Total | ORA Total | FS Supported | ORA Supported | Missing in Oracle | Extra in Oracle | Failed Items | Note |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r.uid}` | `{r.status}` | {r.fs_total} | {r.ora_total} | {r.fs_supported_total} | {r.ora_supported_total} | "
            f"{r.missing_in_oracle} | {r.extra_in_oracle} | {r.failed_items} | {r.note.replace('|','/')} |"
        )
        lines.append("")
        lines.append(f"- `{r.uid}` FS by type: `{r.fs_by_type}`")
        lines.append(f"- `{r.uid}` ORA by type: `{r.ora_by_type}`")
        lines.append(f"- `{r.uid}` ORA by type (FS-key overlap): `{r.ora_by_type_on_fs_keys}`")
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def run(include_test_users: bool) -> int:
    print("=== Phase 3 Entity Parity Check ===")
    uids = _list_uids(include_test_users=include_test_users)
    print(f"[INFO] users={len(uids)} include_test_users={include_test_users}")

    rows: list[UserParityRow] = []
    failures = 0
    for uid in uids:
        print(f"[RUN] uid={uid}")
        try:
            row = _compute_user_parity(uid)
            rows.append(row)
            print(
                f"[INFO] status={row.status} fs_total={row.fs_total} ora_total={row.ora_total} "
                f"missing={row.missing_in_oracle} extra={row.extra_in_oracle} failed_items={row.failed_items}"
            )
            if row.status == "FAIL":
                failures += 1
        except Exception as e:
            failures += 1
            rows.append(
                UserParityRow(
                    uid=uid,
                    fs_total=0,
                    ora_total=len(_load_oracle_items(uid)),
                    fs_supported_total=0,
                    ora_supported_total=0,
                    missing_in_oracle=0,
                    extra_in_oracle=0,
                    fs_by_type={},
                    ora_by_type={},
                    ora_by_type_on_fs_keys={},
                    failed_items=0,
                    status="FAIL",
                    note=f"exception:{e}",
                )
            )
            print(f"[FAIL] uid={uid} err={e}")

    _write_report(rows, include_test_users=include_test_users)
    print(f"[INFO] Report written: {REPORT_PATH.as_posix()}")
    if failures:
        print(f"[FAIL] Phase 3 entity parity check completed with {failures} failing user(s).")
        return 2
    print("[OK] Phase 3 entity parity check completed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 entity parity check")
    parser.add_argument("--include-test-users", action="store_true", help="Include test_* users")
    args = parser.parse_args()
    return run(include_test_users=bool(args.include_test_users))


if __name__ == "__main__":
    raise SystemExit(main())
