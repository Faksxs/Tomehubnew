"""
Sync active Firestore items that are missing in Oracle for one user.

Safety defaults:
- dry-run is default
- execute mode requires explicit --execute
- strict schema validation + quarantine logging are always active

Usage:
  python scripts/sync_missing_items_to_oracle.py --firebase-uid <UID>
  python scripts/sync_missing_items_to_oracle.py --firebase-uid <UID> --execute
"""

from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.firestore_sync_service import (  # noqa: E402
    get_firestore_oracle_sync_status,
    start_firestore_oracle_sync_async,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync missing Firestore items to Oracle")
    parser.add_argument("--firebase-uid", required=True, help="Target Firebase UID")
    parser.add_argument("--execute", action="store_true", help="Run actual write operations (default: dry-run)")
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Optional cap for missing item processing (0 means all missing)",
    )
    parser.add_argument(
        "--embedding-rpm-cap",
        type=int,
        default=30,
        help="Embedding rate cap (requests per minute) for backfill",
    )
    parser.add_argument(
        "--embedding-unit-cost-usd",
        type=float,
        default=0.00002,
        help="Estimated cost per embedding call for cost projection",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Status polling interval in seconds",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    uid = str(args.firebase_uid or "").strip()
    if not uid:
        print("[ERROR] firebase uid required")
        return 2

    dry_run = not bool(args.execute)
    status = start_firestore_oracle_sync_async(
        scope_uid=uid,
        dry_run=dry_run,
        max_items=int(args.max_items),
        embedding_rpm_cap=int(args.embedding_rpm_cap),
        embedding_unit_cost_usd=float(args.embedding_unit_cost_usd),
    )
    print(f"[INFO] job_id={status.get('job_id')} uid={uid} dry_run={dry_run}")

    while True:
        current = get_firestore_oracle_sync_status()
        print(
            "[STATUS]",
            f"running={current.get('running')}",
            f"processed={current.get('processed')}",
            f"synced={current.get('synced')}",
            f"failed={current.get('failed')}",
            f"quarantined={current.get('quarantined')}",
            f"remaining_missing={current.get('remaining_missing')}",
            f"embed_calls={current.get('embedding_calls_total')}",
            f"embed_cost_usd={current.get('embedding_cost_estimate')}",
        )
        if not current.get("running"):
            if dry_run:
                print("[DONE] Dry-run completed.")
                return 0
            remaining = current.get("remaining_missing")
            if isinstance(remaining, int) and remaining == 0 and int(current.get("failed") or 0) == 0:
                print("[DONE] Execute sync completed with zero remaining missing items.")
                return 0
            print("[DONE] Execute sync completed with warnings/errors. Check status/errors.")
            return 1
        time.sleep(max(float(args.poll_interval), 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
