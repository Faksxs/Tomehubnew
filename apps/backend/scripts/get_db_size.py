import os
import sys
import logging
import oracledb

# Add backend directory to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from infrastructure.db_manager import DatabaseManager
from config import settings

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def get_database_size():
    """
    Queries the Oracle database for its total size.
    Connects directly to avoid pooling issues in local script execution.
    """
    conn = None
    try:
        # Connect directly
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

        # Query 1: Tablespace Usage
        print("\n--- Tablespace Usage ---")
        try:
            query_ts = """
                SELECT tablespace_name, 
                       ROUND(SUM(bytes) / 1024 / 1024 / 1024, 2) as used_gb
                FROM dba_segments 
                GROUP BY tablespace_name
                ORDER BY used_gb DESC
            """
            cursor.execute(query_ts)
            for row in cursor.fetchall():
                print(f"Tablespace: {row[0]} | Used: {row[1]} GB")
        except Exception as e:
            logger.warning(f"Could not fetch tablespace info: {e}")

        # Query 2: Top 10 Largest Segments (Tables/Indexes)
        print("\n--- Top 10 Largest Segments ---")
        try:
            query_segments = """
                SELECT segment_name, segment_type, 
                       ROUND(bytes / 1024 / 1024, 2) as size_mb
                FROM (
                    SELECT segment_name, segment_type, bytes
                    FROM dba_segments
                    ORDER BY bytes DESC
                )
                WHERE ROWNUM <= 10
            """
            cursor.execute(query_segments)
            for row in cursor.fetchall():
                print(f"{row[1]}: {row[0]} | Size: {row[2]} MB")
        except Exception as e:
            logger.warning(f"Could not fetch top segments: {e}")

        # Query 3: Allocated File Size
        allocated_gb = "Unknown"
        try:
            cursor.execute("SELECT ROUND(SUM(bytes) / 1024 / 1024 / 1024, 2) FROM v$datafile")
            allocated_gb = cursor.fetchone()[0]
        except Exception:
            pass

        # Query 4: Total Used Data
        try:
            cursor.execute("SELECT ROUND(SUM(bytes) / 1024 / 1024 / 1024, 2) FROM dba_segments")
            used_gb = cursor.fetchone()[0]
        except Exception:
            used_gb = "Unknown"

        print("\n--- Summary ---")
        print(f"User: {settings.DB_USER}")
        print(f"Total Allocated (Files): {allocated_gb} GB")
        print(f"Total Actually Used (Segments): {used_gb} GB")
        print("----------------------------------\n")

    except Exception as e:
        logger.error(f"Error checking database size: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    get_database_size()
