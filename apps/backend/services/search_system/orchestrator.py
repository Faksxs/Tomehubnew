from typing import List, Dict, Any, Optional, Tuple
import time
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from .strategies import (
    SearchStrategy,
    ExactMatchStrategy,
    LemmaMatchStrategy,
    SemanticMatchStrategy,
    _filter_query_lemmas,
)
from utils.logger import get_logger
from .search_utils import compute_rrf
from services.rerank_service import rerank_candidates
from services.monitoring import SEARCH_FUSION_MODE_TOTAL, L3_PERF_GUARD_APPLIED_TOTAL
from services.query_expander import QueryExpander
from services.cache_service import MultiLayerCache, generate_cache_key, get_cache
from .semantic_router import SemanticRouter, to_strategy_labels
from utils.spell_checker import get_spell_checker
from utils.text_utils import get_lemmas, deaccent_text
from config import settings

logger = get_logger("search_orchestrator")
SEMANTIC_MIX_POLICY_VERSION = "v4"
_LAST_SEARCH_LOG_CLEANUP_TS = 0.0

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
        self.router = SemanticRouter()
        
        # Initialize Default Strategies
        self.strategies.append(ExactMatchStrategy())
        self.strategies.append(LemmaMatchStrategy())
        # Semantic strategy needs embedding function
        if self.embedding_fn:
            self.strategies.append(SemanticMatchStrategy(self.embedding_fn))
    
    @staticmethod
    def _item_key(item: Dict[str, Any]) -> str:
        item_id = item.get("id")
        if item_id is not None:
            return str(item_id)
        return f"{item.get('title', '')}_{item.get('page_number', 0)}_{str(item.get('content_chunk', ''))[:40]}"
    
    @staticmethod
    def _intent_weights(intent: str) -> Dict[str, float]:
        if intent in {"DIRECT", "CITATION_SEEKING", "FOLLOW_UP"}:
            return {"exact": 0.55, "lemma": 0.30, "semantic": 0.15}
        if intent in {"SYNTHESIS", "NARRATIVE", "SOCIETAL", "COMPARATIVE"}:
            return {"exact": 0.20, "lemma": 0.20, "semantic": 0.60}
        return {"exact": 0.34, "lemma": 0.33, "semantic": 0.33}

    @staticmethod
    def _token_count(query: str) -> int:
        return len([tok for tok in (query or "").strip().split() if tok.strip()])

    @staticmethod
    def _dynamic_single_token_semantic_cap(lexical_total: int) -> int:
        if lexical_total > 30:
            return 2
        if lexical_total >= 20:
            return 3
        if lexical_total >= 10:
            return 4
        return 5
            
    def search(
        self,
        query: str,
        firebase_uid: str,
        limit: int = 50,
        offset: int = 0,
        book_id: str = None,
        intent: str = 'SYNTHESIS',
        resource_type: Optional[str] = None,
        session_id: Optional[int | str] = None,
        result_mix_policy: Optional[str] = None,
        semantic_tail_cap: Optional[int] = None,
        visibility_scope: str = "default",
        content_type: Optional[str] = None,
        ingestion_type: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        start_time = time.time()
        query_original = query or ""
        query_corrected = query_original
        query_correction_applied = False
        typo_rescue_applied = False
        lemma_seed_fallback_applied = False
        semantic_tail_policy = "default"
        typo_rescue_added_exact = 0
        typo_rescue_added_lemma = 0
        lemma_seed_added = 0
        expansion_skipped_reason = None
        logger.info(f"Orchestrator: Search started for query='{query}' UID='{firebase_uid}' intent='{intent}'")
        print(f"\n[ORCHESTRATOR] SEARCH: '{query}' | UID: {firebase_uid} | Intent: {intent}")
        
        # Determine internal POOL_SIZE based on intent
        # We fetch a large pool to ensure good fusion, even on later pages
        internal_pool_limit = 700 if intent in ['DIRECT', 'CITATION_SEEKING'] else 320
        default_semantic_tail_cap = int(getattr(settings, "SEARCH_SMART_SEMANTIC_TAIL_CAP", 6) or 6)
        semantic_tail_cap_value_for_fetch = (
            semantic_tail_cap
            if isinstance(semantic_tail_cap, int) and semantic_tail_cap > 0
            else default_semantic_tail_cap
        )
        semantic_fetch_limit = 20
        if result_mix_policy == "lexical_then_semantic_tail":
            # Keep semantic pool compact for lower latency while preserving tail quality.
            semantic_fetch_limit = max(24, min(72, semantic_tail_cap_value_for_fetch * 6))
        
        cache_key = None
        router_reason = "static_all"
        selected_buckets = ["exact", "lemma", "semantic"]
        executed_strategies: List[str] = []
        retrieval_mode = "balanced"
        noise_guard_applied = bool(getattr(settings, "SEARCH_NOISE_GUARD_ENABLED", True))
        latency_budget_applied = False
        graph_timeout_triggered = False

        if getattr(settings, "SEARCH_MODE_ROUTING_ENABLED", True):
            if settings.SEARCH_ROUTER_MODE == "rule_based":
                decision = self.router.route(
                    query=query,
                    intent=intent,
                    default_mode=settings.SEARCH_DEFAULT_MODE,
                )
                selected_buckets = decision.selected_buckets
                router_reason = decision.reason
                retrieval_mode = decision.retrieval_mode
            else:
                retrieval_mode = settings.SEARCH_DEFAULT_MODE
                selected_buckets = self.router.buckets_for_mode(retrieval_mode)
                router_reason = f"static_mode:{retrieval_mode}"
        else:
            # Hard rollback switch: keep legacy behavior with all buckets active.
            retrieval_mode = "balanced"
            selected_buckets = ["exact", "lemma", "semantic"]
            router_reason = "mode_routing_disabled"
        route_flags = to_strategy_labels(selected_buckets)

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
            cache_key += f"_int:{intent}_off:{offset}_router:{settings.SEARCH_ROUTER_MODE}"
            cache_key += f"_mix:{result_mix_policy or 'none'}_semcap:{semantic_tail_cap if semantic_tail_cap is not None else 'none'}"
            cache_key += f"_mixver:{SEMANTIC_MIX_POLICY_VERSION}"
            cache_key += f"_rmode:{retrieval_mode}_noise:{int(noise_guard_applied)}_modegate:{int(getattr(settings, 'SEARCH_MODE_ROUTING_ENABLED', True))}"
            cache_key += f"_typo:{int(getattr(settings, 'SEARCH_TYPO_RESCUE_ENABLED', True))}"
            cache_key += f"_lemseed:{int(getattr(settings, 'SEARCH_LEMMA_SEED_FALLBACK_ENABLED', True))}"
            cache_key += f"_dyntail:{int(getattr(settings, 'SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED', True))}"
            cache_key += f"_vis:{(visibility_scope or 'default')}"
            cache_key += f"_ct:{(content_type or 'none')}"
            cache_key += f"_it:{(ingestion_type or 'none')}"
            
            cached_payload = self.cache.get(cache_key)
            if cached_payload:
                # Cache stores just the list. For now, return None for log_id on cache hit 
                # (or we could log cache hits too, but let's keep it simple for now)
                logger.info(f"Cache hit for query: {query[:30]}...")
                print(f"[ORCHESTRATOR] Cache HIT")
                if isinstance(cached_payload, dict) and "results" in cached_payload:
                    cached_results = cached_payload.get("results") or []
                    total_count = cached_payload.get("total_count", len(cached_results))
                    cached_meta = cached_payload.get("metadata") or {}
                else:
                    cached_results = cached_payload
                    total_count = len(cached_results)
                    cached_meta = {}
                meta = {
                    "cached": True,
                    "CACHE_HIT": True,
                    "CACHE_LAYER": "L1_OR_L2",
                    "search_log_id": None,
                    "total_count": total_count,
                    "retrieval_fusion_mode": settings.RETRIEVAL_FUSION_MODE,
                    "retrieval_path": "hybrid",
                    "router_mode": settings.SEARCH_ROUTER_MODE,
                    "retrieval_mode": retrieval_mode,
                    "latency_budget_applied": latency_budget_applied,
                    "graph_timeout_triggered": graph_timeout_triggered,
                    "noise_guard_applied": noise_guard_applied,
                }
                meta.update(cached_meta)
                return cached_results, meta
        
        # 0. Query Expansion (Phase 2) - PARALLELIZED with strategy execution
        # Start expansion in parallel with original query strategies
        # 0. Query Expansion (Phase 2) - PARALLELIZED
        
        # Buckets for strict ordering
        bucket_exact = []
        bucket_lemma = []
        bucket_semantic = []
        semantic_variation_hits = 0
        variation_count = 0
        exact_strat = next((s for s in self.strategies if isinstance(s, ExactMatchStrategy)), None)
        lemma_strat = next((s for s in self.strategies if isinstance(s, LemmaMatchStrategy)), None)
        semantic_strat = next((s for s in self.strategies if isinstance(s, SemanticMatchStrategy)), None)
        strategy_timing_ms: Dict[str, int] = {}
        
        executor = ThreadPoolExecutor(max_workers=6)
        try:
            future_map = {}
            future_started_at: Dict[Any, float] = {}
            
            # A. Start Expansion
            expansion_variation_limit = int(
                getattr(settings, "SEARCH_SEMANTIC_EXPANSION_MAX_VARIATIONS", 2) or 0
            )
            expansion_variation_limit = max(0, min(3, expansion_variation_limit))
            expansion_future = (
                executor.submit(self.expander.expand_query, query, expansion_variation_limit)
                if expansion_variation_limit > 0
                else None
            )
            if expansion_future is None:
                expansion_skipped_reason = "expansion_disabled"
            
            # B. Run Strategies
            for strat in self.strategies:
                s_name = strat.__class__.__name__
                # Label allows us to bucket them later
                label = s_name

                if isinstance(strat, ExactMatchStrategy) and not route_flags["run_exact"]:
                    continue
                if isinstance(strat, LemmaMatchStrategy) and not route_flags["run_lemma"]:
                    continue
                if isinstance(strat, SemanticMatchStrategy) and not route_flags["run_semantic"]:
                    continue

                executed_strategies.append(label)
                if isinstance(strat, SemanticMatchStrategy):
                    fut = executor.submit(
                        strat.search,
                        query,
                        firebase_uid,
                        semantic_fetch_limit,
                        0,
                        intent=intent,
                        resource_type=resource_type,
                        book_id=book_id,
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                    )
                    future_map[fut] = strat
                    future_started_at[fut] = time.perf_counter()
                else:
                    fut = executor.submit(
                        strat.search,
                        query,
                        firebase_uid,
                        internal_pool_limit,
                        0,
                        resource_type=resource_type,
                        book_id=book_id,
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                    )
                    future_map[fut] = strat
                    future_started_at[fut] = time.perf_counter()
            
            # C. Collect Results & Bucket
            for future in list(future_map.keys()):
                strat = future_map[future]
                label = strat.__class__.__name__
                try:
                    res = future.result()
                    started = future_started_at.get(future)
                    if started is not None:
                        strategy_timing_ms[label] = int((time.perf_counter() - started) * 1000)
                    if res:
                        if isinstance(strat, ExactMatchStrategy):
                            bucket_exact.extend(res)
                        elif isinstance(strat, LemmaMatchStrategy):
                            bucket_lemma.extend(res)
                        elif isinstance(strat, SemanticMatchStrategy):
                            bucket_semantic.extend(res)
                        
                        logger.info(f"Strat {label} returned {len(res)} hits")
                except Exception as e:
                    logger.error(f"Strat {label} failed: {e}")

            # D. Expansion Results
            if expansion_future:
                try:
                    expansion_timeout_s = 6.0
                    if getattr(settings, "L3_PERF_EXPANSION_TAIL_FIX_ENABLED", False):
                        expansion_timeout_s = 2.0
                    variations = expansion_future.result(timeout=expansion_timeout_s)
                except FutureTimeoutError:
                    variations = []
                    expansion_future.cancel()
                    expansion_skipped_reason = "expansion_timeout"
                    if getattr(settings, "L3_PERF_EXPANSION_TAIL_FIX_ENABLED", False):
                        try:
                            L3_PERF_GUARD_APPLIED_TOTAL.labels(guard_name="expansion_tail_timeout").inc()
                        except Exception:
                            pass
                except Exception:
                    variations = []
                    expansion_skipped_reason = "expansion_error"
            else:
                variations = []

            # E. Run Semantic for Variations
            if semantic_strat and route_flags["run_semantic"] and variations:
                variation_count = len(variations)
                variation_futures = {}
                variation_fetch_limit = max(12, semantic_fetch_limit // 2)
                for i, var_query in enumerate(variations):
                    label = "SemanticMatchStrategy_Var"
                    fut = executor.submit(
                        semantic_strat.search,
                        var_query,
                        firebase_uid,
                        variation_fetch_limit,
                        0,
                        intent=intent,
                        resource_type=resource_type,
                        book_id=book_id,
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                    )
                    variation_futures[fut] = label
                    future_started_at[fut] = time.perf_counter()
                
                for future in variation_futures:
                    try:
                        res = future.result()
                        started = future_started_at.get(future)
                        if started is not None:
                            strategy_timing_ms["SemanticMatchStrategy_Var"] = strategy_timing_ms.get(
                                "SemanticMatchStrategy_Var", 0
                            ) + int((time.perf_counter() - started) * 1000)
                        if res:
                            bucket_semantic.extend(res)
                            semantic_variation_hits += len(res)
                    except Exception:
                        pass
        finally:
            if getattr(settings, "L3_PERF_EXPANSION_TAIL_FIX_ENABLED", False):
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

        initial_exact_raw_count = len(bucket_exact)
        initial_lemma_raw_count = len(bucket_lemma)
        initial_lexical_raw_count = initial_exact_raw_count + initial_lemma_raw_count

        # Typo rescue for low-lexical cases: re-run lexical strategies once with corrected query.
        if (
            getattr(settings, "SEARCH_TYPO_RESCUE_ENABLED", True)
            and initial_lexical_raw_count <= 2
            and (route_flags["run_exact"] or route_flags["run_lemma"])
        ):
            try:
                corrected = (get_spell_checker().correct(query_original) or "").strip()
            except Exception:
                corrected = query_original

            if corrected and corrected != query_original:
                query_corrected = corrected
                query_correction_applied = True
                typo_rescue_applied = True
                rescue_limit = min(internal_pool_limit, 160)

                if exact_strat and route_flags["run_exact"]:
                    rescue_exact = exact_strat.search(
                        query_corrected,
                        firebase_uid,
                        rescue_limit,
                        0,
                        resource_type=resource_type,
                        book_id=book_id,
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                    )
                    if rescue_exact:
                        bucket_exact.extend(rescue_exact)
                        typo_rescue_added_exact = len(rescue_exact)

                if lemma_strat and route_flags["run_lemma"]:
                    rescue_lemma = lemma_strat.search(
                        query_corrected,
                        firebase_uid,
                        rescue_limit,
                        0,
                        resource_type=resource_type,
                        book_id=book_id,
                        visibility_scope=visibility_scope,
                        content_type=content_type,
                        ingestion_type=ingestion_type,
                    )
                    if rescue_lemma:
                        bucket_lemma.extend(rescue_lemma)
                        typo_rescue_added_lemma = len(rescue_lemma)

        # Lemma-seed fallback: if no lemma hits at all, run exact search for top 1-2 lemmas.
        if (
            getattr(settings, "SEARCH_LEMMA_SEED_FALLBACK_ENABLED", True)
            and route_flags["run_exact"]
            and exact_strat
            and len(bucket_lemma) == 0
        ):
            lemma_source_query = query_corrected if query_correction_applied else query_original
            raw_lemmas = _filter_query_lemmas(get_lemmas(lemma_source_query))
            seed_lemmas: List[str] = []
            seen_norm = set()
            for lemma in raw_lemmas:
                norm = deaccent_text((lemma or "").strip()).lower()
                if len(norm) < 3:
                    continue
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                seed_lemmas.append((lemma or "").strip())
                if len(seed_lemmas) >= 2:
                    break

            if seed_lemmas:
                lemma_seed_fallback_applied = True
                seed_limit = max(40, min(120, limit * 4))
                for seed in seed_lemmas:
                    try:
                        seed_hits = exact_strat.search(
                            seed,
                            firebase_uid,
                            seed_limit,
                            0,
                            resource_type=resource_type,
                            book_id=book_id,
                            visibility_scope=visibility_scope,
                            content_type=content_type,
                            ingestion_type=ingestion_type,
                        )
                        for item in seed_hits:
                            patched = dict(item)
                            patched["match_type"] = "exact_lemma_seed"
                            bucket_exact.append(patched)
                        lemma_seed_added += len(seed_hits)
                    except Exception as e:
                        logger.error(f"Lemma-seed fallback failed for '{seed}': {e}")

        # Safety-net: if lexical-only routing produced no hits, run one semantic pass.
        # This prevents false "no content" failures for conceptual questions misrouted as DIRECT.
        if not bucket_exact and not bucket_lemma and not bucket_semantic and semantic_strat and not route_flags["run_semantic"]:
            logger.warning(
                "Router produced zero lexical hits; enabling semantic safety fallback",
                extra={"query": query, "intent": intent, "router_reason": router_reason}
            )
            try:
                semantic_fallback_limit = max(20, min(100, internal_pool_limit))
                fallback_semantic = semantic_strat.search(
                    query,
                    firebase_uid,
                    semantic_fallback_limit,
                    0,
                    intent=intent,
                    resource_type=resource_type,
                    book_id=book_id,
                    visibility_scope=visibility_scope,
                    content_type=content_type,
                    ingestion_type=ingestion_type,
                )
                if fallback_semantic:
                    bucket_semantic.extend(fallback_semantic)
                    executed_strategies.append("SemanticMatchStrategy_SafetyFallback")
                    if "semantic" not in selected_buckets:
                        selected_buckets.append("semantic")
                    router_reason = f"{router_reason}+semantic_fallback_no_lexical_hits"
            except Exception as e:
                logger.error(f"Semantic safety fallback failed: {e}")

        bucket_raw_counts = {
            "initial_exact_raw_count": initial_exact_raw_count,
            "initial_lemma_raw_count": initial_lemma_raw_count,
            "initial_lexical_raw_count": initial_lexical_raw_count,
            "exact_raw_count": len(bucket_exact),
            "lemma_raw_count": len(bucket_lemma),
            "semantic_raw_count": len(bucket_semantic),
            "semantic_variation_query_count": variation_count,
            "semantic_variation_hit_count": semantic_variation_hits,
            "typo_rescue_added_exact": typo_rescue_added_exact,
            "typo_rescue_added_lemma": typo_rescue_added_lemma,
            "lemma_seed_added_exact": lemma_seed_added,
        }

        # Priority Helper
        def get_priority(item):
            st = item.get('source_type', '')
            if st == 'HIGHLIGHT': return 1
            if st == 'INSIGHT': return 2
            if st == 'NOTES': return 3
            if item.get('comment') or item.get('personal_comment'): return 2.5
            return 4

        def get_bucket_sort_key(item):
            try:
                score = float(item.get("score", 0.0) or 0.0)
            except Exception:
                score = 0.0
            return (get_priority(item), -score)

        fusion_mode = settings.RETRIEVAL_FUSION_MODE
        try:
            SEARCH_FUSION_MODE_TOTAL.labels(fusion_mode=fusion_mode).inc()
        except Exception:
            pass

        if fusion_mode == "rrf":
            bucket_defs = [
                ("exact", bucket_exact, 0, "content_exact"),
                ("lemma", bucket_lemma, 1, "content_fuzzy"),
                ("semantic", bucket_semantic, 2, "semantic"),
            ]
            candidate_pool: Dict[str, Dict[str, Any]] = {}
            rankings: List[List[str]] = []
            weights: List[float] = []
            weights_by_intent = self._intent_weights(intent)

            for bucket_name, bucket, bucket_priority, fallback_match in bucket_defs:
                ranking: List[str] = []
                for item in bucket:
                    key = self._item_key(item)
                    ranking.append(key)
                    if key not in candidate_pool:
                        copied = dict(item)
                        copied["_bucket_priority"] = bucket_priority
                        if "match_type" not in copied:
                            copied["match_type"] = fallback_match
                        candidate_pool[key] = copied
                    else:
                        current = candidate_pool[key]
                        if float(item.get("score", 0.0)) > float(current.get("score", 0.0)):
                            current["score"] = item.get("score", current.get("score", 0.0))
                if ranking:
                    rankings.append(ranking)
                    weights.append(weights_by_intent[bucket_name])

            rrf_scores = compute_rrf(rankings, k=60, weights=weights) if rankings else {}
            fused = []
            for key, sc in rrf_scores.items():
                item = candidate_pool.get(key)
                if not item:
                    continue
                item["rrf_score"] = float(sc)
                fused.append(item)
            fused.sort(key=lambda x: (x.get("rrf_score", 0.0), -x.get("_bucket_priority", 9), x.get("score", 0.0)), reverse=True)

            # Strip helper fields
            final_list = []
            for item in fused:
                clean = dict(item)
                clean.pop("_bucket_priority", None)
                final_list.append(clean)
        else:
            # ---------------------------------------------------------
            # STRICT CONCATENATION & DEDUPLICATION
            # Priority: EXACT > LEMMA > SEMANTIC
            # ---------------------------------------------------------
            final_list = []
            seen_ids = set()

            # Sort Buckets Internally
            bucket_exact.sort(key=get_bucket_sort_key)
            bucket_lemma.sort(key=get_bucket_sort_key)

            def add_batch(batch, match_label):
                for item in batch:
                    key = self._item_key(item)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        if 'match_type' not in item:
                            item['match_type'] = match_label
                        final_list.append(item)

            add_batch(bucket_exact, 'content_exact')
            add_batch(bucket_lemma, 'content_fuzzy')
            add_batch(bucket_semantic, 'semantic')

        lexical_total = None
        semantic_total_raw = None
        semantic_tail_added = None
        semantic_tail_cap_value = None
        mix_policy_applied = None

        # Optional Layer-2 mix policy:
        # 1) lexical (exact+lemma) first
        # 2) then semantic tail with a global cap
        if result_mix_policy == "lexical_then_semantic_tail":
            semantic_tail_cap_value = (
                semantic_tail_cap
                if isinstance(semantic_tail_cap, int) and semantic_tail_cap > 0
                else default_semantic_tail_cap
            )

            lexical_list: List[Dict[str, Any]] = []
            semantic_list_raw: List[Dict[str, Any]] = []
            seen_keys = set()

            for item in final_list:
                key = self._item_key(item)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                match_type = str(item.get("match_type", "")).lower()
                is_semantic = "semantic" in match_type
                if is_semantic:
                    semantic_list_raw.append(item)
                else:
                    lexical_list.append(item)

            lexical_source_types = {
                str(item.get("source_type", "")).upper()
                for item in lexical_list
                if item.get("source_type")
            }

            def get_score(item: Dict[str, Any]) -> float:
                try:
                    return float(item.get("score", 0.0) or 0.0)
                except Exception:
                    return 0.0

            # Quality gate for semantic tail:
            # Keep meaning-rich chunks, reject obvious placeholder/test/template rows.
            def is_semantic_candidate_eligible(item: Dict[str, Any]) -> bool:
                if not noise_guard_applied:
                    return True

                content = str(item.get("content_chunk", "") or "").strip()
                content_lc = content.lower()
                title_lc = str(item.get("title", "") or "").strip().lower()
                source_type = str(item.get("source_type", "") or "").strip().upper()

                allowed_source_types = {
                    "PDF", "EPUB", "PDF_CHUNK", "BOOK",
                    "HIGHLIGHT", "INSIGHT", "NOTES",
                    "PERSONAL_NOTE", "ARTICLE", "WEBSITE", "GRAPH_RELATION"
                }
                if source_type and source_type not in allowed_source_types:
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

                if "deneme" in title_lc and len(content) < 180:
                    return False

                if "unknown" in title_lc and len(content) < 220:
                    return False

                return True

            semantic_list = [item for item in semantic_list_raw if is_semantic_candidate_eligible(item)]
            semantic_list.sort(key=get_score, reverse=True)

            # Adaptive confidence floor:
            # avoids low-score noise while still allowing semantic tail for low-score corpora.
            adaptive_score_floor = 0.0
            if noise_guard_applied and semantic_list:
                top_score = get_score(semantic_list[0])
                if top_score > 0:
                    adaptive_score_floor = max(2.0, top_score * 0.35)

            semantic_scored = semantic_list
            if noise_guard_applied and adaptive_score_floor > 0:
                semantic_scored = [item for item in semantic_list if get_score(item) >= adaptive_score_floor]

            if not semantic_scored and semantic_list:
                semantic_scored = semantic_list[: max(semantic_tail_cap_value, 3)]

            # Prefer source types already present in lexical hits; then backfill.
            if lexical_source_types:
                preferred_semantic = [
                    item for item in semantic_scored
                    if str(item.get("source_type", "")).upper() in lexical_source_types
                ]
                secondary_semantic = [
                    item for item in semantic_scored
                    if str(item.get("source_type", "")).upper() not in lexical_source_types
                ]
                semantic_ordered = preferred_semantic + secondary_semantic
            else:
                semantic_ordered = semantic_scored

            semantic_total_raw = len(semantic_list_raw)
            lexical_total = len(lexical_list)
            if (
                getattr(settings, "SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED", True)
                and self._token_count(query_original) == 1
            ):
                semantic_tail_policy = "dynamic_single_token"
                semantic_tail_cap_value = self._dynamic_single_token_semantic_cap(lexical_total)
            semantic_tail = semantic_ordered[:semantic_tail_cap_value]
            semantic_tail_added = len(semantic_tail)
            final_list = lexical_list + semantic_tail
            mix_policy_applied = "lexical_then_semantic_tail"

        # Pagination Slicing
        total_found = len(final_list)
        top_candidates = final_list[offset : offset + limit]

        duration = time.time() - start_time

        # Log search (best-effort)
        search_log_id = None
        diagnostic_payload = {
            "retrieval_fusion_mode": fusion_mode,
            "retrieval_path": "hybrid",
            "retrieval_steps": bucket_raw_counts,
            "router_mode": settings.SEARCH_ROUTER_MODE,
            "router_reason": router_reason,
            "retrieval_mode": retrieval_mode,
            "selected_buckets": selected_buckets,
            "executed_strategies": executed_strategies,
            "lexical_total": lexical_total,
            "semantic_total_raw": semantic_total_raw,
            "semantic_tail_cap": semantic_tail_cap_value,
            "semantic_tail_added": semantic_tail_added,
            "semantic_tail_policy": semantic_tail_policy,
            "result_mix_policy": mix_policy_applied,
            "query_original": query_original,
            "query_corrected": query_corrected,
            "query_correction_applied": query_correction_applied,
            "typo_rescue_applied": typo_rescue_applied,
            "lemma_seed_fallback_applied": lemma_seed_fallback_applied,
            "visibility_scope": visibility_scope,
            "content_type_filter": content_type,
            "ingestion_type_filter": ingestion_type,
            "latency_budget_applied": latency_budget_applied,
            "graph_timeout_triggered": graph_timeout_triggered,
            "noise_guard_applied": noise_guard_applied,
            "expansion_skipped_reason": expansion_skipped_reason,
            "strategy_timing_ms": strategy_timing_ms,
            "VECTOR_TIME_MS": strategy_timing_ms.get("SemanticMatchStrategy"),
            "GRAPH_TIME_MS": None,
            "RERANK_TIME_MS": None,
            "LLM_TIME_MS": None,
            "CACHE_HIT": False,
            "CACHE_LAYER": "MISS",
            "total_count": total_found,
            "duration_ms": int(duration * 1000),
        }
        try:
            search_log_id = self._log_search(
                firebase_uid,
                query,
                intent,
                None,
                top_candidates,
                duration,
                session_id=session_id,
                diagnostic_payload=diagnostic_payload,
            )
        except Exception as e:
            logger.error(f"Search log failed: {e}")

        # Cache results (best-effort)
        if self.cache and cache_key:
            try:
                self.cache.set(
                    cache_key,
                    {
                        "results": top_candidates,
                        "total_count": total_found,
                        "metadata": {
                            "retrieval_fusion_mode": fusion_mode,
                            "retrieval_path": "hybrid",
                            "retrieval_steps": bucket_raw_counts,
                            "router_mode": settings.SEARCH_ROUTER_MODE,
                            "router_reason": router_reason,
                            "retrieval_mode": retrieval_mode,
                            "selected_buckets": selected_buckets,
                            "executed_strategies": executed_strategies,
                            "lexical_total": lexical_total,
                            "semantic_total_raw": semantic_total_raw,
                            "semantic_tail_cap": semantic_tail_cap_value,
                            "semantic_tail_cap_effective": semantic_tail_cap_value,
                            "semantic_tail_added": semantic_tail_added,
                            "semantic_tail_policy": semantic_tail_policy,
                            "result_mix_policy": mix_policy_applied,
                            "query_original": query_original,
                            "query_corrected": query_corrected,
                            "query_correction_applied": query_correction_applied,
                            "typo_rescue_applied": typo_rescue_applied,
                            "lemma_seed_fallback_applied": lemma_seed_fallback_applied,
                            "visibility_scope": visibility_scope,
                            "content_type_filter": content_type,
                            "ingestion_type_filter": ingestion_type,
                            "latency_budget_applied": latency_budget_applied,
                            "graph_timeout_triggered": graph_timeout_triggered,
                            "noise_guard_applied": noise_guard_applied,
                            "expansion_skipped_reason": expansion_skipped_reason,
                            "strategy_timing_ms": strategy_timing_ms,
                            "VECTOR_TIME_MS": strategy_timing_ms.get("SemanticMatchStrategy"),
                            "GRAPH_TIME_MS": None,
                            "RERANK_TIME_MS": None,
                            "LLM_TIME_MS": None,
                            "CACHE_HIT": False,
                            "CACHE_LAYER": "MISS",
                        },
                    },
                    ttl=settings.CACHE_L1_TTL
                )
            except Exception as e:
                logger.error(f"Search cache set failed: {e}")

        metadata = {
            "total_count": total_found,
            "cached": False,
            "search_log_id": search_log_id,
            "duration_ms": int(duration * 1000),
            "retrieval_fusion_mode": fusion_mode,
            "retrieval_path": "hybrid",
            "retrieval_steps": bucket_raw_counts,
            "router_mode": settings.SEARCH_ROUTER_MODE,
            "router_reason": router_reason,
            "retrieval_mode": retrieval_mode,
            "selected_buckets": selected_buckets,
            "executed_strategies": executed_strategies,
            "lexical_total": lexical_total,
            "semantic_total_raw": semantic_total_raw,
            "semantic_tail_cap": semantic_tail_cap_value,
            "semantic_tail_cap_effective": semantic_tail_cap_value,
            "semantic_tail_added": semantic_tail_added,
            "semantic_tail_policy": semantic_tail_policy,
            "result_mix_policy": mix_policy_applied,
            "query_original": query_original,
            "query_corrected": query_corrected,
            "query_correction_applied": query_correction_applied,
            "typo_rescue_applied": typo_rescue_applied,
            "lemma_seed_fallback_applied": lemma_seed_fallback_applied,
            "visibility_scope": visibility_scope,
            "content_type_filter": content_type,
            "ingestion_type_filter": ingestion_type,
            "latency_budget_applied": latency_budget_applied,
            "graph_timeout_triggered": graph_timeout_triggered,
            "noise_guard_applied": noise_guard_applied,
            "expansion_skipped_reason": expansion_skipped_reason,
            "strategy_timing_ms": strategy_timing_ms,
            "VECTOR_TIME_MS": strategy_timing_ms.get("SemanticMatchStrategy"),
            "GRAPH_TIME_MS": None,
            "RERANK_TIME_MS": None,
            "LLM_TIME_MS": None,
            "CACHE_HIT": False,
            "CACHE_LAYER": "MISS",
        }

        return top_candidates, metadata

    # Helper for DB Logging
    def _log_search(
        self,
        uid,
        query,
        intent,
        rrf_scores,
        results,
        duration,
        session_id: Optional[int | str] = None,
        diagnostic_payload: Optional[Dict[str, Any]] = None,
    ):
        try:
            from infrastructure.db_manager import DatabaseManager
            global _LAST_SEARCH_LOG_CLEANUP_TS
            
            top_id = results[0]['id'] if results else None
            top_score = results[0].get('rrf_score', results[0].get('score', 0)) if results else 0
            
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    weights_str = f"fusion:{settings.RETRIEVAL_FUSION_MODE}, vec:1.0, bm25:1.0, graph:1.0"
                    id_var = cursor.var(int)
                    strategy_json = json.dumps(diagnostic_payload or {}, ensure_ascii=False)
                    
                    # Coerce session_id to int if possible to avoid ORA-01722 when UUID-like strings are passed
                    sid_int = None
                    try:
                        sid_int = int(session_id) if session_id is not None and str(session_id).strip().isdigit() else None
                    except Exception:
                        sid_int = None
                    
                    if bool(getattr(settings, "SEARCH_LOG_DIAGNOSTICS_PERSIST_ENABLED", False)):
                        try:
                            cursor.execute(
                                """
                                INSERT INTO TOMEHUB_SEARCH_LOGS
                                (FIREBASE_UID, SESSION_ID, QUERY_TEXT, INTENT, RRF_WEIGHTS, TOP_RESULT_ID, TOP_RESULT_SCORE, EXECUTION_TIME_MS, STRATEGY_DETAILS)
                                VALUES (:p_uid, :p_sid, :p_q, :p_intent, :p_w, :p_tid, :p_tscore, :p_dur, :p_strategy)
                                RETURNING ID INTO :id_col
                                """,
                                {
                                    "p_uid": uid,
                                    "p_sid": sid_int,
                                    "p_q": query,
                                    "p_intent": intent,
                                    "p_w": weights_str,
                                    "p_tid": top_id,
                                    "p_tscore": top_score,
                                    "p_dur": duration * 1000,
                                    "p_strategy": strategy_json,
                                    "id_col": id_var,
                                },
                            )
                        except Exception as col_err:
                            # Backward compatible fallback when STRATEGY_DETAILS column is absent.
                            if "ORA-00904" not in str(col_err):
                                raise
                            cursor.execute(
                                """
                                INSERT INTO TOMEHUB_SEARCH_LOGS
                                (FIREBASE_UID, SESSION_ID, QUERY_TEXT, INTENT, RRF_WEIGHTS, TOP_RESULT_ID, TOP_RESULT_SCORE, EXECUTION_TIME_MS)
                                VALUES (:p_uid, :p_sid, :p_q, :p_intent, :p_w, :p_tid, :p_tscore, :p_dur)
                                RETURNING ID INTO :id_col
                                """,
                                {
                                    "p_uid": uid,
                                    "p_sid": sid_int,
                                    "p_q": query,
                                    "p_intent": intent,
                                    "p_w": weights_str,
                                    "p_tid": top_id,
                                    "p_tscore": top_score,
                                    "p_dur": duration * 1000,
                                    "id_col": id_var,
                                },
                            )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO TOMEHUB_SEARCH_LOGS
                            (FIREBASE_UID, SESSION_ID, QUERY_TEXT, INTENT, RRF_WEIGHTS, TOP_RESULT_ID, TOP_RESULT_SCORE, EXECUTION_TIME_MS)
                            VALUES (:p_uid, :p_sid, :p_q, :p_intent, :p_w, :p_tid, :p_tscore, :p_dur)
                            RETURNING ID INTO :id_col
                            """,
                            {
                                "p_uid": uid,
                                "p_sid": sid_int,
                                "p_q": query,
                                "p_intent": intent,
                                "p_w": weights_str,
                                "p_tid": top_id,
                                "p_tscore": top_score,
                                "p_dur": duration * 1000,
                                "id_col": id_var,
                            },
                        )
                    
                    # id_var.getvalue() returns a list for returning into
                    vals = id_var.getvalue()
                    if vals:
                        log_id = vals[0]
                        cleanup_enabled = bool(getattr(settings, "SEARCH_LOG_RETENTION_CLEANUP_ENABLED", False))
                        if cleanup_enabled and (time.time() - _LAST_SEARCH_LOG_CLEANUP_TS) > 3600:
                            try:
                                cursor.execute(
                                    """
                                    DELETE FROM TOMEHUB_SEARCH_LOGS
                                    WHERE TIMESTAMP < (CURRENT_TIMESTAMP - NUMTODSINTERVAL(:p_days, 'DAY'))
                                    """,
                                    {"p_days": int(getattr(settings, "SEARCH_LOG_RETENTION_DAYS", 90))},
                                )
                                _LAST_SEARCH_LOG_CLEANUP_TS = time.time()
                            except Exception:
                                pass
                        conn.commit()
                        return int(log_id)
                    else:
                        print(f"[ERROR] LOGGING FAILED: No ID returned. Vals={vals}")
                        return None
        except Exception as e:
            logger.error(f"Failed to log search analytics: {e}")
            print(f"[ERROR] LOGGING FAILED: {e}")
            return None
