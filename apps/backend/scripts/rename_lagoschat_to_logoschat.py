import argparse
import os
import sys
from dataclasses import dataclass
from typing import List

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from config import settings
from infrastructure.db_manager import DatabaseManager


OLD_TEXT = "LagosChat"
NEW_TEXT = "LogosChat"
SUPPORTED_TYPES = ("VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "CLOB", "NCLOB")


@dataclass
class ColumnMatch:
    owner: str
    table_name: str
    column_name: str
    data_type: str
    matched_rows: int
    updated_rows: int = 0


def _q(identifier: str) -> str:
    """Quote Oracle identifiers safely."""
    return '"' + identifier.replace('"', '""') + '"'


def find_candidate_columns(cursor, owner: str):
    cursor.execute(
        """
        SELECT owner, table_name, column_name, data_type
        FROM all_tab_columns
        WHERE owner = :owner
          AND data_type IN ('VARCHAR2', 'NVARCHAR2', 'CHAR', 'NCHAR', 'CLOB', 'NCLOB')
        ORDER BY table_name, column_id
        """,
        {"owner": owner},
    )
    return cursor.fetchall()


def count_matches(cursor, owner: str, table_name: str, column_name: str, data_type: str) -> int:
    q_owner = _q(owner)
    q_table = _q(table_name)
    q_col = _q(column_name)

    if data_type in ("CLOB", "NCLOB"):
        sql = (
            f"SELECT COUNT(*) FROM {q_owner}.{q_table} "
            f"WHERE DBMS_LOB.INSTR({q_col}, :old_text) > 0"
        )
    else:
        sql = f"SELECT COUNT(*) FROM {q_owner}.{q_table} WHERE INSTR({q_col}, :old_text) > 0"

    cursor.execute(sql, {"old_text": OLD_TEXT})
    return int(cursor.fetchone()[0] or 0)


def update_matches(cursor, owner: str, table_name: str, column_name: str, data_type: str) -> int:
    q_owner = _q(owner)
    q_table = _q(table_name)
    q_col = _q(column_name)

    if data_type in ("CLOB", "NCLOB"):
        sql = (
            f"UPDATE {q_owner}.{q_table} "
            f"SET {q_col} = REPLACE({q_col}, :old_text, :new_text) "
            f"WHERE DBMS_LOB.INSTR({q_col}, :old_text) > 0"
        )
    else:
        sql = (
            f"UPDATE {q_owner}.{q_table} "
            f"SET {q_col} = REPLACE({q_col}, :old_text, :new_text) "
            f"WHERE INSTR({q_col}, :old_text) > 0"
        )

    cursor.execute(sql, {"old_text": OLD_TEXT, "new_text": NEW_TEXT})
    return int(cursor.rowcount or 0)


def run(owner: str, apply_changes: bool) -> int:
    conn = None
    cursor = None
    total_matches = 0
    total_updates = 0
    matched_columns: List[ColumnMatch] = []

    print("=== LagosChat -> LogosChat DB Rename Script ===")
    print(f"Owner: {owner}")
    print(f"Mode: {'APPLY' if apply_changes else 'DRY-RUN'}")
    print(f"Search: {OLD_TEXT!r} -> {NEW_TEXT!r}")
    print("")

    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()

        candidates = find_candidate_columns(cursor, owner)
        print(f"Candidate text columns: {len(candidates)}")

        for row in candidates:
            row_owner, table_name, column_name, data_type = row
            try:
                matched_rows = count_matches(cursor, row_owner, table_name, column_name, data_type)
            except Exception as e:
                print(f"[WARN] Count failed on {row_owner}.{table_name}.{column_name}: {e}")
                continue

            if matched_rows <= 0:
                continue

            item = ColumnMatch(
                owner=row_owner,
                table_name=table_name,
                column_name=column_name,
                data_type=data_type,
                matched_rows=matched_rows,
            )
            total_matches += matched_rows

            if apply_changes:
                try:
                    updated_rows = update_matches(cursor, row_owner, table_name, column_name, data_type)
                    item.updated_rows = updated_rows
                    total_updates += updated_rows
                except Exception as e:
                    print(f"[WARN] Update failed on {row_owner}.{table_name}.{column_name}: {e}")
                    continue

            matched_columns.append(item)

        if apply_changes:
            conn.commit()
        else:
            conn.rollback()

        print("")
        if not matched_columns:
            print("No matches found. 0 updates.")
            return 0

        print("Matched columns:")
        for item in matched_columns:
            base = (
                f"- {item.owner}.{item.table_name}.{item.column_name} "
                f"[{item.data_type}] matched_rows={item.matched_rows}"
            )
            if apply_changes:
                base += f", updated_rows={item.updated_rows}"
            print(base)

        print("")
        print(f"Total matched rows: {total_matches}")
        if apply_changes:
            print(f"Total updated rows: {total_updates}")
        else:
            print("Dry-run only. No data changed.")

        return 0
    except Exception as e:
        print(f"[FATAL] Script failed: {e}")
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return 1
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            DatabaseManager.close_pool()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent DB rename tool for LagosChat -> LogosChat."
    )
    parser.add_argument(
        "--owner",
        default=(settings.DB_USER or "ADMIN").upper(),
        help="Oracle schema owner to scan (default: DB_USER).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag, script runs in dry-run mode.",
    )
    args = parser.parse_args()

    return run(owner=args.owner.upper(), apply_changes=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
