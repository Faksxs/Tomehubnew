# -*- coding: utf-8 -*-
import sys
import os
import json

# Add apps/backend to path to import services
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from services.search_service import search_similar_content, generate_answer

def test_search():
    print("======================================================================")
    print("VERIFICATION: Hybrid RAG System (Turkish)")
    print("======================================================================")
    
    # Use a dummy or existing user ID. User input required if not hardcoded.
    uid = "test_user_001"
    
    queries = [
        "Wittgenstein için özel arşiv kodları nelerdir?", # Sparse/Exact (Codes)
        "Sessizlik kavramını açıkla",                     # Semantic (Abstract)
        "Heidegger'in önceki yazarla ilişkisi nedir?"     # Graph/Relational
    ]
    
    for q in queries:
        print(f"\n\n>>> QUERY: {q}")
        print("-" * 60)
        
        # 1. Search Only (Inspect RRF Scores)
        results = search_similar_content(q, uid, top_k=5)
        
        if results:
            print(f"Found {len(results)} results:")
            for i, r in enumerate(results[:5], 1): # Show top 5
                print(f"{i}. [Rerank: {r.get('similarity_score',0):.4f} | RRF: {r.get('final_score',0):.4f}] {r['title']} (p.{r['page_number']})")
                print(f"    v:{r.get('vector_score',0):.2f} | b:{r.get('bm25_score',0):.2f} | g:{r.get('graph_score',0):.2f}")
                print(f"    Sample: {r['content_chunk'][:60]}...")
        else:
            print("No results found.")

if __name__ == "__main__":
    test_search()
