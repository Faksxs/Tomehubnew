from typing import List, Dict, Any, Optional
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
            
    def search(self, query: str, firebase_uid: str, limit: int = 50, book_id: str = None) -> List[Dict[str, Any]]:
        start_time = time.time()
        logger.info(f"Orchestrator: Search started for '{query}'")
        
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
            cached_result = self.cache.get(cache_key)
            if cached_result:
                logger.info(f"Cache hit for query: {query[:30]}...")
                return cached_result
        
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
                future_map[executor.submit(strat.search, query, firebase_uid, limit)] = label
            
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
                    variation_futures[executor.submit(semantic_strat.search, var_query, firebase_uid, limit)] = label
                
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
        
        # 3. Fusion (RRF)
        # Flatten and RRF
        
        candidate_pool = {} # Key -> Item
        rankings = []
        
        for result_set in raw_results_list:
            ranking = []
            for hit in result_set:
                # Key Generation
                if hit.get('id'):
                    key = str(hit['id'])
                else:
                    key = f"{hit['title']}_{hit['page_number']}_{hit['content_chunk'][:30]}"
                
                if key not in candidate_pool:
                    candidate_pool[key] = hit
                    candidate_pool[key]['strategies'] = ['aggregated'] 
                else:
                    # Update score (max)
                    candidate_pool[key]['score'] = max(candidate_pool[key]['score'], hit['score'])
                
                ranking.append(key)
            
            if ranking:
                rankings.append(ranking)
            
        rrf_scores = compute_rrf(rankings)
        
        # Apply RRF scores
        final_list = []
        for key, sc in rrf_scores.items():
            item = candidate_pool[key]
            item['rrf_score'] = sc
            final_list.append(item)
            
        # Sort by RRF
        final_list.sort(key=lambda x: x['rrf_score'], reverse=True)
        top_candidates = final_list[:limit]
        
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
            # TTL: 1 hour (3600 seconds) for search results
            self.cache.set(cache_key, top_candidates, ttl=3600)
            logger.info(f"Cached search results for key: {cache_key[:50]}...")
        
        duration = time.time() - start_time
        logger.info(f"Orchestrator: Finished in {duration:.3f}s. Returning {len(top_candidates)} results.")
        
        return top_candidates
