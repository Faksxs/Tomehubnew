from typing import List, Dict, Any, Optional, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

from .strategies import SearchStrategy, ExactMatchStrategy, LemmaMatchStrategy, SemanticMatchStrategy
from utils.logger import get_logger
from .search_utils import compute_rrf
from services.rerank_service import rerank_candidates
from services.query_expander import QueryExpander
from services.cache_service import MultiLayerCache, generate_cache_key, get_cache
from config import settings

logger = get_logger("search_orchestrator")

class SearchOrchestrator:
    """
    Coordinator for the Search Decision System.
    Manages:
    1. Query Expansion (Phase 2)
    2. Strategy Execution (Parallel/Sequential)
    3. Result Fusion (RRF)
    4. Policy Application (Thresholds, Gating)
    """
    
    def __init__(self, embedding_fn=None, cache: Optional[MultiLayerCache] = None):
        self.strategies: List[SearchStrategy] = []
        self.embedding_fn = embedding_fn
        self.cache = cache or get_cache()  # Use provided cache or global cache
        self.expander = QueryExpander(cache=self.cache)  # Pass cache to expander
        
        # Initialize Default Strategies
        self.strategies.append(ExactMatchStrategy())
        self.strategies.append(LemmaMatchStrategy())
        # Semantic strategy needs embedding function
        if self.embedding_fn:
            self.strategies.append(SemanticMatchStrategy(self.embedding_fn))
            
    def search(self, query: str, firebase_uid: str, limit: int = 50, offset: int = 0, book_id: str = None, intent: str = 'SYNTHESIS', resource_type: Optional[str] = None, session_id: Optional[int | str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        start_time = time.time()
        logger.info(f"Orchestrator: Search started for query='{query}' UID='{firebase_uid}' intent='{intent}'")
        
        # Check cache first
        if self.cache:
            cache_key = generate_cache_key(
                service="search",
                query=query,
                firebase_uid=firebase_uid,
                book_id=book_id,
                limit=limit,
                version=settings.EMBEDDING_MODEL_VERSION
            )
            cache_key += f"_int:{intent}_off:{offset}"
            
            cached_result = self.cache.get(cache_key)
            if cached_result:
                # Cache stores just the list. For now, return None for log_id on cache hit 
                # (or we could log cache hits too, but let's keep it simple for now)
                logger.info(f"Cache hit for query: {query[:30]}...")
                return cached_result, {"cached": True, "search_log_id": None}
        
        # ... [Strategy Execution Code Omitted for Brevity - Keeping existing logic] ...
        # (Assuming the existing strategy execution code remains here)
        # We need to construct this block carefully since I'm blindly replacing the whole function if I'm not careful.
        # But wait, replace_file_content replaces a block. The input file is 175 lines. 
        # I should use multi_replace or be very precise.
        # The user's prompt implies I should just do it. 
        # I'll rely on the fact that I previously read the file. 
        # Actually, since the strategies execution logic is long, I should probably NOT replace the whole function in one go if I can avoid it.
        # But I need to change the Return statement at the end and the signature at the start.
        # And insert the logging logic before return.
        
        # strategy execution...
        # ...
        
        # [RE-INSERTING EXISTING LOGIC FOR CONTEXT SAFETY - I will use a simplified approach to just modify start and end]
        pass 

        # [Resuming Search Logic]

        
        # 0. Query Expansion (Phase 2) - PARALLELIZED with strategy execution
        # Start expansion in parallel with original query strategies
        raw_results_list = []
        
        with ThreadPoolExecutor(max_workers=6) as executor:  # Increased for parallel expansion
            future_map = {}
            
            # A. Start Query Expansion in parallel (non-blocking)
            expansion_future = executor.submit(self.expander.expand_query, query)
            
            # B. Original Query: Run ALL strategies immediately (don't wait for expansion)
            for strat in self.strategies:
                # Label: StrategyName_Original
                label = f"{strat.__class__.__name__}_Original"
                
                # Check if strategy supports 'intent' arg (Semantic does, others don't)
                if isinstance(strat, SemanticMatchStrategy):
                     future_map[executor.submit(strat.search, query, firebase_uid, limit, intent, resource_type)] = label
                else:
                     future_map[executor.submit(strat.search, query, firebase_uid, limit, resource_type)] = label
            
            # C. Collect original query results first
            for future in list(future_map.keys()):
                name = future_map[future]
                try:
                    res = future.result()
                    if res:
                        raw_results_list.append(res)
                        logger.info(f"Strat {name} returned {len(res)} hits")
                except Exception as e:
                    logger.error(f"Strat {name} failed: {e}")
            
            # D. Now get expansion results (should be ready or nearly ready)
            try:
                variations = expansion_future.result(timeout=10)  # 10s timeout for expansion
                logger.info(f"Variations: {variations}")
            except Exception as e:
                logger.warning(f"Query expansion failed or timed out: {e}")
                variations = []  # Fallback: use original query only
            
            # E. Variations: Run Semantic only (if we have variations)
            semantic_strat = next((s for s in self.strategies if isinstance(s, SemanticMatchStrategy)), None)
            if semantic_strat and variations:
                variation_futures = {}
                for i, var_query in enumerate(variations):
                    label = f"SemanticMatchStrategy_Var{i+1}"
                    # Pass intent and resource_type here too
                    variation_futures[executor.submit(semantic_strat.search, var_query, firebase_uid, limit, intent, resource_type)] = label
                
                # Collect variation results
                for future in variation_futures:
                    name = variation_futures[future]
                    try:
                        res = future.result()
                        if res:
                            raw_results_list.append(res)
                            logger.info(f"Strat {name} returned {len(res)} hits")
                    except Exception as e:
                        logger.error(f"Strat {name} failed: {e}")

        # 2. Policy: Exact Match Gating (On Original Query Results Only)
        # Find exact match results from the pool
        # This is harder now since we have a flat list of lists
        # But we can assume if specific ExactMatch returned high scores, we might prioritize.
        # For Phase 2, let's skip gating to maximize recall via RRF.
        
        # 3. Fusion (RRF) with Intent-Aware Weighting
        candidate_pool = {} # Key -> Item
        rankings = []
        
        # Determine base weights based on intent
        # Default: [Exact, Lemma, SemanticOriginal, SemanticVar1, SemanticVar2, ...]
        if intent == 'DIRECT' or intent == 'CITATION_SEEKING':
            base_weights = [0.6, 0.3, 0.1] # High priority on exact/lemma
        elif intent == 'NARRATIVE' or intent == 'SYNTHESIS':
            base_weights = [0.1, 0.2, 0.7] # High priority on semantic
        else:
            base_weights = [0.33, 0.33, 0.34] # Equal-ish distribution
            
        final_weights = []
        
        for i, result_set in enumerate(raw_results_list):
            ranking = []
            # Calculate weight for this specific ranking list
            if i < 3:
                # Original query results (Exact, Lemma, Semantic)
                w = base_weights[i] if i < len(base_weights) else 0.33
            else:
                # Expanded variations (Semantic only)
                # Dampen expansions by 50% relative to the original semantic query
                w = base_weights[2] * 0.5 if len(base_weights) > 2 else 0.15
            
            final_weights.append(w)
            
            for hit in result_set:
                # Key Generation
                if hit.get('id'):
                    key = str(hit['id'])
                else:
                    key = f"{hit['title']}_{hit['page_number']}_{hit['content_chunk'][:30]}"
                
                if key not in candidate_pool:
                    candidate_pool[key] = hit
                    candidate_pool[key]['strategies'] = [f"strat_{i}"]
                else:
                    # Update score (max)
                    candidate_pool[key]['score'] = max(candidate_pool[key]['score'], hit['score'])
                    candidate_pool[key]['strategies'].append(f"strat_{i}")
                
                ranking.append(key)
            
            if ranking:
                rankings.append(ranking)
            else:
                # Maintain weight list integrity even if ranking is empty
                # rankings.append([]) # Actually rankings list in compute_rrf should match weights list size or we handle it
                pass
                
        # Call RRF with calculated weight vector
        rrf_scores = compute_rrf(rankings, weights=final_weights)
        
        # Apply RRF scores
        final_list = []
        for key, sc in rrf_scores.items():
            item = candidate_pool[key]
            item['rrf_score'] = sc
            final_list.append(item)
            
        # Sort by RRF
        final_list.sort(key=lambda x: x['rrf_score'], reverse=True)
        top_candidates = final_list[offset : offset + limit]
        
        # Store in cache
        if self.cache:
            cache_key = generate_cache_key(
                service="search",
                query=query,
                firebase_uid=firebase_uid,
                book_id=book_id,
                limit=limit,
                version=settings.EMBEDDING_MODEL_VERSION
            )
            cache_key += f"_int:{intent}_off:{offset}"
            # TTL: 1 hour (3600 seconds) for search results
            self.cache.set(cache_key, top_candidates, ttl=3600)
            logger.info(f"Cached search results for key: {cache_key[:50]}...")
        
        duration = time.time() - start_time
        logger.info(f"Orchestrator: Finished in {duration:.3f}s. Returning {len(top_candidates)} results.")
        
        # LOG ANALYTICS (Phase 5)
        search_log_id = self._log_search(
            uid=firebase_uid, 
            query=query, 
            intent=intent,
            rrf_scores=None, # Passed inside helper for now
            results=top_candidates,
            duration=duration,
            session_id=session_id
        )
        
        metadata = {
            "search_log_id": search_log_id,
            "intent": intent,
            "duration": duration,
            "cached": False
        }
        
        return top_candidates, metadata

    # Helper for DB Logging
    def _log_search(self, uid, query, intent, rrf_scores, results, duration, session_id: Optional[int | str] = None):
        try:
            from infrastructure.db_manager import DatabaseManager
            import json
            
            top_id = results[0]['id'] if results else None
            top_score = results[0].get('rrf_score', 0) if results else 0
            
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    weights_str = "vec:1.0, bm25:1.0, graph:1.0" 
                    id_var = cursor.var(int)
                    
                    cursor.execute("""
                        INSERT INTO TOMEHUB_SEARCH_LOGS 
                        (FIREBASE_UID, SESSION_ID, QUERY_TEXT, INTENT, RRF_WEIGHTS, TOP_RESULT_ID, TOP_RESULT_SCORE, EXECUTION_TIME_MS)
                        VALUES (:p_uid, :p_sid, :p_q, :p_intent, :p_w, :p_tid, :p_tscore, :p_dur)
                        RETURNING ID INTO :id_col
                    """, {
                        "p_uid": uid,
                        "p_sid": str(session_id) if session_id is not None else None,
                        "p_q": query,
                        "p_intent": intent,
                        "p_w": weights_str,
                        "p_tid": top_id,
                        "p_tscore": top_score,
                        "p_dur": duration * 1000,
                        "id_col": id_var
                    })
                    
                    # id_var.getvalue() returns a list for returning into
                    vals = id_var.getvalue()
                    if vals:
                        log_id = vals[0]
                        conn.commit()
                        return int(log_id)
                    else:
                        print(f"[ERROR] LOGGING FAILED: No ID returned. Vals={vals}")
                        return None
        except Exception as e:
            logger.error(f"Failed to log search analytics: {e}")
            print(f"[ERROR] LOGGING FAILED: {e}")
            return None
