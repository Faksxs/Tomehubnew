
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager
from services.flow_service import FlowService

def test():
    DatabaseManager.init_pool()
    fs = FlowService()
    
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    sid = "test_session"
    vec = [0.1] * 768 # dummy vector (DB uses 768, confirmed via overflow error)
    
    print("\n--- Testing Gravity with ALL_NOTES ---")
    cards = fs._fetch_seed_gravity(uid, sid, vec, "ALL_NOTES", limit=5)
    print(f"Gravity Cards found: {len(cards)}")
    for c in cards:
        print(f" - {c.title}: {c.content[:50]}...")

    print("\n--- Testing Recency with ALL_NOTES ---")
    recency = fs._fetch_seed_recency(uid, sid, "ALL_NOTES", limit=5)
    print(f"Recency Cards found: {len(recency)}")

if __name__ == "__main__":
    test()
