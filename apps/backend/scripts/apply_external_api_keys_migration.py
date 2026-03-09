import os
import sys


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager


def _split_sql_blocks(sql_text: str) -> list[str]:
    commands: list[str] = []
    current: list[str] = []

    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped == "/":
            if current:
                commands.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)

    if current:
        commands.append("\n".join(current).strip())
    return [cmd for cmd in commands if cmd]


def main() -> int:
    migration_path = os.path.join(BACKEND_DIR, "migrations", "phaseX_external_api_keys.sql")
    if not os.path.exists(migration_path):
        print(f"Migration file not found: {migration_path}")
        return 1

    with open(migration_path, "r", encoding="utf-8") as handle:
        sql_text = handle.read()

    commands = _split_sql_blocks(sql_text)
    if not commands:
        print("No SQL blocks found.")
        return 1

    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                for idx, command in enumerate(commands, start=1):
                    print(f"Executing block {idx}/{len(commands)}")
                    cursor.execute(command)
            conn.commit()
        print("External API key migration applied successfully.")
        return 0
    except Exception as exc:
        print(f"Migration failed: {exc}")
        return 1
    finally:
        DatabaseManager.close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
