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
    get_prompt_for_mode
)

# Load environment variables - go up one level from services/ to backend/
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

from utils.logger import get_logger
logger = get_logger("search_service")

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def get_database_connection():
    """
    Establish connection to Oracle Database.
    
    Returns:
        oracledb.Connection: Active database connection
    """
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN", "tomehubdb_high")
    
    # Robust path construction - go up one level from services/ to backend/
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to Oracle with wallet at: {wallet_location}")
    
    if not password:
        raise ValueError("DB_PASSWORD not found in .env file")
    
    try:
        connection = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            config_dir=wallet_location,
            wallet_location=wallet_location,
            wallet_password=password
        )
        
        # Verify connection
        connection.ping()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection checked: Alive")
        return connection
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection failed: {e}")
        raise



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

def get_graph_enriched_context(base_results: List[Dict], firebase_uid: str) -> str:
    """
    Traverses the Oracle Property Graph to find "invisible bridges"
    between the retrieved chunks and related concepts.
    """
    if not base_results:
        return ""
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] GraphRAG: Analyzing semantic bridges...")
    
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # 1. Collect all Content IDs from base results
        # Assuming we can find IDs from content_chunk or similar (not ideal, better to pass IDs)
        # For now, we'll try to find associated concepts for these results.
        # Note: Layer 2 results should include 'id' or we need to fetch them.
        
        # Let's use the content_chunk to find concepts for now as a fallback
        # In a real system, we'd use the numeric ID.
        
        bridges = []
        seen_concepts = set()
        
        for res in base_results[:10]: # Only bridge top 10 to avoid noise
            title = res.get('title', 'Unknown')
            text_preview = res.get('content_chunk', '')[:50]
            
            # Find concepts linked to this chunk (using Title + Text snippet as proxy if ID missing)
            # Better: Search for concepts mentioned in this chunk's metadata
            sql_concepts = """
                SELECT c.name, c.id
                FROM TOMEHUB_CONCEPTS c
                JOIN TOMEHUB_CONCEPT_CHUNKS cc ON c.id = cc.concept_id
                JOIN TOMEHUB_CONTENT ct ON cc.content_id = ct.id
                WHERE ct.title = :title AND ct.normalized_content LIKE '%' || :preview || '%'
                FETCH FIRST 5 ROWS ONLY
            """
            cursor.execute(sql_concepts, {"title": title, "preview": text_preview.lower()})
            
            chunk_concepts = cursor.fetchall()
            for cname, cid in chunk_concepts:
                if cname in seen_concepts: continue
                seen_concepts.add(cname)
                
                # 2. Find NEIGHBORS in the graph (The actual bridges)
                sql_neighbors = """
                    SELECT c2.name, r.rel_type, c2.concept_type
                    FROM TOMEHUB_RELATIONS r
                    JOIN TOMEHUB_CONCEPTS c2 ON r.dst_id = c2.id
                    WHERE r.src_id = :cid
                    UNION
                    SELECT c2.name, r.rel_type, c2.concept_type
                    FROM TOMEHUB_RELATIONS r
                    JOIN TOMEHUB_CONCEPTS c2 ON r.src_id = c2.id
                    WHERE r.dst_id = :cid
                    FETCH FIRST 3 ROWS ONLY
                """
                cursor.execute(sql_neighbors, {"cid": cid})
                neighbors = cursor.fetchall()
                
                for nname, rtype, ntype in neighbors:
                    bridges.append(f"🔗 {cname} is connected to {nname} via '{rtype}' relationship.")
                    
        conn.close()
        
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
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # 1. Generate Embeddings & Patterns
        query_embedding = get_embedding(query_text)
        variations = create_turkish_fuzzy_pattern(query_text)
        safe_uid = firebase_uid.replace("'", "")
        safe_book_id = book_id.replace("'", "")
        
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
        
        cursor.execute(sql, bv_vec=query_embedding, bv_book_id=safe_book_id, bv_uid=safe_uid)
        rows = cursor.fetchall()
        
        chunks = []
        for row in rows:
            text = (row[0].read() if row[0] else "")
            chunks.append({
                'text': text,
                'page': row[1],
                'title': row[3],
                'distance': row[4]
            })
            
        cursor.close()
        conn.close()
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
        connection = get_database_connection()
        cursor = connection.cursor()
        
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
                    content = r[0].read() if r[0] else ""
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
                    content = r[0].read() if r[0] else ""
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
        
        # 6. RE-RANKING (Phase 3)
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
            
        cursor.close()
        connection.close()
        
        logger.info("Hybrid Search Finished", extra={
            "final_count": len(selected_chunks),
            "total_duration_ms": int((time.time() - start_time) * 1000)
        })
        return selected_chunks

    except Exception as e:
        logger.error("Hybrid Search Failed", extra={"error": str(e)}, exc_info=True)
        return None


def generate_answer(question: str, firebase_uid: str, context_book_id: str = None) -> Tuple[Optional[str], Optional[List[Dict]]]:
    """
    Generate an AI-powered answer using RAG (Retrieval-Augmented Generation).
    
    This function:
    1. Searches for relevant content from the user's library
    2. Constructs a context-aware prompt
    3. Generates an answer using Gemini
    4. Returns the answer with source citations
    
    Args:
        question (str): The user's question
        firebase_uid (str): User identifier
    
    Returns:
        Tuple[str, List[Dict]] or (None, None): 
            - answer (str): AI-generated answer
            - sources (List[Dict]): Source citations with title and page numbers
        Returns (None, None) if generation fails.
    
    Example:
        >>> answer, sources = generate_answer("What is phenomenology?", "user_123")
        >>> print(answer)
        >>> for source in sources:
        ...     print(f"Source: {source['title']}, p.{source['page_number']}")
    """
    print("=" * 70)
    print("RAG Question Answering")
    print("=" * 70)
    print(f"\n[QUESTION] {question}")
    
    # Step 1: RETRIEVAL STRATEGY
    # ---------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"Step 1: Retrieving Context (Target Book: {context_book_id if context_book_id else 'None'})")
    print(f"{'='*70}")
    
    # A. Extract keywords EARLY to use for targeted retrieval
    keywords = extract_core_concepts(question)
    print(f"[RETRIEVAL] Extracted core concepts: {keywords}")
    
    all_chunks_map = {}  # Deduplication map: id -> chunk
    
    # B. Run standard Smart Search with full question
    print(f"[RETRIEVAL] Running semantic search for question: '{question}'")
    question_results = perform_smart_search(question, firebase_uid)
    if question_results:
        for c in question_results:
            # Generate a unique ID if not present (title + start of content)
            c_id = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
            all_chunks_map[c_id] = c

    # C. Run SUPPLEMENTARY Keyword Search (The "Gap Filler")
    # This ensures we get the "6 exact matches" the user sees in Layer 2
    if keywords:
        # Construct a keyword-focused query (just the top keywords joined)
        # Limiting to top 2 keywords to avoid noise
        keyword_query = " ".join(keywords[:2])
        if keyword_query and keyword_query != question:
            print(f"[RETRIEVAL] Running supplementary search for keywords: '{keyword_query}'")
            keyword_results = perform_smart_search(keyword_query, firebase_uid)
            
            if keyword_results:
                count_new = 0
                for c in keyword_results:
                    c_id = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
                    if c_id not in all_chunks_map:
                        all_chunks_map[c_id] = c
                        count_new += 1
                print(f"[RETRIEVAL] Added {count_new} unique chunks from keyword search")

    # Convert back to list
    combined_chunks = list(all_chunks_map.values())
    
    if not combined_chunks:
        print(f"[ERROR] No relevant content found via Smart Search")
        return None, None
        
    # CONTEXT MANAGEMENT: Take top 40 (increased from 30 to accommodate merged results)
    # Re-rank strictly? or just trust the merge?
    # For now, let's trust the order: Question results first, then appended keyword results
    # Ideally we should score them, but simple append works for "filling gaps"
    similar_chunks = combined_chunks[:40]
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Context Management: Using top {len(similar_chunks)} chunks")
    
    # Step 2: EPISTEMIC CLASSIFICATION
    print(f"\n{'='*70}")
    print("Step 2: Epistemic Classification (A/B/C Levels)")
    print(f"{'='*70}")
    
    # Classify each chunk (using the already extracted keywords)
    for chunk in similar_chunks:
        chunk['epistemic_level'] = classify_chunk(keywords, chunk)
    
    # Count levels
    level_counts = {'A': 0, 'B': 0, 'C': 0}
    for chunk in similar_chunks:
        level = chunk.get('epistemic_level', 'C')
        level_counts[level] = level_counts.get(level, 0) + 1
    
    print(f"[EPISTEMIC] Classification results: Level A={level_counts['A']}, Level B={level_counts['B']}, Level C={level_counts['C']}")
    
    # Determine answer mode
    answer_mode = determine_answer_mode(similar_chunks)
    print(f"[EPISTEMIC] Answer Mode: {answer_mode}")
    
    # Build epistemic-aware context
    # Add metadata about total evidence count to help Gemini understand the volume
    evidence_meta = f"[SİSTEM NOTU: Kullanıcının kütüphanesinde '{', '.join(keywords)}' ile ilgili toplam {level_counts['A'] + level_counts['B']} adet doğrudan not bulundu.]"
    
    context = evidence_meta + "\n\n" + build_epistemic_context(similar_chunks, answer_mode)
    
    # Track sources for the citations UI
    sources = []
    for chunk in similar_chunks:
        sources.append({
            'title': chunk.get('title', 'Unknown'),
            'page_number': chunk.get('page_number', 0),
            'similarity_score': chunk.get('score', 0),
            'epistemic_level': chunk.get('epistemic_level', 'C')
        })
    
    # --- GRAPHRAG ENRICHMENT (still valuable for synthesis mode) ---
    if answer_mode == 'SYNTHESIS':
        graph_insight = get_graph_enriched_context(similar_chunks, firebase_uid)
        if graph_insight:
            print(f"[INFO] Adding Graph Insights to prompt (Synthesis Mode)...")
            context = graph_insight + "\n\n" + context
    
    # Step 3: Generate answer with mode-specific prompt
    print(f"\n{'='*70}")
    print(f"Step 3: Generating AI Answer ({answer_mode} Mode)")
    print(f"{'='*70}")
    
    try:
        # Get the appropriate prompt for the detected mode
        prompt = get_prompt_for_mode(answer_mode, context, question)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Sending request to gemini-2.0-flash ({answer_mode} Mode)...")
        
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
        
        # DEBUGGING: Log the raw response text
        if response and hasattr(response, 'text'):
            answer = response.text
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] --- GEMINI RESPONSE START ---")
            print(answer[:500] + "..." if len(answer) > 500 else answer)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] --- GEMINI RESPONSE END ---\n")
            return answer, sources
        else:
            print(f"[WARNING] Gemini returned an empty response or unexpected format")
            return "Üzgünüm, şu an cevap üretemiyorum. Lütfen tekrar deneyin.", sources
            
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] [ERROR] Gemini API failed: {e}")
        import traceback
        traceback.print_exc()
        return "Bağlantı sırasında bir hata oluştu. Lütfen kütüphane notlarını kontrol edin.", sources


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
