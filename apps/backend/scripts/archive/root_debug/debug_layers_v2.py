
import sys
import os
import asyncio
import logging
from pprint import pprint

# --- CRITICAL: FIX PATHS FIRST ---
# Add the 'apps/backend' directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Now we can import from 'services', 'infrastructure', etc.
try:
    from services.flow_service import get_flow_service
    from services.search_system.orchestrator import SearchOrchestrator
    from services.embedding_service import get_embedding
    from infrastructure.db_manager import DatabaseManager
except ImportError as e:
    print(f"❌ CRITICAL IMPORT ERROR: {e}")
    # Print sys.path to debug
    print("DEBUG: sys.path:")
    for p in sys.path:
        print(f" - {p}")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_layers():
    print("--- STARTING DEBUG ---")
    
    test_uid = None

    # 1. Test Database Connection & Get User
    try:
        # Initialize Pool manually for CLI script
        DatabaseManager.init_pool()
        
        with DatabaseManager.get_connection() as conn:
            print("[OK] Database Connection: OK")
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
                count = cursor.fetchone()[0]
                print(f"[INFO] Total Content Count: {count}")
                
                # Fetch a user who has content
                cursor.execute("SELECT DISTINCT FIREBASE_UID FROM TOMEHUB_CONTENT FETCH FIRST 1 ROW ONLY")
                row = cursor.fetchone()
                if row:
                    test_uid = row[0]
                    print(f"[INFO] Using Test UID from DB: {test_uid}")
                else:
                    print("[WARN] No users found in content table. System is empty.")
    except Exception as e:
        print(f"[ERROR] Database Connection Failed: {e}")
        return

    if not test_uid:
        print("[ERROR] Cannot proceed without a test UID.")
        return

    # 2. Test Layer 4 (Flow Service)
    print("\n--- TESTING LAYER 4 (FLOW) ---")
    try:
        flow_service = get_flow_service()
        print("[OK] FlowService Initialized")
        
        # Determine anchor
        initial_cards, label, sid = flow_service.start_session(
            firebase_uid=test_uid,
            anchor_type='topic',
            anchor_id='Knowledge Discovery',
            mode='FOCUS'
        )
        print(f"[OK] Start Session Result: {len(initial_cards)} cards returned.")
        if initial_cards:
            print(f"   First Card: {initial_cards[0].title} ({initial_cards[0].chunk_id})")
        else:
            print("[WARN] Returned 0 cards in start_session.")
            
        # Test Batch Fetch specifically
        if initial_cards:
             print("[INFO] Testing Batch Metadata Fetch (New Optimization)...")
             chunk_ids = [c.chunk_id for c in initial_cards]
             meta = flow_service._get_candidate_metadata_batch(test_uid, chunk_ids)
             print(f"   Batch Meta Result Size: {len(meta)}")
             # print(meta) # Too verbose
             
    except Exception as e:
        print(f"[ERROR] Layer 4 Error: {e}")
        import traceback
        traceback.print_exc()

    # 3. Test Layer 3 (Search Orchestrator)
    print("\n--- TESTING LAYER 3 (SEARCH) ---")
    try:
        orchestrator = SearchOrchestrator(embedding_fn=get_embedding)
        print("[OK] SearchOrchestrator Initialized")
        
        query = "Philosophy"
        print(f"[INFO] Searching for: '{query}'...")
        
        results, meta = orchestrator.search(query, firebase_uid=test_uid, limit=5)
        
        print(f"[OK] Search Returned {len(results)} results.")
        if results:
             print(f"   Top Result: {results[0].get('content', '')[:50]}...")
        else:
             print("[WARN] Search returned 0 results.")

    except Exception as e:
        print(f"[ERROR] Layer 3 Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_layers())
