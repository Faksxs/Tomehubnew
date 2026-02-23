# Phase 6 Live Smoke (Real API + DB) Report (2026-02-22)

- Generated: `2026-02-22 23:07:41 UTC`
- Verdict: `PASS`
- Base URL: `http://127.0.0.1:64129`
- Uvicorn lifespan off: `True`
- Sample uid: `vpq1p0UzcCSLAh1d18WgZZWPBE63`
- Sample book_id: `1771629445701`

## Checks

- `seed_outbox_event`: `pass` - event_id=21
- `server_ready`: `pass` - http://127.0.0.1:64129/docs reachable
- `realtime_poll`: `pass` (http=200) - source=outbox count=5
- `ingestion_status`: `pass` (http=200) - match_source=exact_book_id confidence=1.0
- `smart_search`: `pass` (http=200) - total=12 vis=default
- `search`: `pass` (http=200) - answer_len=2167

## Server Logs (stderr tail)

```text
Firebase credentials not configured (OK for development only)
{"asctime": "2026-02-23 00:07:22,309", "levelname": "INFO", "name": "tomehub_api", "message": "Importing flow_routes..."}
{"asctime": "2026-02-23 00:07:22,309", "levelname": "INFO", "name": "tomehub_api", "message": "Importing flow_routes..."}
{"asctime": "2026-02-23 00:07:22,333", "levelname": "INFO", "name": "tomehub_api", "message": "Router registered", "route_count": 6}
{"asctime": "2026-02-23 00:07:22,333", "levelname": "INFO", "name": "tomehub_api", "message": "Router registered", "route_count": 6}
INFO:     Started server process [9124]
INFO:     Uvicorn running on http://127.0.0.1:64129 (Press CTRL+C to quit)
{"asctime": "2026-02-23 00:07:22,376", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from query params"}
{"asctime": "2026-02-23 00:07:22,962", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from query params"}
{"asctime": "2026-02-23 00:07:23,361", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from JSON body"}
{"asctime": "2026-02-23 00:07:23,404", "levelname": "WARNING", "name": "zeyrek.rulebasedanalyzer", "message": "APPENDING RESULT: <(bilhassa_Adv)(-)(bilhassa:advRoot_ST)>"}
{"asctime": "2026-02-23 00:07:24,946", "levelname": "WARNING", "name": "middleware.auth_middleware", "message": "DEV_UNSAFE_AUTH_BYPASS enabled: Using firebase_uid from JSON body"}
{"asctime": "2026-02-23 00:07:24,947", "levelname": "INFO", "name": "tomehub_api", "message": "Using JWT-verified UID: vpq1p0UzcCSLAh1d18WgZZWPBE63"}
{"asctime": "2026-02-23 00:07:24,947", "levelname": "INFO", "name": "tomehub_api", "message": "Using JWT-verified UID: vpq1p0UzcCSLAh1d18WgZZWPBE63"}
{"asctime": "2026-02-23 00:07:24,947", "levelname": "INFO", "name": "tomehub_api", "message": "Search started", "uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63", "question": "bilhassa"}
{"asctime": "2026-02-23 00:07:24,947", "levelname": "INFO", "name": "tomehub_api", "message": "Search started", "uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63", "question": "bilhassa"}
{"asctime": "2026-02-23 00:07:25,198", "levelname": "WARNING", "name": "zeyrek.rulebasedanalyzer", "message": "APPENDING RESULT: <(bilhassa_Adv)(-)(bilhassa:advRoot_ST)>"}
{"asctime": "2026-02-23 00:07:41,515", "levelname": "INFO", "name": "tomehub_api", "message": "Search finished successfully", "answer_length": 2167, "source_count": 7, "first_source_title": "Hayat\u0131n Anlam\u0131 - Terry Eagleton", "first_source_score": null, "metadata": {"degradations": [], "status": "healthy", "search_log_id": 1502, "graph_candidates_count": 0, "external_graph_candidates_count": 0, "vector_candidates_count": 7, "source_diversity_count": 5, "source_type_diversity_count": 1, "academic_scope": false, "external_kb_used": false, "wikidata_qid": null, "openalex_used": false, "dbpedia_used": false, "orkg_used": false, "retrieval_fusion_mode": "concat", "retrieval_path": "hybrid", "router_mode": "rule_based", "router_reason": "intent=FOLLOW_UP", "retrieval_mode": "fast_exact", "latency_budget_applied": false, "graph_timeout_triggered": false, "graph_skipped_by_intent": true, "noise_guard_applied": true, "noise_guard_filtered_graph_count": 0, "supplementary_keyword_search_applied": false, "supplementary_search_skipped_reason": "keyword_variant_missing", "expansion_skipped_reason": null, "compare_applied": false, "target_books_used": [], "target_books_truncated": false, "evidence_policy": "standard", "per_book_evidence_count": {}, "compare_degrade_reason": "", "compare_mode": "EXPLICIT_ONLY", "level_counts": {"A": 2, "B": 5, "C": 0}, "selected_buckets": ["exact", "lemma"], "executed_strategies": ["ExactMatchStrategy", "LemmaMatchStrategy"], "vector_metadata": {"cached": false, "duration_ms": 362, "retrieval_steps": {"initial_exact_raw_count": 7, "initial_lemma_raw_count": 7, "initial_lexical_raw_count": 14, "exact_raw_count": 7, "lemma_raw_count": 7, "semantic_raw_count": 0, "semantic_variation_query_count": 0, "semantic_variation_hit_count": 0, "typo_rescue_added_exact": 0, "typo_rescue_added_lemma": 0, "lemma_seed_added_exact": 0}, "router_mode": "rule_based", "router_reason": "intent=FOLLOW_UP", "retrieval_mode": "fast_exact", "selected_buckets": ["exact", "lemma"], "executed_strategies": ["ExactMatchStrategy", "LemmaMatchStrategy"]}, "model_name": "gemini-2.5-flash", "model_tier": "flash", "provider_name": "gemini", "model_fallback_applied": false, "secondary_fallback_applied": false, "fallback_reason": null, "llm_generation_timeout_applied": false, "context_budget_applied": false, "quote_target_count": 2, "short_answer_recovery_applied": false, "graph_bridge_attempted": false, "graph_bridge_used": false, "graph_bridge_timeout_triggered": false, "graph_bridge_latency_ms": 0.0}}
{"asctime": "2026-02-23 00:07:41,515", "levelname": "INFO", "name": "tomehub_api", "message": "Search finished successfully", "answer_length": 2167, "source_count": 7, "first_source_title": "Hayat\u0131n Anlam\u0131 - Terry Eagleton", "first_source_score": null, "metadata": {"degradations": [], "status": "healthy", "search_log_id": 1502, "graph_candidates_count": 0, "external_graph_candidates_count": 0, "vector_candidates_count": 7, "source_diversity_count": 5, "source_type_diversity_count": 1, "academic_scope": false, "external_kb_used": false, "wikidata_qid": null, "openalex_used": false, "dbpedia_used": false, "orkg_used": false, "retrieval_fusion_mode": "concat", "retrieval_path": "hybrid", "router_mode": "rule_based", "router_reason": "intent=FOLLOW_UP", "retrieval_mode": "fast_exact", "latency_budget_applied": false, "graph_timeout_triggered": false, "graph_skipped_by_intent": true, "noise_guard_applied": true, "noise_guard_filtered_graph_count": 0, "supplementary_keyword_search_applied": false, "supplementary_search_skipped_reason": "keyword_variant_missing", "expansion_skipped_reason": null, "compare_applied": false, "target_books_used": [], "target_books_truncated": false, "evidence_policy": "standard", "per_book_evidence_count": {}, "compare_degrade_reason": "", "compare_mode": "EXPLICIT_ONLY", "level_counts": {"A": 2, "B": 5, "C": 0}, "selected_buckets": ["exact", "lemma"], "executed_strategies": ["ExactMatchStrategy", "LemmaMatchStrategy"], "vector_metadata": {"cached": false, "duration_ms": 362, "retrieval_steps": {"initial_exact_raw_count": 7, "initial_lemma_raw_count": 7, "initial_lexical_raw_count": 14, "exact_raw_count": 7, "lemma_raw_count": 7, "semantic_raw_count": 0, "semantic_variation_query_count": 0, "semantic_variation_hit_count": 0, "typo_rescue_added_exact": 0, "typo_rescue_added_lemma": 0, "lemma_seed_added_exact": 0}, "router_mode": "rule_based", "router_reason": "intent=FOLLOW_UP", "retrieval_mode": "fast_exact", "selected_buckets": ["exact", "lemma"], "executed_strategies": ["ExactMatchStrategy", "LemmaMatchStrategy"]}, "model_name": "gemini-2.5-flash", "model_tier": "flash", "provider_name": "gemini", "model_fallback_applied": false, "secondary_fallback_applied": false, "fallback_reason": null, "llm_generation_timeout_applied": false, "context_budget_applied": false, "quote_target_count": 2, "short_answer_recovery_applied": false, "graph_bridge_attempted": false, "graph_bridge_used": false, "graph_bridge_timeout_triggered": false, "graph_bridge_latency_ms": 0.0}}
```

## Server Logs (stdout tail)

```text
INFO:     127.0.0.1:64138 - "GET /docs HTTP/1.1" 200 OK
INFO:     127.0.0.1:64139 - "GET /api/realtime/poll?firebase_uid=vpq1p0UzcCSLAh1d18WgZZWPBE63&since_ms=0&limit=10 HTTP/1.1" 200 OK
INFO:     127.0.0.1:64143 - "GET /api/books/1771629445701/ingestion-status?firebase_uid=vpq1p0UzcCSLAh1d18WgZZWPBE63 HTTP/1.1" 200 OK
{"timestamp": "2026-02-22T23:07:23.363321Z", "level": "INFO", "name": "search_orchestrator", "message": "Orchestrator: Search started for query='bilhassa' UID='vpq1p0UzcCSLAh1d18WgZZWPBE63' intent='SYNTHESIS'"}

[ORCHESTRATOR] SEARCH: 'bilhassa' | UID: vpq1p0UzcCSLAh1d18WgZZWPBE63 | Intent: SYNTHESIS
{"timestamp": "2026-02-22T23:07:23.745201Z", "level": "INFO", "name": "search_orchestrator", "message": "Strat ExactMatchStrategy returned 7 hits"}
{"timestamp": "2026-02-22T23:07:23.880247Z", "level": "INFO", "name": "search_orchestrator", "message": "Strat LemmaMatchStrategy returned 7 hits"}
{"timestamp": "2026-02-22T23:07:24.893113Z", "level": "INFO", "name": "search_orchestrator", "message": "Strat SemanticMatchStrategy returned 36 hits"}
INFO:     127.0.0.1:64144 - "POST /api/smart-search HTTP/1.1" 200 OK
{"timestamp": "2026-02-22T23:07:25.197845Z", "level": "INFO", "name": "search_orchestrator", "message": "Orchestrator: Search started for query='bilhassa' UID='vpq1p0UzcCSLAh1d18WgZZWPBE63' intent='FOLLOW_UP'"}

[ORCHESTRATOR] SEARCH: 'bilhassa' | UID: vpq1p0UzcCSLAh1d18WgZZWPBE63 | Intent: FOLLOW_UP
{"timestamp": "2026-02-22T23:07:25.529417Z", "level": "INFO", "name": "search_orchestrator", "message": "Strat ExactMatchStrategy returned 7 hits"}
{"timestamp": "2026-02-22T23:07:25.559933Z", "level": "INFO", "name": "search_orchestrator", "message": "Strat LemmaMatchStrategy returned 7 hits"}
INFO:     127.0.0.1:64147 - "POST /api/search HTTP/1.1" 200 OK
```

