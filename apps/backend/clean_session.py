import sys
import uuid
sys.path.insert(0, 'c:\\Users\\aksoy\\Desktop\\yeni tomehub\\apps\\backend')
from infrastructure.db_manager import DatabaseManager

UID = "Faksxs"

print(f"Cleaning SEEN history for {UID}...")
with DatabaseManager.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM TOMEHUB_FLOW_SEEN WHERE firebase_uid = :uid", {"uid": UID})
        conn.commit()
        print("Deleted SEEN records.")
        
        # Also clean sessions to force fresh start
        cursor.execute("DELETE FROM TOMEHUB_FLOW_SESSIONS WHERE firebase_uid = :uid", {"uid": UID})
        conn.commit()
        print("Deleted SESSIONS.")

print("Done. Please refresh frontend.")
