
import os
import sys
import oracledb
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

load_dotenv()

TARGET_UID = 'vpq1p0UzcCSLAh1d18WgZZWPBE63' # Original UID
EMAIL_UID = 'aksoyfeth@gmail.com' # Where I moved it to

def reverse_migration():
    print("="*60)
    print("REVERSING MIGRATION")
    print("="*60)
    
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check counts
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": EMAIL_UID})
        email_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": TARGET_UID})
        target_count = cursor.fetchone()[0]
        
        print(f"Count on EMAIL ({EMAIL_UID}): {email_count}")
        print(f"Count on TARGET ({TARGET_UID}): {target_count}")
        
        if email_count > 0:
            print(f"Moving {email_count} items back to {TARGET_UID}...")
            cursor.execute("""
                UPDATE TOMEHUB_CONTENT 
                SET firebase_uid = :p_new_uid 
                WHERE firebase_uid = :p_old_uid
            """, {"p_new_uid": TARGET_UID, "p_old_uid": EMAIL_UID})
            conn.commit()
            print(f"SUCCESS: Moved {cursor.rowcount} rows back.")
        else:
            print("No data on Email to move back.")

if __name__ == "__main__":
    reverse_migration()
