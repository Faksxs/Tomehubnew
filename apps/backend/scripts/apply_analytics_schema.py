
import os
import sys
import oracledb

# Add parent dir to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.db_manager import DatabaseManager
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

def apply_migration():
    print("=== Applying DB Migration: Search Analytics Schema ===")
    
    DatabaseManager.init_pool()

    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. TOMEHUB_SEARCH_LOGS
                try:
                    print("Creating TOMEHUB_SEARCH_LOGS table...")
                    cursor.execute("""
                        CREATE TABLE TOMEHUB_SEARCH_LOGS (
                            ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            FIREBASE_UID VARCHAR2(100) NOT NULL,
                            SESSION_ID VARCHAR2(100),
                            QUERY_TEXT CLOB,
                            INTENT VARCHAR2(50),
                            RRF_WEIGHTS VARCHAR2(100),
                            TOP_RESULT_ID NUMBER,
                            TOP_RESULT_SCORE NUMBER,
                            EXECUTION_TIME_MS NUMBER,
                            TIMESTAMP TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            STRATEGY_DETAILS CLOB
                        )
                    """)
                    print("[OK] TOMEHUB_SEARCH_LOGS created.")
                except oracledb.DatabaseError as e:
                    error, = e.args
                    if error.code == 955: # ORA-00955: name is already used by an existing object
                        print("[INFO] TOMEHUB_SEARCH_LOGS already exists.")
                    else:
                        print(f"[ERROR] Failed to create TOMEHUB_SEARCH_LOGS: {e}")

                # 2. TOMEHUB_FEEDBACK (Check existence and add SEARCH_LOG_ID if missing)
                try:
                    print("Checking TOMEHUB_FEEDBACK table...")
                    # Try to create it first
                    cursor.execute("""
                        CREATE TABLE TOMEHUB_FEEDBACK (
                            ID NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                            FIREBASE_UID VARCHAR2(100) NOT NULL,
                            SEARCH_LOG_ID NUMBER,
                            QUERY_TEXT CLOB,
                            GENERATED_ANSWER CLOB,
                            RATING NUMBER(1),
                            FEEDBACK_TEXT CLOB,
                            CONTEXT_BOOK_ID VARCHAR2(100),
                            TIMESTAMP TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT fk_search_log FOREIGN KEY (SEARCH_LOG_ID) REFERENCES TOMEHUB_SEARCH_LOGS(ID)
                        )
                    """)
                    print("[OK] TOMEHUB_FEEDBACK created.")
                except oracledb.DatabaseError as e:
                    error, = e.args
                    if error.code == 955: # Table exists
                        print("[INFO] TOMEHUB_FEEDBACK exists. Checking for SEARCH_LOG_ID column...")
                        # Check if column exists, if not add it
                        try:
                            cursor.execute("ALTER TABLE TOMEHUB_FEEDBACK ADD SEARCH_LOG_ID NUMBER")
                            cursor.execute("ALTER TABLE TOMEHUB_FEEDBACK ADD CONSTRAINT fk_search_log FOREIGN KEY (SEARCH_LOG_ID) REFERENCES TOMEHUB_SEARCH_LOGS(ID)")
                            print("[OK] Added SEARCH_LOG_ID column and FK constraint.")
                        except oracledb.DatabaseError as e2:
                            err2, = e2.args
                            if err2.code == 1430: # Column exists
                                print("[INFO] SEARCH_LOG_ID column already exists.")
                            else:
                                print(f"[WARNING] Could not add SEARCH_LOG_ID: {e2}")
                    else:
                        print(f"[ERROR] Failed to create TOMEHUB_FEEDBACK: {e}")

                conn.commit()
                print("\n=== Analytics Schema Applied ===")
                
    except Exception as e:
        print(f"\n[FATAL] Migration failed: {e}")

if __name__ == "__main__":
    apply_migration()
