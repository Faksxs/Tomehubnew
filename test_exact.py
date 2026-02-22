import sys, os, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'apps/backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'apps/backend/.env'))

from infrastructure.db_manager import DatabaseManager, safe_read_clob
from services.search_system.strategies import ExactMatchStrategy, _contains_exact_term_boundary, _normalize_match_text
from services.search_system.orchestrator import SearchOrchestrator

def test():
    with io.open('test_exact_out.txt', 'w', encoding='utf-8') as f:
        uid = None
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT firebase_uid FROM TOMEHUB_CONTENT WHERE title LIKE '%Sosyoloji%' FETCH FIRST 1 ROWS ONLY")
                row = cursor.fetchone()
                if row:
                    uid = row[0]
                    f.write(f"Found UID: {uid}\n")
                else:
                    f.write("UID not found\n")
                    return
        
        strat = ExactMatchStrategy()
        f.write("\n--- ExactMatchStrategy ---\n")
        res = strat.search("bilhassa", uid, limit=100)
        f.write(f"ExactMatchStrategy returned {len(res)} results.\n")
        
        titles_seen = []
        for r in res:
            f.write(f"Title: {r['title']}, Match Type: {r['match_type']}, ID: {r['id']}\n")
            titles_seen.append(r['title'])
            
        f.write("\n--- Orchestrator (ALL_NOTES) ---\n")
        orch = SearchOrchestrator(embedding_fn=None, cache=None)
        res_orch, meta = orch.search("bilhassa", uid, limit=20, resource_type="ALL_NOTES", result_mix_policy="lexical_then_semantic_tail")
        
        f.write(f"Orch exact count: {len([x for x in res_orch if x['match_type'] == 'content_exact'])}\n")
        f.write(f"Orch semantic count: {len([x for x in res_orch if x['match_type'] == 'semantic'])}\n")
        
        for i, r in enumerate(res_orch):
            f.write(f"{i+1}. Title: {r['title']}, Match: {r['match_type']}, ID: {r['id']}\n")

if __name__ == "__main__":
    test()
