
import os
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def fix_schema():
    print("Initializing DB Pool...")
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Check/Add SEEN_AT to TOMEHUB_FLOW_SEEN
                try:
                    cursor.execute("SELECT seen_at FROM TOMEHUB_FLOW_SEEN FETCH FIRST 1 ROW ONLY")
                    print("✅ SEEN_AT column exists.")
                except Exception as e:
                    err = str(e)
                    if "ORA-00942" in err:  # Table does not exist
                        print("⚠️ TOMEHUB_FLOW_SEEN missing. Creating table...")
                        cursor.execute("""
                            CREATE TABLE TOMEHUB_FLOW_SEEN (
                                id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                                firebase_uid VARCHAR2(255) NOT NULL,
                                session_id VARCHAR2(255) NOT NULL,
                                chunk_id NUMBER NOT NULL,
                                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                        cursor.execute("""
                            CREATE INDEX IDX_FLOW_SEEN_CHECK
                            ON TOMEHUB_FLOW_SEEN (firebase_uid, chunk_id)
                        """)
                        cursor.execute("""
                            CREATE INDEX IDX_FLOW_SEEN_SESSION
                            ON TOMEHUB_FLOW_SEEN (session_id)
                        """)
                        try:
                            cursor.execute("""
                                ALTER TABLE TOMEHUB_FLOW_SEEN
                                ADD CONSTRAINT FK_FLOW_CHUNK
                                FOREIGN KEY (CHUNK_ID) REFERENCES TOMEHUB_CONTENT(ID)
                                ON DELETE CASCADE
                            """)
                        except Exception as fk_err:
                            print(f"ℹ️ FK_FLOW_CHUNK not added (will retry in migration): {fk_err}")
                        conn.commit()
                        print("✅ TOMEHUB_FLOW_SEEN created.")
                    elif "ORA-00904" in err: # Column missing
                        print("⚠️ SEEN_AT missing. Adding it...")
                        cursor.execute("ALTER TABLE TOMEHUB_FLOW_SEEN ADD (seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                        conn.commit()
                        print("✅ SEEN_AT added.")
                    else:
                        print(f"Error checking SEEN_AT: {e}")

                # 2. Check CENTRALITY_SCORE? 
                # We know it's missing. We won't add it now as we don't have data for it.
                # We will just note it.
                try:
                    cursor.execute("SELECT centrality_score FROM TOMEHUB_CONCEPTS FETCH FIRST 1 ROW ONLY")
                    print("✅ CENTRALITY_SCORE exists.")
                except Exception as e:
                    if "ORA-00904" in str(e):
                        print("ℹ️ CENTRALITY_SCORE is missing (Expected). Will update code to ignore it.")
                    else:
                        print(f"Error checking CENTRALITY_SCORE: {e}")
                        
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    fix_schema()
