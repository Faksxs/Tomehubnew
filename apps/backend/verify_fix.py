import asyncio
import os
import sys
from unittest.mock import patch

# Add the app path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.flow_models import FlowStartRequest
from services.flow_service import get_flow_service
from services.flow_session_service import get_flow_session_manager

def test_category_persistence():
    firebase_uid = "test_uid_123"
    
    flow_service = get_flow_service()
    session_manager = get_flow_session_manager()
    
    print("1. Starting session without category...")
    start_req = FlowStartRequest(
        firebase_uid=firebase_uid,
        anchor_type="topic",
        anchor_id="General Discovery"
    )
    start_res = flow_service.start_session(start_req)
    session_id = start_res.session_id
    
    state_before = session_manager.get_session(session_id)
    print(f"Session Category Before Pivot: {state_before.category}")
    
    print("\n2. Pivoting to Felsefe category...")
    flow_service.reset_anchor(
        session_id=session_id,
        anchor_type="topic",
        anchor_id="General Discovery",
        firebase_uid=firebase_uid,
        category="Felsefe"
    )
    
    state_after = session_manager.get_session(session_id)
    print(f"Session Category After Pivot: {state_after.category}")
    
    if state_after.category == "Felsefe":
        print("SUCCESS! Category is now persisting in the session state.")
    else:
        print("FAILED! Category did not persist.")

if __name__ == "__main__":
    test_category_persistence()
