import io
import sys
from datetime import datetime
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager
from config import settings

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv('.env')

def purge_chat_messages():
    days = settings.CHAT_RETENTION_DAYS
    print(f"[INFO] Purging chat messages older than {days} days...")
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Delete old messages
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_CHAT_MESSAGES
                    WHERE CREATED_AT < (SYSDATE - :p_days)
                    """,
                    {"p_days": days}
                )
                deleted_messages = cursor.rowcount

                # Optional: delete empty sessions older than retention window
                cursor.execute(
                    """
                    DELETE FROM TOMEHUB_CHAT_SESSIONS s
                    WHERE s.UPDATED_AT < (SYSDATE - :p_days)
                      AND NOT EXISTS (
                        SELECT 1 FROM TOMEHUB_CHAT_MESSAGES m
                        WHERE m.SESSION_ID = s.ID
                      )
                    """,
                    {"p_days": days}
                )
                deleted_sessions = cursor.rowcount

            conn.commit()
        print(f"[DONE] Deleted messages: {deleted_messages}, sessions: {deleted_sessions}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    purge_chat_messages()
