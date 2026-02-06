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
        print(f"\n[ORCHESTRATOR] SEARCH: '{query}' | UID: {firebase_uid} | Intent: {intent}")
        
        # Determine internal POOL_SIZE based on intent
        # We fetch a large pool to ensure good fusion, even on later pages
        internal_pool_limit = 1000 if intent in ['DIRECT', 'CITATION_SEEKING'] else 500
        
        cache_key = None
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
            
            cached_payload = self.cache.get(cache_key)
            if cached_payload:
                # Cache stores just the list. For now, return None for log_id on cache hit 
                # (or we could log cache hits too, but let's keep it simple for now)
                logger.info(f"Cache hit for query: {query[:30]}...")
                print(f"[ORCHESTRATOR] Cache HIT")
                if isinstance(cached_payload, dict) and "results" in cached_payload:
                    cached_results = cached_payload.get("results") or []
                    total_count = cached_payload.get("total_count", len(cached_results))
                else:
                    cached_results = cached_payload
                    total_count = len(cached_results)
                return cached_results, {"cached": True, "search_log_id": None, "total_count": total_count}
        
        # 0. Query Expansion (Phase 2) - PARALLELIZED with strategy execution
        # Start expansion in parallel with original query strategies
        # 0. Query Expansion (Phase 2) - PARALLELIZED
        
        # Buckets for strict ordering
        bucket_exact = []
        bucket_lemma = []
        bucket_semantic = []
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            future_map = {}
            
            # A. Start Expansion
            expansion_future = executor.submit(self.expander.expand_query, query)
            
            # B. Run Strategies
            for strat in self.strategies:
                s_name = strat.__class__.__name__
                # Label allows us to bucket them later
                label = s_name 
                
                if isinstance(strat, SemanticMatchStrategy):
                     future_map[executor.submit(strat.search, query, firebase_uid, 20, 0, intent, resource_type)] = label
                else:
                     future_map[executor.submit(strat.search, query, firebase_uid, internal_pool_limit, 0, resource_type)] = label
            
            # C. Collect Results & Bucket
            for future in list(future_map.keys()):
                label = future_map[future]
                try:
                    res = future.result()
                    if res:
                        if "ExactMatchStrategy" in label:
                            bucket_exact.extend(res)
                        elif "LemmaMatchStrategy" in label:
                            bucket_lemma.extend(res)
                        elif "SemanticMatchStrategy" in label:
                            bucket_semantic.extend(res)
                        
                        logger.info(f"Strat {label} returned {len(res)} hits")
                except Exception as e:
                    logger.error(f"Strat {label} failed: {e}")

            # D. Expansion Results
            try:
                variations = expansion_future.result(timeout=10)
            except Exception:
                variations = []

            # E. Run Semantic for Variations
            semantic_strat = next((s for s in self.strategies if isinstance(s, SemanticMatchStrategy)), None)
            if semantic_strat and variations:
                variation_futures = {}
                for i, var_query in enumerate(variations):
                    label = "SemanticMatchStrategy_Var"
                    variation_futures[executor.submit(semantic_strat.search, var_query, firebase_uid, 20, 0, intent, resource_type)] = label
                
                for future in variation_futures:
                    try:
                        res = future.result()
                        if res:
                            bucket_semantic.extend(res)
                    except Exception:
                        pass
        
        # ---------------------------------------------------------
        # 3. STRICT CONCATENATION & DEDUPLICATION (No RRF)
        # Priority: EXACT > LEMMA > SEMANTIC
        # Sub-Priority: HIGHLIGHT > INSIGHT > NOTES > Others
        # ---------------------------------------------------------
        
        final_list = []
        seen_ids = set()
        
        # Priority Helper
        def get_priority(item):
            st = item.get('source_type', '')
            if st == 'HIGHLIGHT': return 1
            if st == 'INSIGHT': return 2
            if st == 'NOTES': return 3
            if item.get('comment') or item.get('personal_comment'): return 2.5 # Boost comments
            return 4

        # Sort Buckets Internally
        bucket_exact.sort(key=get_priority)
        bucket_lemma.sort(key=get_priority)
        # Semantic is sorted by distance, do not re-sort by type to preserve relevance
        
        def add_batch(batch, match_label):
            count = 0
            for item in batch:
                # Deduplicate by ID
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    # Tag metadata for UI
                    if 'match_type' not in item:
                        item['match_type'] = match_label
                    final_list.append(item)
                    count += 1
            return count

        # 1. Exact Matches (Highest Priority)
        # Already sorted by source_type in strategy (HIGHLIGHT > INSIGHT > NOTES)
        add_batch(bucket_exact, 'content_exact')
        
        # 2. Lemma Matches
        add_batch(bucket_lemma, 'content_fuzzy')
        
        # 3. Semantic Matches (Lowest Priority)
        add_batch(bucket_semantic, 'semantic')

        # Pagination Slicing
        total_found = len(final_list)
        top_candidates = final_list[offset : offset + limit]

        duration = time.time() - start_time

        # Log search (best-effort)
        search_log_id = None
        try:
            search_log_id = self._log_search(
                firebase_uid,
                query,
                intent,
                None,
                top_candidates,
                duration,
                session_id=session_id
            )
        except Exception as e:
            logger.error(f"Search log failed: {e}")

        # Cache results (best-effort)
        if self.cache and cache_key:
            try:
                self.cache.set(
                    cache_key,
                    {"results": top_candidates, "total_count": total_found},
                    ttl=settings.CACHE_L1_TTL
                )
            except Exception as e:
                logger.error(f"Search cache set failed: {e}")

        metadata = {
            "total_count": total_found,
            "cached": False,
            "search_log_id": search_log_id,
            "duration_ms": int(duration * 1000)
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
                    
                    # Coerce session_id to int if possible to avoid ORA-01722 when UUID-like strings are passed
                    sid_int = None
                    try:
                        sid_int = int(session_id) if session_id is not None and str(session_id).strip().isdigit() else None
                    except Exception:
                        sid_int = None
                    
                    cursor.execute("""
                        INSERT INTO TOMEHUB_SEARCH_LOGS 
                        (FIREBASE_UID, SESSION_ID, QUERY_TEXT, INTENT, RRF_WEIGHTS, TOP_RESULT_ID, TOP_RESULT_SCORE, EXECUTION_TIME_MS)
                        VALUES (:p_uid, :p_sid, :p_q, :p_intent, :p_w, :p_tid, :p_tscore, :p_dur)
                        RETURNING ID INTO :id_col
                    """, {
                        "p_uid": uid,
                        "p_sid": sid_int,
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
