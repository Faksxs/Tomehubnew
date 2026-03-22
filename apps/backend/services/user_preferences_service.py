import json
import logging
from typing import Dict, Any

from infrastructure.db_manager import DatabaseManager, safe_read_clob

logger = logging.getLogger(__name__)

def get_user_preferences(user_id: str) -> Dict[str, Any]:
    """Retrieve user preferences as a dictionary."""
    if not user_id:
        return {}
        
    conn = None
    try:
        conn = DatabaseManager.get_read_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT preferences_json FROM TOMEHUB_USER_PREFERENCES WHERE user_id = :1", [user_id])
            row = cursor.fetchone()
            if row and row[0]:
                raw_json = safe_read_clob(row[0])
                if raw_json:
                    return json.loads(raw_json)
            return {}
    except Exception as e:
        logger.error(f"Error reading user preferences for {user_id}: {e}")
        return {}
    finally:
        if conn:
            conn.close()

def update_user_preferences(user_id: str, prefs: Dict[str, Any]) -> bool:
    """Update user preferences."""
    if not user_id:
        return False
        
    conn = None
    try:
        conn = DatabaseManager.get_write_connection()
        prefs_json = json.dumps(prefs)
        with conn.cursor() as cursor:
            cursor.execute("""
                MERGE INTO TOMEHUB_USER_PREFERENCES dst
                USING (SELECT :1 AS user_id, :2 AS prefs FROM DUAL) src
                ON (dst.user_id = src.user_id)
                WHEN MATCHED THEN UPDATE SET dst.preferences_json = src.prefs, dst.updated_at = CURRENT_TIMESTAMP
                WHEN NOT MATCHED THEN INSERT (user_id, preferences_json) VALUES (src.user_id, src.prefs)
            """, [user_id, prefs_json])
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error updating user preferences for {user_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()
