"""
Quick diagnostic script for memory profile.
Reads the current DB state and evidence for a given user.
Run from apps/backend:  python scripts/debug_memory_profile.py
"""
import json
import os
import sys

# Ensure the backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.memory_profile_service import (
    _PROFILE_TABLE,
    _safe_json_loads,
    _table_exists,
    collect_memory_evidence,
    ensure_memory_profile_table,
    get_memory_profile,
)

# Use the first user we find, or override below
TARGET_UID = None  # set manually if needed


def main():
    print("=" * 70)
    print("MEMORY PROFILE DIAGNOSTIC")
    print("=" * 70)

    # 1. Check table existence
    ensure_memory_profile_table()
    exists = _table_exists(_PROFILE_TABLE)
    print(f"\n[1] Table {_PROFILE_TABLE} exists: {exists}")
    if not exists:
        print("   ❌ Table does not exist – refresh would have no persistent store.")
        return

    # 2. Find a UID to examine
    uid = TARGET_UID
    if not uid:
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT FIREBASE_UID FROM {_PROFILE_TABLE} FETCH FIRST 1 ROWS ONLY")
                    row = cur.fetchone()
                    if row:
                        uid = row[0]
        except Exception as e:
            print(f"   ⚠ Could not auto-detect UID: {e}")
    if not uid:
        print("   ❌ No user profile found in table. Nothing to diagnose.")
        return
    print(f"\n[2] Testing with FIREBASE_UID = {uid}")

    # 3. Raw DB row
    print(f"\n[3] Raw DB row for {uid}:")
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT PROFILE_SUMMARY, ACTIVE_THEMES, RECURRING_SOURCES,
                           OPEN_QUESTIONS, EVIDENCE_COUNTS, LAST_REFRESHED_AT
                    FROM {_PROFILE_TABLE}
                    WHERE FIREBASE_UID = :p_uid
                    """,
                    {"p_uid": uid},
                )
                row = cur.fetchone()
                if not row:
                    print("   ❌ No row found for this UID.")
                    return

                summary_raw = safe_read_clob(row[0]) or ""
                themes_raw = safe_read_clob(row[1]) if row[1] else ""
                sources_raw = safe_read_clob(row[2]) if row[2] else ""
                questions_raw = safe_read_clob(row[3]) if row[3] else ""
                counts_raw = safe_read_clob(row[4]) if row[4] else ""
                refreshed_at = row[5]

                print(f"   PROFILE_SUMMARY (len={len(summary_raw)}): {summary_raw[:200]}...")
                print(f"   ACTIVE_THEMES raw: '{themes_raw}'")
                print(f"   RECURRING_SOURCES raw: '{sources_raw}'")
                print(f"   OPEN_QUESTIONS raw: '{questions_raw}'")
                print(f"   EVIDENCE_COUNTS raw: '{counts_raw}'")
                print(f"   LAST_REFRESHED_AT: {refreshed_at}")

                # Parse them
                themes = _safe_json_loads(row[1], [])
                sources = _safe_json_loads(row[2], [])
                questions = _safe_json_loads(row[3], [])
                counts = _safe_json_loads(row[4], {})
                print(f"\n   Parsed ACTIVE_THEMES: {themes}")
                print(f"   Parsed RECURRING_SOURCES: {sources}")
                print(f"   Parsed OPEN_QUESTIONS: {questions}")
                print(f"   Parsed EVIDENCE_COUNTS: {counts}")

    except Exception as e:
        print(f"   ❌ DB read failed: {e}")

    # 4. get_memory_profile() result
    print(f"\n[4] get_memory_profile() result:")
    profile = get_memory_profile(uid)
    if profile:
        for k, v in profile.items():
            print(f"   {k}: {v}")
    else:
        print("   ❌ Returned None")

    # 5. collect_memory_evidence
    print(f"\n[5] collect_memory_evidence() for {uid}:")
    evidence = collect_memory_evidence(uid)
    counts_live = evidence.get("counts", {})
    print(f"   Counts: {counts_live}")
    print(f"   Sessions ({len(evidence.get('sessions', []))}):")
    for s in evidence.get("sessions", [])[:2]:
        print(f"     - {s.get('title', 'N/A')[:60]}: summary_len={len(s.get('summary', ''))}")
    print(f"   Messages ({len(evidence.get('messages', []))}):")
    for m in evidence.get("messages", [])[:2]:
        print(f"     - [{m.get('role')}] {m.get('content', '')[:80]}...")
    print(f"   Notes ({len(evidence.get('notes', []))}):")
    for n in evidence.get("notes", [])[:2]:
        print(f"     - [{n.get('content_type')}] {n.get('content', '')[:80]}...")
    print(f"   Reports ({len(evidence.get('reports', []))}):")
    for r in evidence.get("reports", [])[:2]:
        print(f"     - book_id={r.get('book_id')}: {r.get('summary_text', '')[:80]}...")

    total = sum(int(v or 0) for v in counts_live.values())
    print(f"\n   Total evidence items: {total}")
    if total == 0:
        print("   ⚠ No evidence found! This explains why counts are all zero.")
        print("   The profile_summary you see may be from a previous refresh when evidence existed.")

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
