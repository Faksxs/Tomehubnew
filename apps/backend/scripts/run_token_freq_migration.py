import os
import sys
import oracledb
from dotenv import load_dotenv

# Load .env first
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import settings


def run_sql_file():
    sql_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations', 'phaseX_content_token_freq.sql')
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    print(f"Executing SQL from: {sql_path}")

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')

    conn = oracledb.connect(
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        dsn=settings.DB_DSN,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=settings.DB_PASSWORD
    )
    cursor = conn.cursor()

    try:
        clean_sql = sql_content.strip()
        if clean_sql.endswith('/'):
            clean_sql = clean_sql[:-1]

        # Split on semicolons and execute non-empty statements
        statements = [s.strip() for s in clean_sql.split(';') if s.strip()]
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
        print("SQL Execution Successful.")
    except Exception as e:
        print(f"SQL Execution Failed: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    run_sql_file()
