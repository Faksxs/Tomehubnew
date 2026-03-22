import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    logger.info("Initializing DB Pool...")
    DatabaseManager.init_pool()
    conn = DatabaseManager.get_write_connection()
    try:
        with conn.cursor() as cursor:
            # Check if table exists
            cursor.execute("""
                SELECT count(*) FROM user_tables WHERE table_name = 'TOMEHUB_USER_PREFERENCES'
            """)
            if cursor.fetchone()[0] == 0:
                logger.info("Creating TOMEHUB_USER_PREFERENCES table...")
                cursor.execute("""
                    CREATE TABLE TOMEHUB_USER_PREFERENCES (
                        user_id VARCHAR2(100) PRIMARY KEY,
                        preferences_json CLOB,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("Table TOMEHUB_USER_PREFERENCES created successfully.")
            else:
                logger.info("Table TOMEHUB_USER_PREFERENCES already exists.")
    except Exception as e:
        logger.error(f"Error applying migration: {e}")
    finally:
        conn.close()
        DatabaseManager.close_pool()

if __name__ == "__main__":
    main()
