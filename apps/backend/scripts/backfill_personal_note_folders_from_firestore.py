"""
One-time backfill for Firestore personal note folders -> Oracle TOMEHUB_PERSONAL_NOTE_FOLDERS.

Safety defaults:
- dry-run by default (no writes unless --execute)
- insert-only by default (existing Oracle folders are not overwritten)
- supports single UID or all users

Examples:
  python scripts/backfill_personal_note_folders_from_firestore.py --firebase-uid <UID>
  python scripts/backfill_personal_note_folders_from_firestore.py --firebase-uid <UID> --execute
  python scripts/backfill_personal_note_folders_from_firestore.py --all-users --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any, Dict, Iterable

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import settings  # noqa: E402
from services.library_service import (  # noqa: E402
    ensure_personal_note_folders_table,
    list_personal_note_folders,
    upsert_personal_note_folder,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill Firestore personalNoteFolders to Oracle")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--firebase-uid", help="Target Firebase UID")
    grp.add_argument("--all-users", action="store_true", help="Backfill all users under users/*")
    p.add_argument("--execute", action="store_true", help="Perform writes (default: dry-run)")
    p.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Update Oracle folder rows even if same folder id already exists (default: insert-only)",
    )
    p.add_argument(
        "--report",
        help="Optional JSON report output path (default under documentation/reports)",
    )
    p.add_argument(
        "--limit-users",
        type=int,
        default=0,
        help="Optional cap when using --all-users (0 = no cap)",
    )
    return p.parse_args()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _default_report_path(dry_run: bool) -> str:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    mode = "DRY_RUN" if dry_run else "APPLY"
    return os.path.join(
        ROOT,
        "..",
        "..",
        "documentation",
        "reports",
        f"PERSONAL_NOTE_FOLDERS_BACKFILL_{mode}_{date_str}.json",
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        return str(value)
    except Exception:
        return None


def _normalize_folder(doc_id: str, raw: Dict[str, Any]) -> dict[str, Any] | None:
    folder_id = str(doc_id or "").strip()
    if not folder_id:
        return None

    name = str(raw.get("name") or "").strip()
    if not name:
        # Skip malformed docs instead of creating unnamed folders.
        return None

    category = str(raw.get("category") or "PRIVATE").strip().upper()
    if category not in {"PRIVATE", "DAILY", "IDEAS"}:
        category = "PRIVATE"

    order = raw.get("order", raw.get("display_order", 0))
    try:
        order = int(order)
    except Exception:
        order = 0

    created_at = raw.get("createdAt")
    updated_at = raw.get("updatedAt")
    # Keep raw timestamps in payload for future compatibility (service ignores currently).
    payload = {
        "id": folder_id,
        "name": name,
        "category": category,
        "order": order,
    }
    if created_at is not None:
        payload["createdAt"] = created_at
    if updated_at is not None:
        payload["updatedAt"] = updated_at
    return payload


def _iter_target_uids_from_all_sources(fs_db, *, limit_users: int) -> Iterable[str]:
    """
    Discover UIDs safely even when users/{uid} parent docs do not exist.
    We rely on collection_group(personalNoteFolders), then fall back to users collection docs.
    """
    seen: set[str] = set()
    count = 0
    try:
        for doc in fs_db.collection_group("personalNoteFolders").stream():
            parent_doc = getattr(getattr(doc.reference, "parent", None), "parent", None)
            uid = str(getattr(parent_doc, "id", "") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            yield uid
            count += 1
            if limit_users and count >= limit_users:
                return
    except Exception:
        # Fall through to root users collection discovery.
        pass

    if limit_users and count >= limit_users:
        return

    for user_doc in fs_db.collection("users").stream():
        uid = str(user_doc.id or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        yield uid
        count += 1
        if limit_users and count >= limit_users:
            return


def main() -> int:
    args = _parse_args()
    dry_run = not bool(args.execute)
    target_uid = str(args.firebase_uid or "").strip() or None

    if not bool(getattr(settings, "FIREBASE_READY", False)):
        print("[ERROR] FIREBASE_READY is false. Configure Firebase Admin credentials first.")
        return 2

    from firebase_admin import firestore  # noqa: E402

    ensure_personal_note_folders_table()
    fs_db = firestore.client()

    report: dict[str, Any] = {
        "started_at": _now_iso(),
        "dry_run": dry_run,
        "overwrite_existing": bool(args.overwrite_existing),
        "target": {"firebase_uid": target_uid, "all_users": bool(args.all_users)},
        "summary": {
            "users_scanned": 0,
            "users_with_folder_docs": 0,
            "folder_docs_seen": 0,
            "valid_folder_docs": 0,
            "invalid_folder_docs": 0,
            "oracle_existing_before": 0,
            "insert_candidates": 0,
            "update_candidates": 0,
            "inserted": 0,
            "updated": 0,
            "skipped_existing": 0,
            "errors": 0,
        },
        "users": [],
        "errors": [],
    }

    if target_uid:
        target_uids: Iterable[str] = [target_uid]
    else:
        target_uids = _iter_target_uids_from_all_sources(fs_db, limit_users=int(args.limit_users or 0))

    for uid in target_uids:
        user_entry: dict[str, Any] = {
            "firebase_uid": uid,
            "folder_docs_seen": 0,
            "valid_folder_docs": 0,
            "invalid_folder_docs": 0,
            "oracle_existing_before": 0,
            "insert_candidates": 0,
            "update_candidates": 0,
            "inserted": 0,
            "updated": 0,
            "skipped_existing": 0,
            "invalid_examples": [],
            "error": None,
        }
        report["summary"]["users_scanned"] += 1

        try:
            fs_docs = list(
                fs_db.collection("users")
                .document(uid)
                .collection("personalNoteFolders")
                .stream()
            )
            user_entry["folder_docs_seen"] = len(fs_docs)
            report["summary"]["folder_docs_seen"] += len(fs_docs)
            if not fs_docs:
                report["users"].append(user_entry)
                continue

            report["summary"]["users_with_folder_docs"] += 1
            oracle_existing = {str(f["id"]): f for f in list_personal_note_folders(uid)}
            user_entry["oracle_existing_before"] = len(oracle_existing)
            report["summary"]["oracle_existing_before"] += len(oracle_existing)

            for doc in fs_docs:
                raw = doc.to_dict() or {}
                normalized = _normalize_folder(str(doc.id), raw)
                if not normalized:
                    user_entry["invalid_folder_docs"] += 1
                    report["summary"]["invalid_folder_docs"] += 1
                    if len(user_entry["invalid_examples"]) < 5:
                        user_entry["invalid_examples"].append(
                            {"doc_id": str(doc.id), "raw_keys": list((raw or {}).keys())}
                        )
                    continue

                user_entry["valid_folder_docs"] += 1
                report["summary"]["valid_folder_docs"] += 1

                exists = normalized["id"] in oracle_existing
                if exists and not args.overwrite_existing:
                    user_entry["skipped_existing"] += 1
                    report["summary"]["skipped_existing"] += 1
                    continue

                if exists:
                    user_entry["update_candidates"] += 1
                    report["summary"]["update_candidates"] += 1
                else:
                    user_entry["insert_candidates"] += 1
                    report["summary"]["insert_candidates"] += 1

                if not dry_run:
                    upsert_personal_note_folder(uid, normalized["id"], normalized)
                    if exists:
                        user_entry["updated"] += 1
                        report["summary"]["updated"] += 1
                    else:
                        user_entry["inserted"] += 1
                        report["summary"]["inserted"] += 1

        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            user_entry["error"] = msg
            report["summary"]["errors"] += 1
            report["errors"].append({"firebase_uid": uid, "error": msg})

        report["users"].append(user_entry)

    report["finished_at"] = _now_iso()
    report_path = args.report or _default_report_path(dry_run=dry_run)
    os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(report), f, ensure_ascii=False, indent=2)

    print(f"[DONE] dry_run={dry_run} report={report_path}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report["errors"]:
        print("[WARN] errors:")
        for err in report["errors"][:10]:
            print(" -", err["firebase_uid"], err["error"])
    return 0 if report["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
