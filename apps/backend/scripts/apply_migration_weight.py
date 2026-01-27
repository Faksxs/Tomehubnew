
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
    print("=== Applying DB Migration: Add WEIGHT to TOMEHUB_RELATIONS ===")
    
    # Initialize Pool
    DatabaseManager.init_pool()

    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Add Column
                try:
                    print("Adding WEIGHT column...")
                    cursor.execute("ALTER TABLE TOMEHUB_RELATIONS ADD WEIGHT NUMBER DEFAULT 1.0")
                    print("[OK] Column added.")
                except oracledb.DatabaseError as e:
                    error, = e.args
                    if error.code == 1430: # ORA-01430: column being added already exists in table
                        print("[INFO] Column WEIGHT already exists.")
                    else:
                        print(f"[ERROR] Adding column failed: {e}")
                        # raise e # Don't stop, try to update graph definition anyway
                
                # 2. Re-create Property Graph
                # Property Graphs in Oracle 23ai are metadata objects. 
                # We usually need to DROP and CREATE.
                print("Updating Property Graph definition...")
                
                try:
                    cursor.execute("DROP PROPERTY GRAPH TOMEHUB_GRAPH")
                    print("[OK] Old graph dropped.")
                except oracledb.DatabaseError as e:
                     print(f"[INFO] Drop graph skipped/failed (maybe didn't exist): {e}")

                create_graph_sql = """
                CREATE PROPERTY GRAPH TOMEHUB_GRAPH
                  VERTEX TABLES (
                    TOMEHUB_CONCEPTS
                      KEY (ID)
                      LABEL CONCEPT
                      PROPERTIES (NAME, CONCEPT_TYPE)
                  )
                  EDGE TABLES (
                    TOMEHUB_RELATIONS
                      KEY (ID)
                      SOURCE KEY (SRC_ID) REFERENCES TOMEHUB_CONCEPTS(ID)
                      DESTINATION KEY (DST_ID) REFERENCES TOMEHUB_CONCEPTS(ID)
                      LABEL RELATED_TO
                      PROPERTIES (REL_TYPE, WEIGHT)
                  )
                """
                
                try:
                    cursor.execute(create_graph_sql)
                    print("[OK] New Property Graph created with WEIGHT property.")
                except oracledb.DatabaseError as e:
                    print(f"[ERROR] Create graph failed: {e}")
                    raise e
                    
                conn.commit()
                print("\n=== Migration Successfully Completed ===")
                
    except Exception as e:
        print(f"\n[FATAL] Migration failed: {e}")

if __name__ == "__main__":
    apply_migration()
