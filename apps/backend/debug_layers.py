
import sys
import os
import asyncio
import logging
from pprint import pprint

# Setup paths
import sys
import os

# Get the directory where this script is located (apps/backend)
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the project root (parent of apps/backend -> parent of backend -> apps -> root)
# Actually, the structure is: root/apps/backend. 
# Imports inside backend often look like 'from services...'. So we need 'apps/backend' in path.
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Also try adding the parent of 'apps' just in case imports are 'apps.backend...'
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.flow_service import get_flow_service
from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding
from services.auth_service import verify_firebase_token # Mock or bypass for debug if needed
from infrastructure.db_manager import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_layers():
    print("--- STARTING DEBUG ---")
    
    # 1. Test Database Connection
    try:
        with DatabaseManager.get_connection() as conn:
            print("✅ Database Connection: OK")
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
                count = cursor.fetchone()[0]
                print(f"📊 Total Content Count: {count}")
    except Exception as e:
        print(f"❌ Database Connection Failed: {e}")
        return

    # 2. Setup Context (Need a valid UID - ideally one that exists in DB)
    # We'll try to find a UID from the DB to be sure
    test_uid = None
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT FIREBASE_UID FROM TOMEHUB_CONTENT FETCH FIRST 1 ROW ONLY")
                row = cursor.fetchone()
                if row:
                    test_uid = row[0]
                    print(f"👤 Using Test UID from DB: {test_uid}")
                else:
                    print("⚠️ No users found in content table. System is empty.")
    except Exception as e:
        print(f"❌ Failed to fetch test UID: {e}")

    if not test_uid:
        print("❌ Cannot proceed without a test UID.")
        return

    # 3. Test Layer 4 (Flow Service)
    print("\n--- TESTING LAYER 4 (FLOW) ---")
    try:
        flow_service = get_flow_service()
        print("✅ FlowService Initialized")
        
        # Test Start Session
        session_id = f"debug_session_{test_uid[:5]}"
        print(f"🚀 Starting Flow Session for {test_uid}...")
        
        # We need to simulate the args for start_session
        # This is async in the route but sync in service? Check service definition.
        # FlowService methods are generally sync unless async keyword is used.
        # Based on previous readings, start_session is sync.
        
        try:
            # Re-read flow_service signatures if needed, but assuming standard call
            initial_cards, label, sid = flow_service.start_session(
                firebase_uid=test_uid,
                anchor_type='topic',
                anchor_id='Philosophy', # Generic topic
                mode='FOCUS'
            )
            print(f"✅ Start Session Result: {len(initial_cards)} cards returned.")
            if initial_cards:
                print(f"   First Card: {initial_cards[0].title} ({initial_cards[0].chunk_id})")
            else:
                print("⚠️  Returned 0 cards in start_session.")
                
            # Test Batch Fetch (The optimized part)
            if initial_cards:
                 print("🧪 Testing Batch Metadata Fetch...")
                 chunk_ids = [c.chunk_id for c in initial_cards]
                 meta = flow_service._get_candidate_metadata_batch(test_uid, chunk_ids)
                 print(f"   Batch Meta Result Size: {len(meta)}")
                 pprint(meta)
                 
        except Exception as e:
             print(f"❌ FlowService Error: {e}")
             import traceback
             traceback.print_exc()

    except Exception as e:
        print(f"❌ Layer 4 Init Failed: {e}")

    # 4. Test Layer 3 (Search Service)
    print("\n--- TESTING LAYER 3 (SEARCH) ---")
    try:
        # SearchOrchestrator needs embedding function
        orchestrator = SearchOrchestrator(embedding_fn=get_embedding)
        print("✅ SearchOrchestrator Initialized")
        
        # Test Basic Search
        query = "Philosophy of logic"
        print(f"🔍 Searching for: '{query}'...")
        
        # Search returns tuple (results, metadata)
        results, meta = orchestrator.search(query, firebase_uid=test_uid, limit=10)
        
        # Verify structure
        print(f"✅ Search Returned {len(results)} results.")
        if results:
             print(f"   Top Result: {results[0].get('content', '')[:50]}...")
             print(f"   Meta: {meta}")
        else:
             print("⚠️ Search returned 0 results.")

    except Exception as e:
        print(f"❌ SearchService Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_layers())
