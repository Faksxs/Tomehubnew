import sys
sys.path.insert(0, 'c:\\Users\\aksoy\\Desktop\\yeni tomehub\\apps\\backend')

from services.flow_service import FlowService
from models.flow_models import FlowStartRequest
from infrastructure.db_manager import DatabaseManager

# Test All Notes flow
service = FlowService()

# Simulate starting All Notes flow
request = FlowStartRequest(
    firebase_uid="Faksxs",  # Replace with actual UID
    anchor_id="general_discovery",
    anchor_type="topic",
    resource_type=None,  # All Notes
    horizon=0.5
)

print("=" * 80)
print("Testing All Notes Flow Start")
print("=" * 80)

try:
    response = service.start_session(request)
    
    print(f"\nSession ID: {response.session_id}")
    print(f"Original Anchor: {response.original_anchor_id}")
    print(f"Cards returned: {len(response.cards)}")
    
    print("\nCards:")
    for idx, card in enumerate(response.cards, 1):
        print(f"\n{idx}. [{card.zone}] {card.title}")
        print(f"   Reason: {card.reason}")
        print(f"   Content: {card.content[:100]}...")
        
    if response.pivot_info:
        print(f"\n⚠️ PIVOT INFO: {response.pivot_info.message}")
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Also check content count
print("\n" + "=" * 80)
print("Database Check")
print("=" * 80)

with DatabaseManager.get_connection() as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM TOMEHUB_CONTENT 
            WHERE firebase_uid = :uid AND VEC_EMBEDDING IS NOT NULL
        """, {"uid": "Faksxs"})
        
        count = cursor.fetchone()[0]
        print(f"Total content with embeddings for Faksxs: {count}")
