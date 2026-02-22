import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

from services.search_system.orchestrator import SearchOrchestrator
from services.embedding_service import get_embedding

def test():
    firebase_uid = "vpq1pS6E8gP44SDBmEDtM5T1ZTo2"
    orch = SearchOrchestrator(embedding_fn=get_embedding, cache=None)
    results, meta = orch.search(
        query="bilhassa",
        firebase_uid=firebase_uid,
        limit=20,
        result_mix_policy="lexical_then_semantic_tail"
    )
    print("Meta lexical total:", meta.get("lexical_total"))
    print("Meta semantic tail total added:", meta.get("semantic_tail_added"))
    for i, r in enumerate(results):
        print(f"{i+1}. ID: {r.get('id')} | Match: {r.get('match_type')} | Title: {r.get('title')[:30]}")

if __name__ == "__main__":
    test()
