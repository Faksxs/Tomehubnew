import os
import sys
from typing import List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager  # noqa: E402


def _split_sql_blocks(sql_content: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []
    for line in sql_content.splitlines():
        if line.strip() == "/":
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []
            continue
        current.append(line)
    tail = "\n".join(current).strip()
    if tail:
        blocks.append(tail)
    return blocks


def run_migration() -> int:
    migration_path = os.path.join(
        BACKEND_DIR,
        "infrastructure",
        "migrations",
        "phase_odl_shadow_schema.sql",
    )
    if not os.path.exists(migration_path):
        print(f"FATAL: migration file not found: {migration_path}")
        return 1

    with open(migration_path, "r", encoding="utf-8") as f:
        sql_content = f.read()
    blocks = _split_sql_blocks(sql_content)
    if not blocks:
        print("No SQL blocks found.")
        return 1

    conn = None
    cursor = None
    try:
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()
        print(f"Executing {len(blocks)} SQL blocks from {migration_path}")
        for idx, block in enumerate(blocks, start=1):
            print(f"[{idx}/{len(blocks)}] Running block...")
            cursor.execute(block)
        conn.commit()
        print("ODL shadow schema migration applied successfully.")
        return 0
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"Migration failed: {exc}")
        return 2
    finally:
        try:
            if cursor is not None:
                cursor.close()
        except Exception:
            pass
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(run_migration())
