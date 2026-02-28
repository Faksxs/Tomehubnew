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
import re
import json
from typing import List, Dict, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dotenv import load_dotenv
import oracledb
from config import settings
from services.llm_client import (
    MODEL_TIER_FLASH,
    MODEL_TIER_LITE,
    ROUTE_MODE_DEFAULT,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    generate_text,
    get_model_for_tier,
)

# Import TomeHub services
from services.embedding_service import get_embedding, batch_get_embeddings
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

# Initialize logger
from utils.logger import get_logger
logger = get_logger("search_service")


from infrastructure.db_manager import DatabaseManager, safe_read_clob



# Import Smart Search Service & Helpers
from services.smart_search_service import (
    perform_search, 
    create_turkish_fuzzy_pattern, 
    parse_and_clean_content,
    generate_query_variations,
    score_with_bm25,
    compute_rrf
)

# Import Graph Service
from services.graph_service import get_graph_candidates, GraphRetrievalError

# Import Re-rank Service
from services.rerank_service import rerank_candidates
from services.network_classifier import classify_network_status
from services.network_classifier import classify_network_status
from services.monitoring import (
    GRAPH_BRIDGES_FOUND,
    SEARCH_DIVERSITY_COUNT,
    SEARCH_RESULT_COUNT,
    L3_PERF_GUARD_APPLIED_TOTAL,
    L3_PHASE_LATENCY_SECONDS,
)
from services.cache_service import get_cache, generate_cache_key
from services.external_kb_service import (
    get_external_graph_candidates,
    get_external_meta,
    maybe_refresh_external_for_explorer_async,
)
from services.analytics_service import (
    is_analytic_word_count,
    extract_target_term,
    count_lemma_occurrences,
    resolve_multiple_book_ids_from_question,
    resolve_all_book_ids,
)

NOISE_SOURCE_ALLOWLIST = {
    "PDF", "EPUB", "PDF_CHUNK", "BOOK",
    "HIGHLIGHT", "INSIGHT", "PERSONAL_NOTE",
    "ARTICLE", "WEBSITE", "GRAPH_RELATION", 
    "UNKNOWN", "OTHER" 
}


def _resolve_user_book_ids(firebase_uid: str) -> set[str]:
    """
    Backward-compatible helper used by compare policy and tests.
    Returns the set of book ids the user can compare against.
    """
    try:
        return {str(bid).strip() for bid in (resolve_all_book_ids(firebase_uid) or []) if str(bid).strip()}
    except Exception:
        return set()


def resolve_book_ids_from_question(firebase_uid: str, question: str) -> List[str]:
    """
    Backward-compatible alias for compare target auto-resolution.
    """
    try:
        return list(resolve_multiple_book_ids_from_question(firebase_uid, question) or [])
    except Exception:
        return []

_REWRITE_TRIGGER_TOKENS = {
    "bu", "bunu", "buna", "bunun", "bundan",
    "su", "sunu", "boyle", "soyle",
    "o", "onu", "ona", "onun", "ondan",
    "bunlar", "onlar", "ikisi", "ikisinin", "ikisinde",
    "ayni", "fark", "farki", "iliski", "ilgili",
    "devam", "peki", "ya", "pekiya",
}

_REWRITE_LEADIN_PHRASES = (
    "peki", "o zaman", "bu durumda", "buna gore",
    "bununla", "bunun icin", "buradan",
)

_REWRITE_GREETING_TOKENS = {
    "merhaba", "selam", "selamlar", "hey", "hi", "hello", "gunaydin",
    "iyiaksamlar", "iyiaksam", "iyigunler",
}

def _passes_noise_guard_for_chunk(chunk: Dict[str, Any]) -> bool:
    if not getattr(settings, "SEARCH_NOISE_GUARD_ENABLED", True):
        return True

    content = str(chunk.get("content_chunk", "") or chunk.get("content", "")).strip()
    title = str(chunk.get("title", "")).strip().lower()
    source_type = str(chunk.get("source_type", "") or chunk.get("type", "")).strip().upper()
    content_lc = content.lower()

    if source_type and source_type not in NOISE_SOURCE_ALLOWLIST:
        return False

    if len(content) < 60:
        return False

    if "website deneme" in content_lc:
        return False

    if source_type in {"WEBSITE", "ARTICLE"} and len(content) < 100:
        return False

    if content_lc.startswith("title:") and len(content) < 220:
        return False

    if content_lc.startswith("author:") and len(content) < 220:
        return False

    if "deneme" in title and len(content) < 180:
        return False

    if "unknown" in title and len(content) < 220:
        return False

    return True

def get_graph_enriched_context(base_results: List[Dict], firebase_uid: str) -> str:
    """
    Traverses the Oracle Property Graph to find "invisible bridges"
    between the retrieved chunks and related concepts.
    """
    if not base_results:
        return ""
        
    if settings.DEBUG_VERBOSE_PIPELINE:
        logger.debug("GraphRAG: analyzing semantic bridges (batched)")
    
    try:
        # Collect IDs for batch processing
        target_results = base_results[:10]
        content_ids = [res.get('id') for res in target_results if res.get('id')]
        
        if not content_ids:
            return ""

        bridges = []
        
        with DatabaseManager.get_read_connection() as conn:
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
                    bridges.append(f"[BRIDGE] {c1_name} is connected to {c2_name} via '{rtype}' relationship.")
        
        GRAPH_BRIDGES_FOUND.observe(len(bridges))
        
        if bridges:
            return "\nSEMANTIC BRIDGES (Graph Insights):\n" + "\n".join(set(bridges))
        return ""
        
    except Exception as e:
        logger.warning("Graph enrichment failed: %s", e)
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
    if settings.DEBUG_VERBOSE_PIPELINE:
        logger.debug("Fetching context for book_id=%s query=%s", book_id, query_text)
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Generate Embeddings & Patterns
                query_embedding = get_embedding(query_text)
                variations = create_turkish_fuzzy_pattern(query_text)
                
                # 2-5. Combined Heavy SQL Query
                # Prioritizes:
                # - Semantic match (Vector Distance)
                # - Keyword match (Turkish Fuzzy)
                
                sql = """
                    SELECT c.content_chunk, c.page_number, c.chunk_index, c.title,
                           (VECTOR_DISTANCE(c.vec_embedding, :bv_vec, COSINE) / NULLIF(c.rag_weight, 0.0001)) as dist
                    FROM TOMEHUB_CONTENT_V2 c
                    WHERE c.item_id = :bv_book_id 
                      AND c.firebase_uid = :bv_uid
                      AND c.AI_ELIGIBLE = 1
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
        logger.error("Context retrieval failed: %s", e)
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
        with DatabaseManager.get_read_connection() as connection:
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
                
                # B3: Batch get embeddings for all query variations (N+1 Elimination)
                unique_queries = list(set(queries))
                q_embeddings = batch_get_embeddings(unique_queries, task_type="retrieval_query")
                
                for q, q_emb in zip(unique_queries, q_embeddings):
                    # A. Vector Retrieval
                    if q_emb:
                        vector_sql = """
                        SELECT c.content_chunk, c.page_number, c.title, c.content_type,
                               (VECTOR_DISTANCE(c.vec_embedding, :p_vec, COSINE) / NULLIF(c.rag_weight, 0.0001)) as dist
                        FROM TOMEHUB_CONTENT_V2 c
                        WHERE c.firebase_uid = :p_uid
                          AND c.AI_ELIGIBLE = 1
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

                    # B. Keyword/SQL Retrieval (Tokenized Lemma Search)
                    # Uses lemmatized tokens to catch morphological variations
                    if q == query_text:
                        from utils.text_utils import get_lemmas
                        lemmas = get_lemmas(q)
                        # Filter out very short or stop words
                        keywords = [l for l in lemmas if len(l) > 2][:5]  # Max 5 keywords
                        
                        if keywords:
                            # Build OR conditions for each keyword
                            conditions = []
                            params = {"p_uid": firebase_uid}
                            for i, kw in enumerate(keywords):
                                conditions.append(f"LOWER(c.content_chunk) LIKE :kw{i}")
                                params[f"kw{i}"] = f"%{kw.lower()}%"
                            
                            keyword_sql = f"""
                            SELECT c.content_chunk, c.page_number, c.title, c.content_type
                            FROM TOMEHUB_CONTENT_V2 c
                            WHERE c.firebase_uid = :p_uid
                              AND c.AI_ELIGIBLE = 1
                            AND ({" OR ".join(conditions)})
                            FETCH FIRST 25 ROWS ONLY
                            """
                            cursor.execute(keyword_sql, params)
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
                                        'vector_score': 0.0,
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
                
                # Fuse 3 Lists (Order matters: BM25 first for weighted RRF)
                rrf_scores = compute_rrf([bm25_ranking, vector_ranking, graph_ranking], k=60)
                
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
                    
                # [Observability] Record Metrics
                SEARCH_RESULT_COUNT.observe(len(reranked_results))
                
                unique_books = set(c.get('title') for c in selected_chunks)
                SEARCH_DIVERSITY_COUNT.observe(len(unique_books))
                
                logger.info("Hybrid Search Finished", extra={
                    "final_count": len(selected_chunks),
                    "total_duration_ms": int((time.time() - start_time) * 1000)
                })
                return selected_chunks

    except Exception as e:
        logger.error("Hybrid Search Failed", extra={"error": str(e)}, exc_info=True)
        return None


from concurrent.futures import ThreadPoolExecutor

def _normalize_ascii(text: str) -> str:
    return (
        (text or "")
        .replace("ç", "c").replace("Ç", "C")
        .replace("ğ", "g").replace("Ğ", "G")
        .replace("ı", "i").replace("İ", "I")
        .replace("ö", "o").replace("Ö", "O")
        .replace("ş", "s").replace("Ş", "S")
        .replace("ü", "u").replace("Ü", "U")
    )


def _should_rewrite_with_history(question: str, history: List[Dict]) -> bool:
    if not history:
        return False
    q = (question or "").strip()
    if not q:
        return False

    q_ascii = _normalize_ascii(q).lower()
    tokens = re.findall(r"[^\W_]+", q_ascii, flags=re.UNICODE)
    token_set = set(tokens)

    if len(tokens) <= 4:
        return True
    if any(q_ascii.startswith(prefix) for prefix in _REWRITE_LEADIN_PHRASES):
        return True
    if token_set.intersection(_REWRITE_TRIGGER_TOKENS):
        return True
    if "?" in q and len(tokens) <= 8:
        return True
    return False


def _rewrite_history_fingerprint(history: List[Dict]) -> str:
    if not history:
        return ""
    parts = []
    for msg in history[-settings.CHAT_PROMPT_TURNS:]:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", "")).strip()
        if content:
            parts.append(f"{role}:{content[:220]}")
    return "\n".join(parts)


def _rewrite_guard_skip_reason(question: str) -> Optional[str]:
    """
    Optional Layer-3 perf guard: skip rewrite if query is already specific enough.
    Flag-off path must preserve legacy behavior.
    """
    if not getattr(settings, "L3_PERF_REWRITE_GUARD_ENABLED", False):
        return None

    q = (question or "").strip()
    if not q:
        return "empty_query"

    q_ascii = _normalize_ascii(q).lower()
    tokens = re.findall(r"[^\W_]+", q_ascii, flags=re.UNICODE)
    if not tokens:
        return "empty_query"

    if len(tokens) == 1 and tokens[0] in _REWRITE_GREETING_TOKENS:
        return "standalone_greeting"

    if len(tokens) == 1:
        return None

    token_set = set(tokens)
    has_leadin = any(q_ascii.startswith(prefix) for prefix in _REWRITE_LEADIN_PHRASES)
    has_trigger = bool(token_set.intersection(_REWRITE_TRIGGER_TOKENS))
    has_short_question_signal = "?" in q and len(tokens) <= 8

    if (
        2 <= len(tokens) <= 7
        and not has_leadin
        and not has_trigger
        and not has_short_question_signal
    ):
        return "standalone_short_query"

    if not has_leadin and not has_trigger and not has_short_question_signal:
        return "lexically_specific_query"
    return None


def _infer_explorer_book_ids(question_results: List[Dict[str, Any]], hard_limit: int = 3) -> List[str]:
    counts: Dict[str, int] = {}
    for chunk in question_results[:60]:
        book_id = str(chunk.get("book_id") or "").strip()
        if not book_id:
            continue
        counts[book_id] = counts.get(book_id, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    return [book_id for book_id, _ in ordered[: max(1, hard_limit)]]


def rewrite_query_with_history(question: str, history: List[Dict]) -> str:
    """
    Rewrite short/ambiguous follow-up queries into standalone form.
    Uses lightweight gating + cache to avoid LLM rewrite on every turn.
    """
    if not history:
        return question
    skip_reason = _rewrite_guard_skip_reason(question)
    if skip_reason:
        try:
            L3_PERF_GUARD_APPLIED_TOTAL.labels(guard_name=f"rewrite_skip_{skip_reason}").inc()
        except Exception:
            pass
        return question
    if not _should_rewrite_with_history(question, history):
        return question

    try:
        history_str = ""
        for msg in history[-settings.CHAT_PROMPT_TURNS:]:
            role = "Kullanıcı" if msg['role'] == 'user' else "Asistan"
            history_str += f"{role}: {msg['content']}\n"

        cache = get_cache()
        cache_key = None
        if cache:
            history_fingerprint = _rewrite_history_fingerprint(history)
            cache_key = generate_cache_key(
                service="query_rewrite",
                query=f"{question}\n{history_fingerprint}",
                firebase_uid="",
                book_id=None,
                limit=settings.CHAT_PROMPT_TURNS,
                version=settings.LLM_MODEL_VERSION
            )
            cached = cache.get(cache_key)
            if isinstance(cached, str) and cached.strip():
                return cached

        prompt = f"""
        Aşağıdaki konuşma geçmişine dayanarak, kullanıcının son sorusunu bağlamı içerecek şekilde (tek başına anlamlı) yeniden yaz.
        Eğer soru zaten tam ve anlaşılırsa, olduğu gibi bırak.
        Sadece yeniden yazılmış soruyu döndür. Dil: Türkçe.

        GEÇMİŞ:
        {history_str}

        SON SORU: {question}

        YENİDEN YAZILMIŞ SORU:
        """

        model = get_model_for_tier(MODEL_TIER_LITE)
        result = generate_text(
            model=model,
            prompt=prompt,
            task="query_rewrite",
            model_tier=MODEL_TIER_LITE,
            timeout_s=4.0,
        )
        rewritten = result.text.strip() if result and result.text else question
        if not rewritten:
            return question
        if len(rewritten) > max(220, len(question) * 3):
            return question
        if cache and cache_key:
            cache.set(cache_key, rewritten, ttl=1800)
        return rewritten
    except Exception as e:
        logger.warning("Query rewriting failed: %s", e)
        return question


def _compute_quote_target_count(confidence_score: float, chunk_count: int) -> int:
    min_quotes = int(getattr(settings, "L3_QUOTE_DYNAMIC_MIN", 2) or 2)
    max_quotes = int(getattr(settings, "L3_QUOTE_DYNAMIC_MAX", 5) or 5)
    if max_quotes < min_quotes:
        max_quotes = min_quotes
    default_quotes = max(2, min(5, min_quotes))

    if not bool(getattr(settings, "L3_QUOTE_DYNAMIC_COUNT_ENABLED", False)):
        return min(default_quotes, max(1, int(chunk_count or 0))) if chunk_count else default_quotes

    score = float(confidence_score or 0.0)
    if score >= 4.6:
        desired = max_quotes
    elif score >= 4.1:
        desired = min(max_quotes, max(min_quotes, 4))
    elif score >= 3.4:
        desired = min(max_quotes, max(min_quotes, 3))
    else:
        desired = min_quotes
    if chunk_count > 0:
        desired = min(desired, int(chunk_count))
    return max(min_quotes, min(max_quotes, desired))


def _read_search_log_strategy_details_json(cursor, search_log_id: int) -> Dict[str, Any]:
    """Read STRATEGY_DETAILS safely, with fallback that avoids direct CLOB fetch edge cases."""
    try:
        cursor.execute(
            """
            SELECT STRATEGY_DETAILS
            FROM TOMEHUB_SEARCH_LOGS
            WHERE ID = :p_id
            """,
            {"p_id": search_log_id},
        )
        row = cursor.fetchone()
        if not row or row[0] is None:
            return {}
        raw = safe_read_clob(row[0]) or "{}"
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as err:
        err_text = str(err)
        # Oracle may reject certain direct CLOB access paths in some environments/drivers.
        # Fallback to chunked DBMS_LOB.SUBSTR reads to avoid CLOB object handling.
        if "ORA-22848" not in err_text:
            raise

        cursor.execute(
            """
            SELECT DBMS_LOB.GETLENGTH(STRATEGY_DETAILS)
            FROM TOMEHUB_SEARCH_LOGS
            WHERE ID = :p_id
            """,
            {"p_id": search_log_id},
        )
        len_row = cursor.fetchone()
        total_len = int(len_row[0] or 0) if len_row else 0
        if total_len <= 0:
            return {}

        chunks: List[str] = []
        step = 32767
        offset = 1
        while offset <= total_len:
            cursor.execute(
                """
                SELECT DBMS_LOB.SUBSTR(STRATEGY_DETAILS, :p_len, :p_off)
                FROM TOMEHUB_SEARCH_LOGS
                WHERE ID = :p_id
                """,
                {"p_len": step, "p_off": offset, "p_id": search_log_id},
            )
            part_row = cursor.fetchone()
            if not part_row or part_row[0] is None:
                break
            part = part_row[0]
            chunks.append(part if isinstance(part, str) else safe_read_clob(part))
            offset += step

        try:
            parsed = json.loads("".join(chunks) or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            logger.warning(
                "Failed to parse STRATEGY_DETAILS via CLOB fallback id=%s (ORA-22848 path)",
                search_log_id,
            )
            return {}


def _append_search_log_diagnostics(search_log_id: Optional[int], diagnostics: Dict[str, Any]) -> None:
    if not search_log_id:
        return
    if not bool(getattr(settings, "SEARCH_LOG_DIAGNOSTICS_PERSIST_ENABLED", False)):
        return
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                payload: Dict[str, Any] = {}
                try:
                    payload = _read_search_log_strategy_details_json(cursor, int(search_log_id))
                except Exception as col_err:
                    if "ORA-00904" in str(col_err):
                        return
                    payload = {}
                payload.update(diagnostics or {})

                cursor.execute(
                    """
                    UPDATE TOMEHUB_SEARCH_LOGS
                    SET STRATEGY_DETAILS = :p_payload
                    WHERE ID = :p_id
                    """,
                    {
                        "p_payload": json.dumps(payload, ensure_ascii=False),
                        "p_id": search_log_id,
                    },
                )
            conn.commit()
    except Exception as e:
        logger.warning("Failed to append search log diagnostics id=%s: %s", search_log_id, e)
def get_rag_context(question: str, firebase_uid: str, context_book_id: str = None, chat_history: List[Dict] = None, mode: str = 'STANDARD', resource_type: Optional[str] = None, limit: Optional[int] = None, offset: int = 0, session_id: Optional[int | str] = None, scope_mode: str = "GLOBAL", apply_scope_policy: bool = False, compare_mode: Optional[str] = None, target_book_ids: Optional[List[str]] = None, visibility_scope: str = "default", content_type: Optional[str] = None, ingestion_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
    if settings.DEBUG_VERBOSE_PIPELINE:
        logger.debug("Retrieving RAG context for mode=%s question=%s", mode, question)
    
    # 0. Query Rewriting (Memory Layer)
    effective_query = question
    if chat_history:
        effective_query = rewrite_query_with_history(question, chat_history)
        if effective_query != question and settings.DEBUG_VERBOSE_PIPELINE:
            logger.debug(
                "Contextual query rewrite applied: original=%s rewritten=%s",
                question,
                effective_query,
            )

    # 1. Keyword Extraction & Intent Classification
    # We classify intent EARLY now (Phase 4) to guide retrieval strategy
    intent, complexity = classify_question_intent(effective_query)
    keywords = extract_core_concepts(effective_query)
    
    if settings.DEBUG_VERBOSE_PIPELINE:
        logger.debug("RAG intent=%s complexity=%s", intent, complexity)
    
    all_chunks_map = {}

    # ── Compare Policy: Per-Book Fan-Out Retrieval ──────────────────
    compare_focus_query = (keywords[0] if keywords else effective_query).strip() or effective_query
    _compare_targets = [str(b).strip() for b in (target_book_ids or []) if str(b or "").strip()]
    auto_resolved_target_book_ids: List[str] = []
    unauthorized_target_book_ids: List[str] = []
    per_book_evidence_count: Dict[str, int] = {}
    target_books_used: List[str] = []
    target_books_truncated = False
    compare_degrade_reason = ""
    evidence_policy = "standard"
    latency_budget_hit = False

    compare_mode_norm = str(compare_mode or "").strip().upper()
    compare_policy_enabled = bool(getattr(settings, "SEARCH_COMPARE_POLICY_ENABLED", False))
    if not compare_policy_enabled:
        canary_uids = getattr(settings, "SEARCH_COMPARE_CANARY_UIDS", set()) or set()
        compare_policy_enabled = str(firebase_uid) in {str(uid).strip() for uid in canary_uids}

    q_norm = (effective_query or "").lower()
    notes_vs_single_requested = bool(
        context_book_id and not _compare_targets and any(tok in q_norm for tok in ("not", "note", "highlight", "vurgu"))
    )

    if notes_vs_single_requested:
        _compare_targets = [str(context_book_id).strip(), "__USER_NOTES__"]
    elif not _compare_targets:
        resolved_ids = resolve_book_ids_from_question(firebase_uid, effective_query)
        if len(resolved_ids) >= 2:
            auto_resolved_target_book_ids = [str(b).strip() for b in resolved_ids if str(b).strip()]
            _compare_targets = list(auto_resolved_target_book_ids)
            if settings.DEBUG_VERBOSE_PIPELINE:
                logger.debug("Auto-resolved compare targets from query: %s", _compare_targets)

    authorized_book_ids = _resolve_user_book_ids(firebase_uid)
    filtered_targets: List[str] = []
    for bid in _compare_targets:
        if not bid:
            continue
        if bid == "__USER_NOTES__":
            if bid not in filtered_targets:
                filtered_targets.append(bid)
            continue
        if authorized_book_ids and bid not in authorized_book_ids:
            unauthorized_target_book_ids.append(bid)
            continue
        if bid not in filtered_targets:
            filtered_targets.append(bid)
    _compare_targets = filtered_targets

    compare_requested = compare_mode_norm == "EXPLICIT_ONLY" or compare_policy_enabled or notes_vs_single_requested
    compare_applied = compare_requested and len(_compare_targets) >= 2

    if compare_applied:
        max_targets = max(2, int(getattr(settings, "SEARCH_COMPARE_TARGET_MAX", 8) or 8))
        if len(_compare_targets) > max_targets:
            _compare_targets = _compare_targets[:max_targets]
            target_books_truncated = True

        target_books_used = list(_compare_targets)
        evidence_policy = "TEXT_PRIMARY_NOTES_SECONDARY_V1"

        per_book_primary_limit = max(1, int(getattr(settings, "SEARCH_COMPARE_PRIMARY_PER_BOOK", 6) or 6))
        per_book_secondary_limit = max(0, int(getattr(settings, "SEARCH_COMPARE_SECONDARY_PER_BOOK", 2) or 2))
        timeout_ms = max(50, int(getattr(settings, "SEARCH_COMPARE_TIMEOUT_MS", 2500) or 2500))
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        search_depth = 'deep' if mode == 'EXPLORER' else 'normal'
        compare_primary_rows: List[Dict[str, Any]] = []
        compare_secondary_rows: List[Dict[str, Any]] = []

        for bid in _compare_targets:
            if time.monotonic() > deadline:
                latency_budget_hit = True
                compare_degrade_reason = "timeout_partial_results"
                break

            try:
                if bid == "__USER_NOTES__":
                    rows, _meta = perform_search(
                        compare_focus_query,
                        firebase_uid,
                        intent=intent,
                        book_id=None,
                        search_depth=search_depth,
                        resource_type="ALL_NOTES",
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                        limit=per_book_secondary_limit,
                        offset=0,
                        session_id=session_id,
                    )
                    count = 0
                    for c in (rows or []):
                        c2 = dict(c)
                        c2["_compare_target"] = True
                        c2["_compare_book_id"] = "__USER_NOTES__"
                        c2["_compare_secondary"] = True
                        compare_secondary_rows.append(c2)
                        count += 1
                    per_book_evidence_count[bid] = count
                else:
                    rows, _meta = perform_search(
                        compare_focus_query,
                        firebase_uid,
                        intent=intent,
                        book_id=bid,
                        search_depth=search_depth,
                        resource_type="BOOK",
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                        limit=per_book_primary_limit,
                        offset=0,
                        session_id=session_id,
                    )
                    count = 0
                    for c in (rows or []):
                        c2 = dict(c)
                        c2["_compare_target"] = True
                        c2["_compare_book_id"] = bid
                        c2["_compare_primary"] = True
                        compare_primary_rows.append(c2)
                        count += 1
                    per_book_evidence_count[bid] = count
            except Exception as exc:
                logger.error("Compare fan-out search failed for target %s: %s", bid, exc)
                per_book_evidence_count[bid] = 0

        max_secondary_allowed = max(1, len(compare_primary_rows) // 3) if compare_primary_rows else 0
        if max_secondary_allowed and len(compare_secondary_rows) > max_secondary_allowed:
            compare_secondary_rows = compare_secondary_rows[:max_secondary_allowed]

        for c in compare_primary_rows + compare_secondary_rows:
            key = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
            if key not in all_chunks_map:
                all_chunks_map[key] = c

        if settings.DEBUG_VERBOSE_PIPELINE:
            logger.debug(
                "Compare fan-out results: targets=%s evidence=%s focus_query=%s",
                _compare_targets, per_book_evidence_count, compare_focus_query,
            )

    # 2. Parallel Retrieval (Vector + Graph)
    def run_vector_search():
        # Pass intent to guide filtering (Short/Long bias)
        # Returns (results, metadata)
        search_depth = 'deep' if mode == 'EXPLORER' else 'normal'
        # When compare fan-out already ran, do a broad (no book_id) search to fill gaps
        effective_book_id = None if compare_applied else context_book_id
        return perform_search(
            effective_query,
            firebase_uid,
            intent=intent,
            book_id=effective_book_id,
            search_depth=search_depth,
            resource_type=resource_type,
            limit=limit,
            offset=offset,
            session_id=session_id,
            visibility_scope=visibility_scope,
            content_type=content_type,
            ingestion_type=ingestion_type,
        )
        
    def run_graph_search():
        try:
            return get_graph_candidates(effective_query, firebase_uid, limit=limit or 15, offset=offset)
        except:
            return []

    graph_results = []
    question_results = []
    vec_meta = {}
    graph_timeout_triggered = False
    graph_latency_budget_applied = False
    graph_skipped_by_intent = False
    noise_guard_applied = bool(getattr(settings, "SEARCH_NOISE_GUARD_ENABLED", True))
    graph_filtered_count = 0
    external_graph_results: List[Dict[str, Any]] = []
    external_kb_used = False
    external_graph_candidates_count = 0
    academic_scope = False
    wikidata_qid = None
    openalex_used = False
    dbpedia_used = False
    orkg_used = False
    
    degradations = []
    
    # Replaced Sentry Spans with Standard Threading
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_vector = executor.submit(run_vector_search)
        future_graph = None
        if getattr(settings, "SEARCH_GRAPH_DIRECT_SKIP", True) and intent in {"DIRECT", "FOLLOW_UP"}:
            graph_skipped_by_intent = True
        else:
            future_graph = executor.submit(run_graph_search)
            graph_latency_budget_applied = True

        try:
            # Result is now (list, dict)
            res_v, meta_v = future_vector.result()
            question_results = res_v or []
            vec_meta = meta_v
            search_log_id = meta_v.get('search_log_id')
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            degradations.append({"component": "VECTOR_SEARCH", "reason": str(e), "severity": "HIGH"})
            vec_meta = {}
            search_log_id = None
            
        if future_graph is not None:
            try:
                timeout_sec = max(0.05, float(getattr(settings, "SEARCH_GRAPH_TIMEOUT_MS", 120)) / 1000.0)
                graph_results = future_graph.result(timeout=timeout_sec)
            except FutureTimeoutError:
                graph_timeout_triggered = True
                graph_results = []
                future_graph.cancel()
                degradations.append({
                    "component": "GRAPH_SERVICE",
                    "reason": f"timeout>{int(getattr(settings, 'SEARCH_GRAPH_TIMEOUT_MS', 120))}ms",
                    "severity": "MEDIUM"
                })
            except GraphRetrievalError as gre:
                logger.error(f"Graph retrieval failed (Fail Loud): {gre}")
                degradations.append({"component": "GRAPH_SERVICE", "reason": str(gre), "severity": "HIGH"})
                graph_results = []
            except Exception as e:
                logger.error(f"Graph retrieval unexpected error: {e}")
                degradations.append({"component": "GRAPH_SERVICE", "reason": str(e), "severity": "HIGH"})
                graph_results = []

    # Merge Results
    if question_results:
        for c in question_results:
            key = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
            existing = all_chunks_map.get(key)
            if existing and existing.get("_compare_target") and not c.get("_compare_target"):
                continue
            all_chunks_map[key] = c

    if graph_results:
        for c in graph_results:
            # Graph results now have a calculated 'graph_score' (0.5 - 1.0)
            g_score = c.get('graph_score', 0.5)
            
            c_std = {
                'title': c.get('title', 'Unknown'),
                'content_chunk': c.get('content', '') or c.get('content_chunk', ''),
                'page_number': c.get('page', 0),
                'source_type': 'GRAPH_RELATION',
                'epistemic_level': 'B', # Default, will be adjusted
                'score': g_score,       # Use graph score as the similarity score
                'graph_score': g_score 
            }
            if not _passes_noise_guard_for_chunk(c_std):
                graph_filtered_count += 1
                continue
            key = f"{c_std['title']}_{str(c_std['content_chunk'])[:20]}"
            if key not in all_chunks_map:
                all_chunks_map[key] = c_std

    # Optional External KB candidate injection.
    # Explorer only, but no longer requires explicit context_book_id.
    if mode == "EXPLORER" and bool(getattr(settings, "EXTERNAL_KB_ENABLED", False)):
        candidate_book_ids: List[str] = []
        if context_book_id:
            candidate_book_ids.append(str(context_book_id).strip())
        else:
            candidate_book_ids = _infer_explorer_book_ids(question_results, hard_limit=3)
            if not candidate_book_ids:
                candidate_book_ids = _infer_explorer_book_ids(list(all_chunks_map.values()), hard_limit=3)

        ext_limit_total = max(1, min(int(getattr(settings, "EXTERNAL_KB_MAX_CANDIDATES", 5) or 5), 10))
        per_book_limit = max(1, min(3, ext_limit_total))
        seen_external = set()

        for candidate_book_id in candidate_book_ids:
            if not candidate_book_id:
                continue
            external_meta = get_external_meta(candidate_book_id, firebase_uid)
            academic_scope = academic_scope or bool(external_meta.get("academic_scope"))
            if not wikidata_qid:
                wikidata_qid = external_meta.get("wikidata_qid")
            openalex_used = openalex_used or bool(external_meta.get("openalex_id"))
            dbpedia_used = dbpedia_used or bool(external_meta.get("dbpedia_uri"))
            orkg_used = orkg_used or bool(external_meta.get("orkg_id"))

            try:
                maybe_refresh_external_for_explorer_async(
                    book_id=candidate_book_id,
                    firebase_uid=firebase_uid,
                )
            except Exception:
                pass

            book_external = get_external_graph_candidates(
                book_id=candidate_book_id,
                firebase_uid=firebase_uid,
                question=effective_query,
                limit=per_book_limit,
                min_confidence=float(getattr(settings, "EXTERNAL_KB_MIN_CONFIDENCE", 0.45)),
            )
            for candidate in book_external:
                c_key = f"{candidate.get('title','')}_{str(candidate.get('content_chunk',''))[:80]}"
                if c_key in seen_external:
                    continue
                seen_external.add(c_key)
                external_graph_results.append(candidate)
                if len(external_graph_results) >= ext_limit_total:
                    break
            if len(external_graph_results) >= ext_limit_total:
                break

        external_graph_candidates_count = len(external_graph_results)
        external_kb_used = external_graph_candidates_count > 0

        for c in external_graph_results:
            c_std = {
                "title": c.get("title", "External KB"),
                "content_chunk": c.get("content_chunk", ""),
                "page_number": c.get("page_number", 0),
                "source_type": "EXTERNAL_KB",
                "epistemic_level": "B",
                "score": c.get("score", 0.5),
                "external_weight": float(
                    c.get("external_weight", getattr(settings, "EXTERNAL_KB_GRAPH_WEIGHT", 0.15))
                ),
            }
            key = f"{c_std['title']}_{str(c_std['content_chunk'])[:20]}"
            if key not in all_chunks_map:
                all_chunks_map[key] = c_std

    # 3. Supplementary Keyword Search (Gap Filling)
    # Only run when primary retrieval is sparse to avoid extra latency.
    supplementary_search_applied = False
    supplementary_search_skipped_reason = None
    gap_fill_threshold = max(10, min(20, (limit or 20)))
    should_run_supplementary = False

    if not keywords:
        supplementary_search_skipped_reason = "no_keywords"
    else:
        if not getattr(settings, "L3_PERF_SUPPLEMENTARY_GATE_ENABLED", False):
            should_run_supplementary = len(all_chunks_map) < gap_fill_threshold
        else:
            low_evidence_threshold = max(4, min(10, (limit or 20) // 2))
            sparse_primary = len(question_results) <= low_evidence_threshold
            sparse_combined = len(all_chunks_map) < gap_fill_threshold
            should_run_supplementary = sparse_primary and sparse_combined
            if not should_run_supplementary:
                supplementary_search_skipped_reason = "sufficient_primary_evidence"
                try:
                    L3_PERF_GUARD_APPLIED_TOTAL.labels(
                        guard_name="supplementary_gate_skip_sufficient_evidence"
                    ).inc()
                except Exception:
                    pass

    if should_run_supplementary:
        search_kw = " ".join(keywords[:2]).strip()
        if search_kw and search_kw != effective_query:
            supplementary_search_applied = True
            kw_limit = min(14, max(8, (limit or 12)))
            kw_res, _ = perform_search(
                search_kw,
                firebase_uid,
                intent=intent,
                resource_type=resource_type,
                visibility_scope=visibility_scope,
                content_type=content_type,
                ingestion_type=ingestion_type,
                limit=kw_limit,
                offset=0,
                session_id=session_id,
                result_mix_policy="lexical_then_semantic_tail",
                semantic_tail_cap=getattr(settings, "SEARCH_SMART_SEMANTIC_TAIL_CAP", 6),
            )
            if kw_res:
                for c in kw_res:
                    key = f"{c.get('title','')}_{str(c.get('content_chunk',''))[:20]}"
                    if key not in all_chunks_map:
                        all_chunks_map[key] = c
        else:
            supplementary_search_skipped_reason = "keyword_variant_missing"
    
    combined_chunks = list(all_chunks_map.values())
    
    if not combined_chunks and mode != 'EXPLORER':
        return None
        
    # Truncate if too many
    if len(combined_chunks) > 100:
        combined_chunks = combined_chunks[:100]

    # 4. Epistemic Scoring (Already have intent)
    # intent, complexity = classify_question_intent(question) # MOVED UP
    
    for chunk in combined_chunks:
        classify_chunk(keywords, chunk)
        
        # CRITICAL: Graph Results Re-Scoring
        # classify_chunk may give 0 score if no keywords match (which is the point of "Invisible Bridges")
        # We must restore the score based on the graph confidence weight.
        if chunk.get('source_type') == 'GRAPH_RELATION':
            g_score = chunk.get('graph_score', 0.5)
            # Map 0.5-1.0 range to Answerability Score 1.5-4.0
            # 0.5 -> 1.5 (Level B)
            # 1.0 -> 3.5 (Level A - strong definition/citation)
            boost = 1.5 + (g_score - 0.5) * 4.0 
            
            # Apply boost if it's higher than the keyword-based score
            if boost > chunk.get('answerability_score', 0):
                chunk['answerability_score'] = boost
                
                # Re-assign Level based on new score
                if boost >= 3.0:
                    chunk['epistemic_level'] = 'A'
                elif boost >= 1.0:
                    chunk['epistemic_level'] = 'B'
        elif chunk.get('source_type') == 'EXTERNAL_KB':
            ext_weight = float(chunk.get('external_weight', getattr(settings, "EXTERNAL_KB_GRAPH_WEIGHT", 0.15)))
            ext_boost = max(0.4, min(1.3, ext_weight * 3.2))
            if ext_boost > chunk.get('answerability_score', 0):
                chunk['answerability_score'] = ext_boost
                chunk['epistemic_level'] = 'B'
        
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

        if chunk.get('source_type') == 'EXTERNAL_KB':
            ext_weight = float(chunk.get('external_weight', getattr(settings, "EXTERNAL_KB_GRAPH_WEIGHT", 0.15)))
            return base * max(0.05, min(0.30, ext_weight))
        
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

    retrieval_fusion_mode = vec_meta.get("retrieval_fusion_mode", "concat")
    vector_retrieval_path = vec_meta.get("retrieval_path", "hybrid")
    retrieval_path = (
        f"{vector_retrieval_path}+graph"
        if graph_latency_budget_applied and not graph_skipped_by_intent
        else vector_retrieval_path
    )
    router_mode = vec_meta.get("router_mode", "static")
    router_reason = vec_meta.get("router_reason")
    retrieval_mode = vec_meta.get("retrieval_mode", "balanced")
    selected_buckets = vec_meta.get("selected_buckets", [])
    executed_strategies = vec_meta.get("executed_strategies", [])
    expansion_skipped_reason = vec_meta.get("expansion_skipped_reason")
    odl_rescue_applied = bool(vec_meta.get("odl_rescue_applied", False))
    odl_rescue_reason = vec_meta.get("odl_rescue_reason")
    odl_rescue_timed_out = bool(vec_meta.get("odl_rescue_timed_out", False))
    odl_rescue_latency_ms = vec_meta.get("odl_rescue_latency_ms")
    odl_rescue_candidates_added = int(vec_meta.get("odl_rescue_candidates_added", 0) or 0)
    odl_rescue_candidates_topk = int(vec_meta.get("odl_rescue_candidates_topk", 0) or 0)
    odl_shadow_status = vec_meta.get("odl_shadow_status")

    dynamic_confidence = max(0.5, min(5.0, float(avg_conf or 0.0)))
    source_diversity_count = len(
        {
            str(c.get("title") or "").strip().lower()
            for c in final_chunks
            if str(c.get("title") or "").strip()
        }
    )
    source_type_diversity_count = len(
        {
            str(c.get("source_type") or "").strip().upper()
            for c in final_chunks
            if str(c.get("source_type") or "").strip()
        }
    )
    level_a_count = sum(1 for c in final_chunks if c.get('epistemic_level') == 'A')
    level_b_count = sum(1 for c in final_chunks if c.get('epistemic_level') == 'B')
    level_c_count = sum(1 for c in final_chunks if c.get('epistemic_level') == 'C')
    _append_search_log_diagnostics(
        search_log_id,
        {
            "vector_candidates_count": len(question_results),
            "graph_candidates_count": len(graph_results),
            "external_graph_candidates_count": external_graph_candidates_count,
            "retrieval_fusion_mode": retrieval_fusion_mode,
            "degradations": degradations,
            "retrieval_path": retrieval_path,
            "latency_budget_applied": graph_latency_budget_applied,
            "graph_timeout_triggered": graph_timeout_triggered,
            "graph_skipped_by_intent": graph_skipped_by_intent,
            "source_diversity_count": source_diversity_count,
            "source_type_diversity_count": source_type_diversity_count,
            "level_counts": {"A": level_a_count, "B": level_b_count, "C": level_c_count},
            "odl_rescue_applied": odl_rescue_applied,
            "odl_rescue_reason": odl_rescue_reason,
            "odl_rescue_timed_out": odl_rescue_timed_out,
            "odl_rescue_latency_ms": odl_rescue_latency_ms,
            "odl_rescue_candidates_added": odl_rescue_candidates_added,
            "odl_rescue_candidates_topk": odl_rescue_candidates_topk,
            "odl_shadow_status": odl_shadow_status,
        },
    )

    return {
        "chunks": final_chunks,
        "intent": intent,
        "complexity": complexity,
        "mode": answer_mode,
        "confidence": dynamic_confidence,
        "network_status": network_info["status"],
        "network_reason": network_info["reason"],
        "keywords": keywords,
        "search_log_id": search_log_id,
        "graph_candidates_count": len(graph_results),
        "external_graph_candidates_count": external_graph_candidates_count,
        "vector_candidates_count": len(question_results),
        "source_diversity_count": source_diversity_count,
        "source_type_diversity_count": source_type_diversity_count,
        "academic_scope": academic_scope,
        "external_kb_used": external_kb_used,
        "wikidata_qid": wikidata_qid,
        "openalex_used": openalex_used,
        "dbpedia_used": dbpedia_used,
        "orkg_used": orkg_used,
        "retrieval_fusion_mode": retrieval_fusion_mode,
        "retrieval_path": retrieval_path,
        "router_mode": router_mode,
        "router_reason": router_reason,
        "retrieval_mode": retrieval_mode,
        "selected_buckets": selected_buckets,
        "executed_strategies": executed_strategies,
        "latency_budget_applied": graph_latency_budget_applied,
        "graph_timeout_triggered": graph_timeout_triggered,
        "graph_skipped_by_intent": graph_skipped_by_intent,
        "noise_guard_applied": noise_guard_applied,
        "noise_guard_filtered_graph_count": graph_filtered_count,
        "supplementary_keyword_search_applied": supplementary_search_applied,
        "supplementary_search_skipped_reason": supplementary_search_skipped_reason,
        "expansion_skipped_reason": expansion_skipped_reason,
        "odl_rescue_applied": odl_rescue_applied,
        "odl_rescue_reason": odl_rescue_reason,
        "odl_rescue_timed_out": odl_rescue_timed_out,
        "odl_rescue_latency_ms": odl_rescue_latency_ms,
        "odl_rescue_candidates_added": odl_rescue_candidates_added,
        "odl_rescue_candidates_topk": odl_rescue_candidates_topk,
        "odl_shadow_status": odl_shadow_status,
        "compare_applied": compare_applied,
        "target_books_used": target_books_used,
        "target_books_truncated": target_books_truncated,
        "unauthorized_target_book_ids": unauthorized_target_book_ids,
        "auto_resolved_target_book_ids": auto_resolved_target_book_ids,
        "compare_focus_query": compare_focus_query,
        "latency_budget_hit": latency_budget_hit,
        "evidence_policy": evidence_policy,
        "per_book_evidence_count": per_book_evidence_count,
        "compare_degrade_reason": compare_degrade_reason,
        "compare_mode": compare_mode,
        "level_counts": {
            'A': level_a_count,
            'B': level_b_count,
            'C': level_c_count,
        },
        "metadata": {
            "degradations": degradations,
            "status": "partial" if degradations else "healthy",
            "search_log_id": search_log_id,
            "graph_candidates_count": len(graph_results),
            "external_graph_candidates_count": external_graph_candidates_count,
            "vector_candidates_count": len(question_results),
            "source_diversity_count": source_diversity_count,
            "source_type_diversity_count": source_type_diversity_count,
            "academic_scope": academic_scope,
            "external_kb_used": external_kb_used,
            "wikidata_qid": wikidata_qid,
            "openalex_used": openalex_used,
            "dbpedia_used": dbpedia_used,
            "orkg_used": orkg_used,
            "retrieval_fusion_mode": retrieval_fusion_mode,
            "retrieval_path": retrieval_path,
            "router_mode": router_mode,
            "router_reason": router_reason,
            "retrieval_mode": retrieval_mode,
            "latency_budget_applied": graph_latency_budget_applied,
            "graph_timeout_triggered": graph_timeout_triggered,
            "graph_skipped_by_intent": graph_skipped_by_intent,
            "noise_guard_applied": noise_guard_applied,
            "noise_guard_filtered_graph_count": graph_filtered_count,
            "supplementary_keyword_search_applied": supplementary_search_applied,
            "supplementary_search_skipped_reason": supplementary_search_skipped_reason,
            "expansion_skipped_reason": expansion_skipped_reason,
            "odl_rescue_applied": odl_rescue_applied,
            "odl_rescue_reason": odl_rescue_reason,
            "odl_rescue_timed_out": odl_rescue_timed_out,
            "odl_rescue_latency_ms": odl_rescue_latency_ms,
            "odl_rescue_candidates_added": odl_rescue_candidates_added,
            "odl_rescue_candidates_topk": odl_rescue_candidates_topk,
            "odl_shadow_status": odl_shadow_status,
            "compare_applied": compare_applied,
            "target_books_used": target_books_used,
            "target_books_truncated": target_books_truncated,
            "unauthorized_target_book_ids": unauthorized_target_book_ids,
            "auto_resolved_target_book_ids": auto_resolved_target_book_ids,
            "compare_focus_query": compare_focus_query,
            "latency_budget_hit": latency_budget_hit,
            "evidence_policy": evidence_policy,
            "per_book_evidence_count": per_book_evidence_count,
            "compare_degrade_reason": compare_degrade_reason,
            "compare_mode": compare_mode,
            "level_counts": {"A": level_a_count, "B": level_b_count, "C": level_c_count},
            "selected_buckets": selected_buckets,
            "executed_strategies": executed_strategies,
            "vector_metadata": {
                "cached": vec_meta.get("cached"),
                "duration_ms": vec_meta.get("duration_ms"),
                "retrieval_steps": vec_meta.get("retrieval_steps", {}),
                "router_mode": router_mode,
                "router_reason": router_reason,
                "retrieval_mode": retrieval_mode,
                "selected_buckets": selected_buckets,
                "executed_strategies": executed_strategies,
                "odl_rescue_applied": odl_rescue_applied,
                "odl_rescue_reason": odl_rescue_reason,
                "odl_rescue_timed_out": odl_rescue_timed_out,
                "odl_rescue_latency_ms": odl_rescue_latency_ms,
                "odl_rescue_candidates_added": odl_rescue_candidates_added,
                "odl_rescue_candidates_topk": odl_rescue_candidates_topk,
                "odl_shadow_status": odl_shadow_status,
            },
        }
    }


def generate_answer(question: str, firebase_uid: str, context_book_id: str = None, chat_history: List[Dict] = None, session_summary: str = "", limit: Optional[int] = None, offset: int = 0, session_id: Optional[int | str] = None, resource_type: Optional[str] = None, scope_mode: str = "GLOBAL", apply_scope_policy: bool = False, compare_mode: Optional[str] = None, target_book_ids: Optional[List[str]] = None, visibility_scope: str = "default", content_type: Optional[str] = None, ingestion_type: Optional[str] = None) -> Tuple[Optional[str], Optional[List[Dict]], Dict]:
    """
    RAG generation pipeline with Memory Layer support.
    """
    if is_analytic_word_count(question):
        if not context_book_id:
            return (
                "Analitik sayÄ±m iÃ§in Ã¶nce bir kitap seÃ§melisin.",
                [],
                {
                    "status": "analytic",
                    "analytics": {
                        "type": "word_count",
                        "error": "book_id_required",
                    },
                },
            )
        term = extract_target_term(question)
        if not term:
            return (
                "SayÄ±lacak kelimeyi belirtir misin?",
                [],
                {
                    "status": "analytic",
                    "analytics": {
                        "type": "word_count",
                        "error": "term_missing",
                    },
                },
            )
        count = count_lemma_occurrences(firebase_uid, context_book_id, term)
        contexts = get_keyword_contexts(firebase_uid, context_book_id, term, limit=10) # Initial 10 for the short-circuit
        answer = f"\"{term}\" kelimesi bu kitapta toplam {count} kez geÃ§iyor."
        return (
            answer,
            [],
            {
                "status": "analytic",
                "analytics": {
                    "type": "word_count",
                    "term": term,
                    "count": count,
                    "match": "lemma",
                    "scope": "book_chunks",
                    "contexts": contexts
                },
            },
        )

    # 1. Retrieve Context
    retrieval_phase_start = time.perf_counter()
    ctx = get_rag_context(
        question,
        firebase_uid,
        context_book_id,
        chat_history=chat_history,
        limit=limit,
        offset=offset,
        session_id=session_id,
        resource_type=resource_type,
        scope_mode=scope_mode,
        apply_scope_policy=apply_scope_policy,
        compare_mode=compare_mode,
        target_book_ids=target_book_ids,
        visibility_scope=visibility_scope,
        content_type=content_type,
        ingestion_type=ingestion_type,
    )
    retrieval_phase_sec = time.perf_counter() - retrieval_phase_start
    try:
        L3_PHASE_LATENCY_SECONDS.labels(phase="retrieval").observe(retrieval_phase_sec)
    except Exception:
        pass
    if not ctx:
        return "ÃœzgÃ¼nÃ¼m, ÅŸu an cevap Ã¼retemiyorum. Ä°lgili iÃ§erik bulunamadÄ±.", [], {"status": "failed"}
        
    chunks = ctx['chunks']
    answer_mode = ctx['mode']
    avg_conf = ctx['confidence']
    keywords = ctx['keywords']
    quote_target_count = _compute_quote_target_count(avg_conf, len(chunks))
    context_budget_applied = bool(
        getattr(settings, "L3_PERF_CONTEXT_BUDGET_ENABLED", False) and answer_mode != "EXPLORER"
    )
    
    # 2. Build Context String
    prompt_build_phase_start = time.perf_counter()
    level_counts = ctx['level_counts']
    evidence_meta = f"[SÄ°STEM NOTU: KullanÄ±cÄ±nÄ±n kÃ¼tÃ¼phanesinde '{', '.join(keywords)}' ile ilgili toplam {level_counts['A'] + level_counts['B']} adet doÄŸrudan not bulundu.]"
    
    graph_bridge_used = False
    graph_bridge_attempted = False
    graph_bridge_timeout_triggered = False
    graph_bridge_latency_ms = 0.0
    graph_insight = ""

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_context = executor.submit(build_epistemic_context, chunks, answer_mode)
        future_graph_bridge = None
        graph_bridge_started_at = None

        if answer_mode == 'SYNTHESIS':
            graph_bridge_attempted = True
            graph_bridge_started_at = time.perf_counter()
            future_graph_bridge = executor.submit(get_graph_enriched_context, chunks, firebase_uid)

        context_str_base, used_chunks = future_context.result()
        context_str = evidence_meta + "\n\n" + context_str_base

        if future_graph_bridge is not None:
            timeout_sec = max(
                0.05,
                float(getattr(settings, "SEARCH_GRAPH_BRIDGE_TIMEOUT_MS", 650)) / 1000.0
            )
            try:
                graph_insight = future_graph_bridge.result(timeout=timeout_sec) or ""
                if graph_bridge_started_at is not None:
                    graph_bridge_latency_ms = (time.perf_counter() - graph_bridge_started_at) * 1000.0
                if graph_insight:
                    graph_bridge_used = True
                    context_str = graph_insight + "\n\n" + context_str
            except FutureTimeoutError:
                graph_bridge_timeout_triggered = True
                future_graph_bridge.cancel()
                if graph_bridge_started_at is not None:
                    graph_bridge_latency_ms = (time.perf_counter() - graph_bridge_started_at) * 1000.0
            except Exception as bridge_err:
                logger.warning("Graph bridge enrichment skipped: %s", bridge_err)
                if graph_bridge_started_at is not None:
                    graph_bridge_latency_ms = (time.perf_counter() - graph_bridge_started_at) * 1000.0
            
    # 3. Generate Answer (Ensure sources match IDs)
    sources = [{
        'id': i,
        'title': c.get('title', 'Unknown'), 
        'page_number': c.get('page_number', 0),
        'content': str(c.get('content_chunk', ''))[:400],
        'score': c.get('score', 0)
    } for i, c in enumerate(used_chunks, 1)]
    
    try:
        network_status = ctx.get('network_status', 'IN_NETWORK')
        
        # Prepare Memory-Augmented Prompt
        history_str = ""
        if chat_history:
            for msg in chat_history[-settings.CHAT_PROMPT_TURNS:]: # Just last N turns
                role = "KullanÄ±cÄ±" if msg['role'] == 'user' else "Asistan"
                history_str += f"{role}: {msg['content']}\n"
        
        # In Memory Layer, we explicitly label context zones (Structured Phase 3)
        structured_context = []
        if session_summary:
            structured_context.append(f"### KONUÅžMA Ã–ZETÄ° (LONG-TERM MEMORY)\n{session_summary}")
        
        if history_str:
            structured_context.append(f"### SON YAZIÅžMALAR (SHORT-TERM MEMORY)\n{history_str}")
        
        structured_context.append(f"### KAYNAK DOKÃœMANLAR (FOUND EVIDENCE)\n{context_str}")
        
        full_context_str = "\n\n---\n\n".join(structured_context)
            
        prompt = get_prompt_for_mode(
            answer_mode, 
            full_context_str, 
            question, 
            confidence_score=avg_conf, 
            network_status=network_status,
            quote_target_count=quote_target_count,
        )
        prompt_build_phase_sec = time.perf_counter() - prompt_build_phase_start
        try:
            L3_PHASE_LATENCY_SECONDS.labels(phase="prompt_build").observe(prompt_build_phase_sec)
        except Exception:
            pass
        
        # Heavy Layer-3 generation policy:
        # - Qwen primary for both Standard and Explorer (when pilot flag enabled)
        # - Gemini (FLASH tier, configured as flash-lite) secondary fallback
        route_mode = ROUTE_MODE_DEFAULT
        provider_hint = None
        allow_secondary_fallback = False
        allow_pro_fallback_effective = False
        model_name = get_model_for_tier(MODEL_TIER_FLASH)

        if settings.LLM_EXPLORER_QWEN_PILOT_ENABLED:
            route_mode = ROUTE_MODE_EXPLORER_QWEN_PILOT
            provider_hint = settings.LLM_EXPLORER_PRIMARY_PROVIDER
            model_name = settings.LLM_EXPLORER_PRIMARY_MODEL
            allow_secondary_fallback = True

        max_output_tokens = None
        llm_timeout_s = None
        llm_generation_timeout_applied = False
        if getattr(settings, "L3_PERF_OUTPUT_BUDGET_ENABLED", False) and answer_mode != "EXPLORER":
            max_output_tokens = int(getattr(settings, "L3_PERF_MAX_OUTPUT_TOKENS_STANDARD", 650) or 650)
            if max_output_tokens < 128:
                max_output_tokens = 650
            llm_timeout_s = 18.0
            llm_generation_timeout_applied = True
            try:
                L3_PERF_GUARD_APPLIED_TOTAL.labels(guard_name="output_budget_standard").inc()
            except Exception:
                pass

        fallback_state = {"pro_fallback_used": 0}
        llm_phase_start = time.perf_counter()
        result = generate_text(
            model=model_name,
            prompt=prompt,
            task="search_generate_answer",
            model_tier=MODEL_TIER_FLASH,
            max_output_tokens=max_output_tokens,
            timeout_s=llm_timeout_s,
            allow_pro_fallback=allow_pro_fallback_effective,
            fallback_state=fallback_state,
            provider_hint=provider_hint,
            route_mode=route_mode,
            allow_secondary_fallback=allow_secondary_fallback,
        )
        llm_phase_sec = time.perf_counter() - llm_phase_start
        try:
            L3_PHASE_LATENCY_SECONDS.labels(phase="llm_generate").observe(llm_phase_sec)
        except Exception:
            pass
        answer = result.text if result and result.text else "Cevap üretilemedi."

        # Recovery guard: if Standard mode answer is underfilled, regenerate once in richer mode.
        short_answer_recovery_applied = False
        normalized_answer = (answer or "").lower()
        heading_count = answer.count("## ")
        paragraph_count = len([p for p in re.split(r"\n\s*\n", answer) if p.strip()])
        looks_underfilled = (
            len(answer.strip()) < 520
            or paragraph_count < 2
            or (answer_mode in {"QUOTE", "HYBRID"} and heading_count < 2)
            or (
                "doğrudan tanımlar" in normalized_answer
                and "bağlamsal analiz" not in normalized_answer
                and "bağlamsal kanıtlar" not in normalized_answer
            )
        )

        if looks_underfilled and answer_mode != "EXPLORER":
            try:
                recovery_mode = "HYBRID" if answer_mode == "HYBRID" else "SYNTHESIS"
                recovery_prompt = get_prompt_for_mode(
                    recovery_mode,
                    full_context_str,
                    question,
                    confidence_score=max(float(avg_conf or 0.0), 4.0),
                    network_status=network_status,
                )
                recovery_prompt += (
                    "\n\nADDITIONAL REQUIREMENT:\n"
                    "- Do not answer in a single paragraph.\n"
                    "- Provide at least 3 substantial paragraphs.\n"
                    "- Explain reasoning with concrete links to the provided context.\n"
                )
                recovery_max_tokens = (
                    max(int(max_output_tokens or 0), 1600)
                    if getattr(settings, "L3_PERF_OUTPUT_BUDGET_ENABLED", False)
                    else 1600
                )
                recovery_timeout_s = 25.0 if llm_timeout_s else None

                recovery_result = generate_text(
                    model=model_name,
                    prompt=recovery_prompt,
                    task="search_generate_answer_recovery",
                    model_tier=MODEL_TIER_FLASH,
                    max_output_tokens=recovery_max_tokens,
                    timeout_s=recovery_timeout_s,
                    allow_pro_fallback=allow_pro_fallback_effective,
                    fallback_state=fallback_state,
                    provider_hint=provider_hint,
                    route_mode=route_mode,
                    allow_secondary_fallback=allow_secondary_fallback,
                )
                recovered = recovery_result.text if recovery_result and recovery_result.text else ""
                if recovered.strip() and (
                    len(recovered.strip()) >= 260
                    and len(recovered.strip()) > len(answer.strip()) + 40
                ):
                    answer = recovered
                    result = recovery_result
                    short_answer_recovery_applied = True
            except Exception as recovery_err:
                logger.warning("Short answer recovery skipped: %s", recovery_err)

        # Merge degradations from context
        meta = ctx.get('metadata', {}) or {}
        meta["model_name"] = result.model_used
        meta["model_tier"] = result.model_tier
        meta["provider_name"] = result.provider_name
        meta["model_fallback_applied"] = bool(result.fallback_applied)
        meta["secondary_fallback_applied"] = bool(result.secondary_fallback_applied)
        meta["fallback_reason"] = result.fallback_reason
        meta["llm_generation_timeout_applied"] = llm_generation_timeout_applied
        meta["context_budget_applied"] = context_budget_applied
        meta["quote_target_count"] = quote_target_count
        meta["short_answer_recovery_applied"] = short_answer_recovery_applied
        meta["supplementary_search_skipped_reason"] = ctx.get("supplementary_search_skipped_reason")
        meta["expansion_skipped_reason"] = ctx.get("expansion_skipped_reason")
        meta["source_diversity_count"] = ctx.get("source_diversity_count", 0)
        meta["source_type_diversity_count"] = ctx.get("source_type_diversity_count", 0)
        meta["graph_bridge_attempted"] = graph_bridge_attempted
        meta["graph_bridge_used"] = graph_bridge_used
        meta["graph_bridge_timeout_triggered"] = graph_bridge_timeout_triggered
        meta["graph_bridge_latency_ms"] = graph_bridge_latency_ms
        search_log_id = meta.get("search_log_id")
        if search_log_id:
            try:
                with DatabaseManager.get_write_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            """
                            UPDATE TOMEHUB_SEARCH_LOGS
                            SET MODEL_NAME = :p_model
                            WHERE ID = :p_id
                            """,
                            {"p_model": result.model_used, "p_id": search_log_id}
                        )
                    conn.commit()
            except Exception as e:
                logger.warning(f"Failed to update MODEL_NAME for search_log_id={search_log_id}: {e}")
        
        return answer, sources, meta
    except Exception as e:
        import traceback as _tb
        logger.error(
            "Generate Answer failed",
            extra={"error": str(e), "traceback": _tb.format_exc()},
            exc_info=True,
        )
        return "Bir hata oluÅŸtu.", sources, {"status": "error", "error": str(e)}


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TomeHub RAG Search Service - Interactive Test")
    print("=" * 70)
    
    # Init DB Pool for test
    from infrastructure.db_manager import DatabaseManager
    try:
        DatabaseManager.init_pool()
    except Exception as e:
        print(f"[ERROR] DB Init Failed: {e}")
        exit(1)
        
    # Get user ID
    firebase_uid = input("\nEnter Firebase UID: ").strip()
    if not firebase_uid:
        print("[ERROR] Firebase UID required.")
        exit(1)
    
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




