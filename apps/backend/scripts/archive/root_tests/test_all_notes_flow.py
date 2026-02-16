"""
Test script to simulate All Notes flow request
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
from services.flow_service import FlowService
import json

DatabaseManager.init_pool()

try:
    flow_service = FlowService()
    
    # Get session for testing
    # First, get any firebase_uid from database
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT firebase_uid FROM TOMEHUB_CONTENT WHERE ROWNUM = 1")
            row = cursor.fetchone()
            if not row:
                print("No content found in database")
                sys.exit(1)
            firebase_uid = row[0]
            print(f"Using firebase_uid: {firebase_uid}")
    
    # Create/get session with resource_type=None (All Notes)
    from models.flow_models import FlowStartRequest, FlowMode
    
    request = FlowStartRequest(
        firebase_uid=firebase_uid,
        anchor_type="topic",
        anchor_id="general_discovery",
        horizon_value=0.5,
        mode=FlowMode.FOCUS,
        resource_type=None  # ALL NOTES
    )
    
    result = flow_service.start_session(request)
    
    print(f"\nSession created: {result.session_id}")
    print(f"Prefetched cards: {len(result.initial_cards)}")
    
    if result.initial_cards:
        print("\nFirst 3 cards:")
        for i, card in enumerate(result.initial_cards[:3]):
            print(f"\n{i+1}. {card.title} (Zone {card.zone})")
            print(f"   Reason: {card.reason}")
            print(f"   Content: {card.content[:100]}...")
    else:
        print("\nNo cards returned!")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
