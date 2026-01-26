# -*- coding: utf-8 -*-
"""
TomeHub Search Service
======================
Implements RAG (Retrieval-Augmented Generation) for semantic search
and AI-powered question answering from the user's personal library.

Author: TomeHub Team
Date: 2026-01-07
"""

import os
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv
import oracledb
import google.generativeai as genai

# Import TomeHub services
from services.embedding_service import get_embedding
from services.epistemic_service import (
    extract_core_concepts, 
    classify_chunk, 
    determine_answer_mode,
    build_epistemic_context,
    get_prompt_for_mode,
    classify_question_intent
)

# Load environment variables - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)


from infrastructure.db_manager import DatabaseManager, safe_read_clob



# Import Smart Search Service & Helpers
from services.smart_search_service import (
    perform_smart_search, 
    create_turkish_fuzzy_pattern, 
    parse_and_clean_content,
    generate_query_variations,
    score_with_bm25,
    compute_rrf
)

# Import Graph Service
from services.graph_service import get_graph_candidates

# Import Re-rank Service
from services.rerank_service import rerank_candidates
from services.network_classifier import classify_network_status

def get_graph_enriched_context(base_results: List[Dict], firebase_uid: str) -> str:
    """
    Traverses the Oracle Property Graph to find "invisible bridges"
    between the retrieved chunks and related concepts.
    """
    if not base_results:
        return ""
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] GraphRAG: Analyzing semantic bridges (Batched)...")
    
    try:
        # Collect IDs for batch processing
        target_results = base_results[:10]
        content_ids = [res.get('id') for res in target_results if res.get('id')]
        
        if not content_ids:
            return ""

        bridges = []
        
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. BATCH FETCH: Concepts for these chunks
                # Dynamically build bind variables for IN clause
                bind_names = [f":id{i}" for i in range(len(content_ids))]
                bind_clause = ",".join(bind_names)
                params = {f"id{i}": cid for i, cid in enumerate(content_ids)}
                
                sql_concepts = f"""
                    SELECT cc.content_id, c.name, c.id
                    FROM TOMEHUB_CONCEPTS c
                    JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c.id = cc.concept_id
                    WHERE cc.content_id IN ({bind_clause})
                """
                cursor.execute(sql_concepts, params)
                rows_concepts = cursor.fetchall()
                
                # Map cid -> concept_name
                concept_map = {} # cid -> name
                related_concept_ids = []
                
                for _, cname, cid in rows_concepts:
                    concept_map[cid] = cname
                    related_concept_ids.append(cid)
                
                related_concept_ids = list(set(related_concept_ids))
                
                if not related_concept_ids:
                    return ""

                # 2. BATCH FETCH: Neighbors for these concepts
                # Limit to avoiding too massive query if many concepts
                if len(related_concept_ids) > 20: 
                    related_concept_ids = related_concept_ids[:20]
                    
                bind_names_c = [f":cid{i}" for i in range(len(related_concept_ids))]
                bind_clause_c = ",".join(bind_names_c)
                params_c = {f"cid{i}": cid for i, cid in enumerate(related_concept_ids)}
                
                # Fetch relations where source OR dest is one of our concepts
                # Join to get the OTHER concept's name
                sql_neighbors = f"""
                    SELECT c1.name as concept_A, r.rel_type, c2.name as concept_B
                    FROM TOMEHUB_RELATIONS r
                    JOIN TOMEHUB_CONCEPTS c1 ON r.src_id = c1.id
                    JOIN TOMEHUB_CONCEPTS c2 ON r.dst_id = c2.id
                    WHERE (r.src_id IN ({bind_clause_c}) OR r.dst_id IN ({bind_clause_c}))
                    FETCH FIRST 15 ROWS ONLY
                """
                cursor.execute(sql_neighbors, params_c)
                rows_rels = cursor.fetchall()
                
                for c1_name, rtype, c2_name in rows_rels:
                    # Filter to keep only if one side is in our original concept set?
                    # The graph query ensures at least one side is. This bridge connects them.
                    bridges.append(f"🔗 {c1_name} is connected to {c2_name} via '{rtype}' relationship.")
                        
        if bridges:
            return "\nSEMANTIC BRIDGES (Graph Insights):\n" + "\n".join(set(bridges))
        return ""
        
    except Exception as e:
        print(f"[WARNING] Graph enrichment failed: {e}")
        return ""

def get_book_context(book_id: str, query_text: str, firebase_uid: str) -> List[Dict]:
    """
    Retrieve contextual chunks specifically from a target book.
    
    5-STEP PIPELINE:
    1. Normalization: Apply Turkish fuzzy pattern.
    2. Filter: Restrict to book_id.
    3. Semantic Search: Vector distance.
    4. Logical Proximity: (Implied by semantic density, but could specific prev/next fetch).
    5. Scoring: Combined semantic + fuzzy keyword match.
    """
    print(f"\n[CTX] Fetching context for Book: {book_id} | Query: {query_text}")
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Generate Embeddings & Patterns
                query_embedding = get_embedding(query_text)
                variations = create_turkish_fuzzy_pattern(query_text)
                
                # 2-5. Combined Heavy SQL Query
                # Prioritizes:
                # - Semantic match (Vector Distance)
                # - Keyword match (Turkish Fuzzy)
                
                sql = """
                    SELECT content_chunk, page_number, chunk_index, title,
                           VECTOR_DISTANCE(vec_embedding, :bv_vec, COSINE) as dist
                    FROM TOMEHUB_CONTENT
                    WHERE book_id = :bv_book_id 
                      AND firebase_uid = :bv_uid
                    ORDER BY dist ASC
                    FETCH FIRST 15 ROWS ONLY
                """
                
                cursor.execute(sql, bv_vec=query_embedding, bv_book_id=book_id, bv_uid=firebase_uid)
                rows = cursor.fetchall()
                
                chunks = []
                for row in chunks:
                    text = safe_read_clob(row[0])
                    chunks.append({
                        'text': text,
                        'page': row[1],
                        'title': row[3],
                        'distance': row[4]
                    })
                
                # FIX: chunks logic was accessing empty list, should interpret rows
                chunks = []
                for row in rows:
                    text = safe_read_clob(row[0])
                    chunks.append({
                        'text': text,
                        'page': row[1],
                        'title': row[3],
                        'distance': row[4]
                    })
            
                return chunks
        
    except Exception as e:
        print(f"[ERROR] Context retrieval failed: {e}")
        return []


def search_similar_content(query_text: str, firebase_uid: str, top_k: int = 5) -> Optional[List[Dict]]:
    """
    Advanced Hybrid RAG Retrieval Pipeline (Phase 1 Upgrade).
    
    Orchestration:
    1. Query Expansion (Gemini) -> [q1, q2, q3]
    2. Parallel Vector Search (Oracle) for all queries
    3. Sparse Retrieval Simulation (BM25)
    4. Reciprocal Rank Fusion (RRF)
    5. Final Candidate Selection
    """
    start_time = time.time()
    logger.info("Hybrid Search Started", extra={"query": query_text, "uid": firebase_uid})
    
    try:
        with DatabaseManager.get_connection() as connection:
            with connection.cursor() as cursor:
                # 1. QUERY EXPANSION
                t0 = time.time()
                queries = [query_text]
                variations = generate_query_variations(query_text)
                if variations:
                    queries.extend(variations)
                    logger.info("Query Expansion Complete", extra={
                        "original": query_text, 
                        "expanded": variations,
                        "duration_ms": int((time.time() - t0) * 1000)
                    })

                # 2. RETRIEVAL (Vector + Keyword for ALL variations)
                t1 = time.time()
                candidate_pool = {} # content_hash -> row_data
                
                for q in set(queries): # Unique queries only
                    # A. Vector Retrieval
                    q_emb = get_embedding(q)
                    if q_emb:
                        vector_sql = """
                        SELECT content_chunk, page_number, title, source_type,
                               VECTOR_DISTANCE(vec_embedding, :p_vec, COSINE) as dist
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                        ORDER BY dist
                        FETCH FIRST 20 ROWS ONLY
                        """
                        cursor.execute(vector_sql, {"p_vec": q_emb, "p_uid": firebase_uid})
                        rows = cursor.fetchall()
                        
                        for r in rows:
                             # Create unique key (assuming title+page+content_snippet is unique enough)
                            content = safe_read_clob(r[0])
                            key = f"{r[2]}_{r[1]}_{content[:30]}"
                            
                            if key not in candidate_pool:
                                candidate_pool[key] = {
                                    'content': content,
                                    'page': r[1],
                                    'title': r[2],
                                    'type': r[3],
                                    'vector_score': 1 - r[4], # Similarity (0.0 to 1.0)
                                    'bm25_score': 0.0,
                                    'graph_score': 0.0
                                }
                            else:
                                # Keep best vector score if found multiple times
                                current_sim = 1 - r[4]
                                if current_sim > candidate_pool[key]['vector_score']:
                                    candidate_pool[key]['vector_score'] = current_sim

                    # B. Keyword/SQL Retrieval (Broad sweep for exact matches)
                    # Only run for original query to avoid noise
                    if q == query_text:
                        keyword_sql = """
                        SELECT content_chunk, page_number, title, source_type
                        FROM TOMEHUB_CONTENT
                        WHERE firebase_uid = :p_uid
                        AND LOWER(content_chunk) LIKE :p_kw
                        FETCH FIRST 15 ROWS ONLY
                        """
                        cursor.execute(keyword_sql, {"p_uid": firebase_uid, "p_kw": f"%{q.lower()}%"})
                        k_rows = cursor.fetchall()
                        
                        for r in k_rows:
                            content = safe_read_clob(r[0])
                            key = f"{r[2]}_{r[1]}_{content[:30]}"
                            if key not in candidate_pool:
                                candidate_pool[key] = {
                                    'content': content,
                                    'page': r[1],
                                    'title': r[2],
                                    'type': r[3],
                                    'vector_score': 0.0, # Not found by vector
                                    'bm25_score': 0.0,
                                    'graph_score': 0.0
                                }
                
                logger.info("Base Retrieval Complete", extra={
                    "candidates_count": len(candidate_pool),
                    "duration_ms": int((time.time() - t1) * 1000)
                })

                # 3. GRAPH RETRIEVAL (Phase 2)
                # Finds chunks that are conceptually related but textually different
                t2 = time.time()
                logger.info("Executing GraphRAG Retrieval...")
                graph_chunks = get_graph_candidates(query_text, firebase_uid)
                
                for gc in graph_chunks:
                    # Create same key structure
                    key = f"{gc['title']}_{gc['page']}_{gc['content'][:30]}"
                    if key not in candidate_pool:
                        candidate_pool[key] = {
                            'content': gc['content'],
                            'page': gc['page'],
                            'title': gc['title'],
                            'type': gc['type'],
                            'vector_score': 0.0,
                            'bm25_score': 0.0,
                            'graph_score': 1.0 # High confidence
                        }
                    else:
                        candidate_pool[key]['graph_score'] = 1.0

                logger.info("Graph Retrieval Complete", extra={
                    "graph_candidates": len(graph_chunks),
                    "duration_ms": int((time.time() - t2) * 1000)
                })

                # 4. BM25 SCORING (Sparse)
                candidates_list = list(candidate_pool.values())
                corpus = [c['content'] for c in candidates_list]
                bm25_scores = score_with_bm25(corpus, query_text) # Score against ORIGINAL query
                
                for i, score in enumerate(bm25_scores):
                    candidates_list[i]['bm25_score'] = score
                    
                # 5. FUSION (RRF)
                # Create ranked lists
                # Rank by Vector (High to Low)
                vector_ranking = sorted([k for k, v in candidate_pool.items() if v['vector_score'] > 0], 
                                      key=lambda k: candidate_pool[k]['vector_score'], reverse=True)
                                      
                # Rank by BM25 (High to Low)
                bm25_ranking = sorted([k for k, v in candidate_pool.items()], 
                                    key=lambda k: candidate_pool[k]['bm25_score'], reverse=True)
                                    
                # Rank by Graph (High to Low) - essentially binary here but robust for future
                graph_ranking = sorted([k for k, v in candidate_pool.items() if v['graph_score'] > 0], 
                                     key=lambda k: candidate_pool[k]['graph_score'], reverse=True)
                
                # Fuse 3 Lists
                rrf_scores = compute_rrf([vector_ranking, bm25_ranking, graph_ranking], k=60)
                
                # Attach RRF scores
                final_results = []
                for key, score in rrf_scores.items():
                    cand = candidate_pool[key]
                    cand['rrf_score'] = score
                    final_results.append(cand)
                    
                # Sort by RRF
                final_results.sort(key=lambda x: x['rrf_score'], reverse=True)
                
                # 6. SMART RE-RANKING (Phase 3) - Skip if high confidence
                # Check if reranking is needed based on RRF scores
                top_rrf_score = final_results[0].get('rrf_score', 0) if final_results else 0
                second_rrf_score = final_results[1].get('rrf_score', 0) if len(final_results) > 1 else 0
                score_gap = top_rrf_score - second_rrf_score if second_rrf_score > 0 else top_rrf_score
                
                # Skip reranking if high confidence (top score > 0.8 and gap > 0.1)
                skip_reranking = top_rrf_score > 0.8 and score_gap > 0.1
                
                if skip_reranking:
                    logger.info(f"Skipping reranking: High RRF confidence (top={top_rrf_score:.3f}, gap={score_gap:.3f})")
                    # Convert to reranked format for consistency
                    reranked_results = []
                    for res in final_results[:top_k]:
                        reranked_results.append({
                            'content': res['content'],
                            'page': res['page'],
                            'title': res['title'],
                            'type': res['type'],
                            'rrf_score': res['rrf_score'],
                            'rerank_score': res['rrf_score']  # Use RRF score as rerank score
                        })
                else:
                    # RE-RANKING (Phase 3)
                    # We take top 30 from RRF and re-score them using LLM
                    t3 = time.time()
                    logger.info("Re-ranking top candidates...")
                    
                    # Prepare candidates for re-ranking (Standardize Keys)
                    rerank_input = []
                    for res in final_results[:30]:
                        rerank_input.append({
                            'content': res['content'],
                            'page': res['page'],
                            'title': res['title'],
                            'type': res['type'],
                            'rrf_score': res['rrf_score']
                        })
                        
                    reranked_results = rerank_candidates(query_text, rerank_input)
                    
                    if not reranked_results:
                         logger.warning("Re-ranking returned empty/failed. Using RRF results.")
                         reranked_results = rerank_input
                    
                    logger.info("Re-ranking Complete", extra={
                        "input_count": len(rerank_input),
                        "output_count": len(reranked_results),
                        "duration_ms": int((time.time() - t3) * 1000)
                    })

                logger.info("Re-ranking Complete", extra={
                    "input_count": len(rerank_input),
                    "output_count": len(reranked_results),
                    "duration_ms": int((time.time() - t3) * 1000)
                })

                # 7. FORMATTING & DIVERSITY
                selected_chunks = []
                seen_titles = set()
                
                # Diversity Pass: First 10 results from diff books
                for res in reranked_results:
                    if len(selected_chunks) >= top_k: 
                        break
                    
                    # Use 'content_chunk' key to match old API
                    selected_chunks.append({
                        'content_chunk': res['content'],
                        'page_number': res['page'],
                        'title': res['title'],
                        'similarity_score': res.get('rerank_score', 0), # New score
                        'final_score': res['rrf_score'], # Keep original for debug
                        'source_type': res['type']
                    })
                    
                logger.info("Hybrid Search Finished", extra={
                    "final_count": len(selected_chunks),
                    "total_duration_ms": int((time.time() - start_time) * 1000)
                })
                return selected_chunks

    except Exception as e:
        logger.error("Hybrid Search Failed", extra={"error": str(e)}, exc_info=True)
        return None


from concurrent.futures import ThreadPoolExecutor

def get_rag_context(question: str, firebase_uid: str, context_book_id: str = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves and processes context for RAG.
    Shared by Legacy Search and Dual-AI Chat.
    
    Returns dict with:
    - chunks: List[Dict] (The weighted, sorted chunks)
    - intent: str
    - complexity: str
    - mode: str
    - confidence: float
    - keywords: List[str]
    """
    print(f"\n[RAG] Retrieving context for: {question}")
    
    # 1. Keyword Extraction
    keywords = extract_core_concepts(question)
    
    all_chunks_map = {}
    
    # 2. Parallel Retrieval (Vector + Graph)
    def run_vector_search():
        return perform_smart_search(question, firebase_uid) or []
        
    def run_graph_search():
        try:
            return get_graph_candidates(question, firebase_uid)
        except:
            return []

    graph_results = []
    question_results = []
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_vec = executor.submit(run_vector_search)
        future_graph = executor.submit(run_graph_search)
        
        try:
            question_results = future_vec.result()
        except Exception as e:
            print(f"[ERROR] Vector: {e}")
            
        try:
            graph_results = future_graph.result()
        except Exception as e:
            print(f"[ERROR] Graph: {e}")

    # Merge Results
    if question_results:
        for c in question_results:
            key = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
            all_chunks_map[key] = c

    if graph_results:
        for c in graph_results:
            c_std = {
                'title': c.get('title', 'Unknown'),
                'content_chunk': c.get('content', '') or c.get('content_chunk', ''),
                'page_number': c.get('page', 0),
                'source_type': 'GRAPH_RELATION',
                'epistemic_level': 'B',
                'score': 100
            }
            key = f"{c_std['title']}_{str(c_std['content_chunk'])[:20]}"
            if key not in all_chunks_map:
                all_chunks_map[key] = c_std

    # 3. Supplementary Keyword Search (Gap Filling)
    if keywords:
        search_kw = " ".join(keywords[:2])
        if search_kw and search_kw != question:
            kw_res = perform_smart_search(search_kw, firebase_uid)
            if kw_res:
                for c in kw_res:
                    key = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
                    if key not in all_chunks_map:
                        all_chunks_map[key] = c
    
    combined_chunks = list(all_chunks_map.values())
    
    if not combined_chunks:
        return None
        
    # Truncate if too many
    if len(combined_chunks) > 100:
        combined_chunks = combined_chunks[:100]

    # 4. Epistemic Scoring & Intent
    intent, complexity = classify_question_intent(question)
    
    for chunk in combined_chunks:
        classify_chunk(keywords, chunk)
        
    # Passage Weighting & Sorting
    standard_top_40 = combined_chunks[:40]
    
    # Logic to include "Gold" chunks (score >= 2) if missed
    final_ids = {f"{c.get('title')}_{c.get('content_chunk')[:20]}" for c in standard_top_40}
    final_chunks = list(standard_top_40)
    
    for chunk in combined_chunks:
        if chunk.get('answerability_score', 0) >= 2:
            cid = f"{chunk.get('title')}_{chunk.get('content_chunk')[:20]}"
            if cid not in final_ids:
                final_chunks.append(chunk)
                final_ids.add(cid)

    # Weighted Sort
    def get_weighted_score(chunk):
        base = float(chunk.get('answerability_score', 0))
        level = chunk.get('epistemic_level', 'C')
        is_lit = len(str(chunk.get('content_chunk', ''))) > 300 and level != 'A'
        
        weight = 1.0
        if intent in ['NARRATIVE', 'SOCIETAL']:
            if is_lit: weight = 1.2
        else:
            if level == 'A': weight = 1.2
            elif level == 'B': weight = 0.9
            elif is_lit: weight = 0.4
            
        return base * weight

    final_chunks.sort(key=get_weighted_score, reverse=True)
    
    # Answer Mode & Confidence
    answer_mode = determine_answer_mode(final_chunks, intent, complexity)
    
    top_5 = final_chunks[:5]
    avg_conf = sum(c.get('answerability_score', 0) for c in top_5) / max(1, len(top_5)) if top_5 else 0
    
    # Network Classification (Phase 3)
    network_info = classify_network_status(question, final_chunks)

    return {
        "chunks": final_chunks,
        "intent": intent,
        "complexity": complexity,
        "mode": answer_mode,
        "confidence": avg_conf,
        "network_status": network_info["status"],
        "network_reason": network_info["reason"],
        "keywords": keywords,
        "level_counts": {
            'A': sum(1 for c in final_chunks if c.get('epistemic_level') == 'A'),
            'B': sum(1 for c in final_chunks if c.get('epistemic_level') == 'B'),
        }
    }


def generate_answer(question: str, firebase_uid: str, context_book_id: str = None) -> Tuple[Optional[str], Optional[List[Dict]]]:
    """
    Legacy RAG generation (Wrapper around get_rag_context).
    """
    # 1. Retrieve Context
    ctx = get_rag_context(question, firebase_uid, context_book_id)
    if not ctx:
        return "Üzgünüm, şu an cevap üretemiyorum. İlgili içerik bulunamadı.", []
        
    chunks = ctx['chunks']
    answer_mode = ctx['mode']
    avg_conf = ctx['confidence']
    keywords = ctx['keywords']
    
    # 2. Build Context String
    level_counts = ctx['level_counts']
    evidence_meta = f"[SİSTEM NOTU: Kullanıcının kütüphanesinde '{', '.join(keywords)}' ile ilgili toplam {level_counts['A'] + level_counts['B']} adet doğrudan not bulundu.]"
    
    context_str = evidence_meta + "\n\n" + build_epistemic_context(chunks, answer_mode)
    
    # Add Graph insights if synthesis
    if answer_mode == 'SYNTHESIS':
        try:
            graph_insight = get_graph_enriched_context(chunks, firebase_uid)
            if graph_insight:
                context_str = graph_insight + "\n\n" + context_str
        except:
            pass
            
    # 3. Generate Answer
    sources = [{
        'title': c.get('title', 'Unknown'), 
        'page_number': c.get('page_number', 0),
        'similarity_score': c.get('score', 0)
    } for c in chunks]
    
    try:
        network_status = ctx.get('network_status', 'IN_NETWORK')
        prompt = get_prompt_for_mode(answer_mode, context_str, question, confidence_score=avg_conf, network_status=network_status)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        answer = response.text if response else "Cevap üretilemedi."
        return answer, sources
    except Exception as e:
        print(f"[ERROR] Generate Answer failed: {e}")
        return "Bir hata oluştu.", sources


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TomeHub RAG Search Service - Interactive Test")
    print("=" * 70)
    
    # Get user ID
    firebase_uid = input("\nEnter Firebase UID (press Enter for test_user_001): ").strip()
    if not firebase_uid:
        firebase_uid = "test_user_001"
    
    print(f"\n[INFO] Using user ID: {firebase_uid}")
    
    # Interactive question loop
    while True:
        print("\n" + "=" * 70)
        question = input("\nEnter your question (or 'quit' to exit): ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            print("\n[INFO] Exiting...")
            break
        
        if not question:
            print("[ERROR] Please enter a question")
            continue
        
        # Generate answer
        answer, sources = generate_answer(question, firebase_uid)
        
        if answer and sources:
            # Display answer
            print("\n" + "=" * 70)
            print("AI ANSWER")
            print("=" * 70)
            print(f"\n{answer}\n")
            
            # Display sources
            print("=" * 70)
            print("SOURCES USED")
            print("=" * 70)
            
            # Group sources by title
            from collections import defaultdict
            sources_by_title = defaultdict(list)
            
            for source in sources:
                sources_by_title[source['title']].append(source['page_number'])
            
            for i, (title, pages) in enumerate(sources_by_title.items(), 1):
                pages_str = ", ".join([f"p.{p}" for p in sorted(set(pages))])
                print(f"{i}. {title} ({pages_str})")
            
            print("=" * 70)
        else:
            print("\n[ERROR] Failed to generate answer")
            print("Please check:")
            print("  1. Database contains content for this user")
            print("  2. GEMINI_API_KEY is configured")
            print("  3. Internet connectivity")
