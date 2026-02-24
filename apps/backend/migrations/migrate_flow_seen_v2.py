"""
Migration: Optimize TOMEHUB_FLOW_SEEN for Layer 4 performance.

Changes:
1. Add composite index (FIREBASE_UID, CHUNK_ID, SEEN_AT DESC) for fast global-seen lookups.
2. Add engagement columns: REACTION_TYPE, STAY_DURATION_MS, DISCOVERED_VIA.
3. All changes are additive (ALTER ADD / CREATE INDEX) — zero risk of data loss.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from infrastructure.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger("migrate_flow_seen")


STEPS = [
    # ── 1. Composite index for fast global-seen check ────────────────────
    (
        "IDX_FLOW_SEEN_GLOBAL",
        """
        CREATE INDEX IDX_FLOW_SEEN_GLOBAL
        ON TOMEHUB_FLOW_SEEN (FIREBASE_UID, CHUNK_ID, SEEN_AT DESC)
        """,
    ),
    # ── 2. Engagement: reaction type (like / skip / dislike / save) ──────
    (
        "ADD REACTION_TYPE",
        """
        ALTER TABLE TOMEHUB_FLOW_SEEN
        ADD (REACTION_TYPE VARCHAR2(20) DEFAULT NULL)
        """,
    ),
    # ── 3. Engagement: dwell time in milliseconds ────────────────────────
    (
        "ADD STAY_DURATION_MS",
        """
        ALTER TABLE TOMEHUB_FLOW_SEEN
        ADD (STAY_DURATION_MS NUMBER DEFAULT NULL)
        """,
    ),
    # ── 4. Engagement: discovery channel ─────────────────────────────────
    (
        "ADD DISCOVERED_VIA",
        """
        ALTER TABLE TOMEHUB_FLOW_SEEN
        ADD (DISCOVERED_VIA VARCHAR2(50) DEFAULT NULL)
        """,
    ),
]


def run_migration():
    DatabaseManager.init_pool()
    success = 0
    skipped = 0
    failed = 0

    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cursor:
            for label, ddl in STEPS:
                try:
                    cursor.execute(ddl)
                    conn.commit()
                    success += 1
                    print(f"  ✅ {label}")
                except Exception as e:
                    err_msg = str(e)
                    # ORA-00955 = name already used (index exists)
                    # ORA-01430 = column already exists
                    if "ORA-00955" in err_msg or "ORA-01430" in err_msg:
                        skipped += 1
                        print(f"  ⏭️  {label} (already exists)")
                    else:
                        failed += 1
                        print(f"  ❌ {label}: {e}")

    print(f"\nMigration complete: {success} applied, {skipped} skipped, {failed} failed.")


if __name__ == "__main__":
    run_migration()
