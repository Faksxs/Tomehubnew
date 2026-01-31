
"""
Simple usage verification script for Flow API (Layer 4).
Runs against local backend (localhost:5000).
"""
import requests
import time
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:5000/api/flow"
HEALTH_URL = "http://localhost:5000/"
FIREBASE_UID = "test_user_123"  # Mock UID

HEADERS = {
    "Authorization": "Bearer mock_token",
    "Content-Type": "application/json"
}

def test_flow_lifecycle():
    logger.info("--- Starting Flow API Test ---")
    
    # 0. Check Health
    try:
        res = requests.get(HEALTH_URL)
        logger.info(f"Health Check: {res.status_code} {res.json()}")
    except Exception as e:
        logger.error(f"Health Check Failed: {e}")
        return

    # 1. Start Session
    logger.info("1. Starting Session...")
    start_payload = {
        "firebase_uid": FIREBASE_UID,
        "anchor_type": "topic",
        "anchor_id": "Philosophy of Science",
        "mode": "FOCUS",
        "horizon_value": 0.2
    }
    
    try:
        res = requests.post(f"{BASE_URL}/start", json=start_payload, headers=HEADERS)
        if res.status_code != 200:
            logger.error(f"Start failed: {res.status_code} {res.text}")
            return
            
        data = res.json()
        session_id = data["session_id"]
        initial_cards = data["initial_cards"]
        logger.info(f"✅ Session Started: {session_id}")
        logger.info(f"Received {len(initial_cards)} initial cards")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    # 2. Get Next Batch
    logger.info("\n2. Getting Next Batch...")
    next_payload = {
        "firebase_uid": FIREBASE_UID,
        "session_id": session_id,
        "batch_size": 3
    }
    
    res = requests.post(f"{BASE_URL}/next", json=next_payload, headers=HEADERS)
    if res.status_code == 200:
        data = res.json()
        cards = data.get("cards", [])
        logger.info(f"✅ Received {len(cards)} more cards")
        if cards:
            first_card = cards[0]
            logger.info(f"   Sample Card: {first_card.get('title')} (Zone {first_card.get('zone')})")
            
            # 3. Submit Feedback (Like)
            logger.info(f"\n3. Submitting Feedback (Like) on {first_card['chunk_id']}...")
            feedback_payload = {
                "firebase_uid": FIREBASE_UID,
                "session_id": session_id,
                "chunk_id": first_card['chunk_id'],
                "action": "like"
            }
            res = requests.post(f"{BASE_URL}/feedback", json=feedback_payload, headers=HEADERS)
            if res.status_code == 200:
                logger.info("✅ Feedback submitted successfully")
            else:
                logger.error(f"Feedback failed: {res.text}")
    else:
        logger.error(f"Next batch failed: {res.text}")

    # 4. Adjust Horizon
    logger.info("\n4. Adjusting Horizon to 0.8 (Discovery)...")
    adjust_payload = {
        "session_id": session_id,
        "horizon_value": 0.8
    }
    res = requests.post(f"{BASE_URL}/adjust", json=adjust_payload, headers=HEADERS)
    if res.status_code == 200:
        logger.info("✅ Horizon adjusted")
    else:
        logger.warning(f"Horizon adjust returned: {res.status_code} {res.text}")

    # 5. Get Session Info
    logger.info("\n5. Getting Session Info...")
    res = requests.get(f"{BASE_URL}/session/{session_id}", headers=HEADERS)
    if res.status_code == 200:
        info = res.json()
        logger.info(f"✅ Session Info: Mode={info.get('mode')}, Horizon={info.get('horizon_value')}, Cards Shown={info.get('cards_shown')}")
    else:
        logger.error(f"Get session info failed: {res.text}")

    logger.info("\n--- Test Complete ---")

if __name__ == "__main__":
    test_flow_lifecycle()
