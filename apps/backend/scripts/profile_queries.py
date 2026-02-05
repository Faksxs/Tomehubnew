
import os
import sys
import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add backend to path for config and db_manager
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BACKEND_DIR)

from infrastructure.db_manager import DatabaseManager
from config import settings

def format_sql(sql: str, length: int = 80) -> str:
    """Truncates and formats SQL for display."""
    clean = " ".join(sql.split())
    if len(clean) > length:
        return clean[:length-3] + "..."
    return clean

def get_profiling_results(minutes: int = 60, min_executions: int = 1, sort_by: str = 'total_time') -> List[Dict[str, Any]]:
    """
    Fetches performance metrics from Oracle's v$sql view.
    """
    results = []
    
    # Assumption: User has SELECT privilege on v$sql (common for DBA/ADMIN role)
    # We filter by parsing_schema_name to keep it relevant to our app
    query = """
    SELECT 
        sql_text,
        executions,
        elapsed_time / 1000000 as total_time_sec,
        (elapsed_time / NULLIF(executions, 0)) / 1000000 as avg_time_sec,
        rows_processed,
        buffer_gets,
        (buffer_gets / NULLIF(executions, 0)) as avg_buffer_gets,
        last_active_time,
        sql_id
    FROM v$sql
    WHERE parsing_schema_name = :schema
      AND last_active_time >= :since
      AND executions >= :min_exec
      AND sql_text NOT LIKE '%v$sql%'
    ORDER BY 
    """
    
    # Sort mapping
    sort_map = {
        'total_time': 'total_time_sec DESC',
        'avg_time': 'avg_time_sec DESC',
        'executions': 'executions DESC',
        'rows': 'rows_processed DESC',
        'buffer_gets': 'buffer_gets DESC'
    }
    
    query += sort_map.get(sort_by, 'total_time_sec DESC')
    query += " FETCH FIRST 20 ROWS ONLY"

    since_time = datetime.now() - timedelta(minutes=minutes)
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, {
                    "schema": settings.DB_USER.upper(),
                    "since": since_time,
                    "min_exec": min_executions
                })
                
                columns = [col[0].lower() for col in cursor.description]
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
                    
    except Exception as e:
        print(f"Error querying v$sql: {e}")
        # Hint for permission issues
        if "table or view does not exist" in str(e).lower():
            print("\n[!] TIP: Ensure your DB user has 'SELECT ANY DICTIONARY' or direct access to 'v$sql'.")
            
    return results

def print_report(data: List[Dict[str, Any]], minutes: int):
    """Prints a clear, formatted report to the console."""
    if not data:
        print("\n[!] No SQL metrics found in the specified window.")
        return

    print("\n" + "="*120)
    print(f" TOMEHUB QUERY PROFILE REPORT (Last {minutes} minutes)")
    print("="*120)
    
    # Header
    header = f"{'SQL_ID':<15} | {'Execs':<8} | {'Total(s)':<10} | {'Avg(s)':<8} | {'Rows':<10} | {'BuffGets':<10} | {'SQL Snippet'}"
    print(header)
    print("-" * 120)

    for row in data:
        line = (
            f"{row['sql_id']:<15} | "
            f"{row['executions']:<8} | "
            f"{row['total_time_sec']:<10.2f} | "
            f"{row['avg_time_sec']:<8.3f} | "
            f"{row['rows_processed']:<10} | "
            f"{row['buffer_gets']:<10} | "
            f"{format_sql(row['sql_text'])}"
        )
        print(line)
    
    print("-" * 120)
    print(f"Total bottled queries: {len(data)}")
    print("Elapsed time is in seconds. Buffer gets are a proxy for CPU/IO load.")
    print("="*120 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TomeHub SQL Profiler using Oracle v$sql")
    parser.add_argument("--minutes", type=int, default=60, help="Lookback window in minutes")
    parser.add_argument("--min-exec", type=int, default=1, help="Minimum executions to include")
    parser.add_argument("--sort", type=str, default="total_time", 
                        choices=['total_time', 'avg_time', 'executions', 'rows', 'buffer_gets'],
                        help="Metric to sort by")
    
    args = parser.parse_args()
    
    # Mock some env vars if not set for local testing
    if not os.getenv("DB_PASSWORD"):
        print("[!] Warning: DB_PASSWORD not found. This script will fail if connection is needed.")
    
    print(f"Starting profiling (Sorting by {args.sort})...")
    metrics = get_profiling_results(minutes=args.minutes, min_executions=args.min_exec, sort_by=args.sort)
    print_report(metrics, args.minutes)
