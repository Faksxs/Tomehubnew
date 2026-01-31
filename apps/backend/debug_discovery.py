
import os
import sys
import logging

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
from services.flow_service import FlowService, FlowSessionState

# Mock state
class MockState:
    def __init__(self, uid, sid):
        self.firebase_uid = uid
        self.session_id = sid

def debug_discovery():
    try:
        DatabaseManager.init_pool()
        
        # Get a valid user
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT FETCH FIRST 1 ROW ONLY")
                uid = cursor.fetchone()[0]
                print(f"Testing with UID: {uid}")
                
        # Create dummy session
        state = MockState(uid, "debug_session_123")
        
        service = FlowService()
        
        print("\n--- Testing _discovery_pivot ---")
        try:
            result = service._discovery_pivot(state)
            if result[0]:
                print(f"SUCCESS: Found pivot: {result[1]} ({result[2]})")
                print(f"Msg: {result[3].message if result[3] else 'None'}")
            else:
                print("FAILURE: _discovery_pivot returned None")
                
            # Debug the queries manually
            print("\n--- Manual Query Check ---")
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check Concepts Query
                    # print("Checking Priority 1 (Epistemic Gaps)...")
                    # cursor.execute("""
                    #     SELECT count(*)
                    #     FROM TOMEHUB_CONCEPTS c
                    #     JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c.id = cc.concept_id
                    #     JOIN TOMEHUB_CONTENT ct ON cc.content_id = ct.id
                    #     WHERE ct.firebase_uid = :p_uid
                    #     AND c.centrality_score > 0.05
                    # """, {"p_uid": uid})
                    # count = cursor.fetchone()[0]
                    # print(f"  > Total high-centrality concepts for user: {count}")
                    
                    # Check Dormant Books Query
                    print("Checking Priority 2 (Dormant)...")
                    cursor.execute("""
                        SELECT count(*)
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                    """, {"p_uid": uid})
                    count = cursor.fetchone()[0]
                    print(f"  > Total content items: {count}")

        except Exception as e:
            print(f"Error calling _discovery_pivot: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"Setup failed: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    debug_discovery()
