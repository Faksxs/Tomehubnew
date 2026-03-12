import os
import sys
from pathlib import Path

import oracledb


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_sql_file.py <sql-file>")
        return 2

    sql_path = Path(sys.argv[1])
    sql_text = sql_path.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql_text.split(";") if part.strip()]

    conn = oracledb.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dsn=os.environ["DB_DSN"],
        config_dir="/app/wallet",
        wallet_location="/app/wallet",
        wallet_password=os.environ["DB_PASSWORD"],
    )
    try:
        cur = conn.cursor()
        for stmt in statements:
            cur.execute(stmt)
        conn.commit()
        print(f"applied:{sql_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
