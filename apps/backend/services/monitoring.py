# -*- coding: utf-8 -*-
"""
TomeHub Monitoring Service
==========================
Defines custom Prometheus metrics for "Epistemic Observability".
These metrics track the quality, intent, and diversity of the system's "brain".
"""

from prometheus_client import Counter, Histogram, Gauge

# ==============================================================================
# 1. JUDGE AI METRICS (Quality Control)
# ==============================================================================
# Tracks the score given by the Judge AI, segmented by "why".
# Labels:
# - intent: DIRECT, COMPARATIVE, SYNTHESIS
# - network_status: IN_NETWORK, OUT_OF_NETWORK
# - verdict: PASS, REGENERATE, DECLINE
JUDGE_SCORE = Histogram(
    'tomehub_judge_score', 
    'Quality score assigned by Judge AI (0.0 to 1.0)',
    labelnames=['intent', 'network_status', 'verdict'],
    buckets=(0.1, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0)
)

# ==============================================================================
# 2. SEARCH & GRAPH METRICS (Recall & Diversity)
# ==============================================================================
# Tracks how many "invisible bridges" were found per query.
# Using Histogram to see the distribution (e.g., "Most queries find 0 bridges, some find 10")
GRAPH_BRIDGES_FOUND = Histogram(
    'tomehub_graph_bridges_found',
    'Number of semantic bridges found via GraphRAG per query',
    buckets=(0, 1, 3, 5, 10, 20)
)

# Tracks the number of unique books in the final result set (Diversity)
SEARCH_DIVERSITY_COUNT = Histogram(
    'tomehub_search_diversity_source_count',
    'Number of unique sources (books) in the final top results',
    buckets=(1, 2, 3, 5, 8, 10, 15)
)

# Tracks empty or low-recall searches
SEARCH_RESULT_COUNT = Histogram(
    'tomehub_search_result_count',
    'Total number of chunks retrieved before filtering',
    buckets=(0, 5, 10, 30, 50, 100)
)

# Tracks which retrieval fusion mode is used (concat vs rrf).
SEARCH_FUSION_MODE_TOTAL = Counter(
    'tomehub_search_fusion_mode_total',
    'Count of retrieval fusion mode usage',
    labelnames=['fusion_mode']
)

# ODL secondary observability
ODL_SHADOW_JOBS_TOTAL = Counter(
    'tomehub_odl_shadow_jobs_total',
    'ODL shadow ingestion jobs by status',
    labelnames=['status']
)

ODL_SHADOW_JOB_DURATION_SECONDS = Histogram(
    'tomehub_odl_shadow_job_duration_seconds',
    'ODL shadow ingestion job duration in seconds',
    labelnames=['status'],
    buckets=(0.5, 1.0, 3.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 300.0)
)

ODL_SHADOW_READY_COUNT = Gauge(
    'tomehub_odl_shadow_ready_count',
    'Latest READY chunk count for ODL shadow by user and item',
    labelnames=['firebase_uid', 'item_id']
)

ODL_RESCUE_CALLS_TOTAL = Counter(
    'tomehub_odl_rescue_calls_total',
    'ODL rescue calls by trigger reason',
    labelnames=['reason']
)

ODL_RESCUE_TIMEOUT_TOTAL = Counter(
    'tomehub_odl_rescue_timeout_total',
    'ODL rescue timeout count'
)

ODL_RESCUE_CANDIDATE_CONTRIBUTION_RATIO = Histogram(
    'tomehub_odl_rescue_candidate_contribution_ratio',
    'ODL candidate share inside top-k response',
    buckets=(0.0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0)
)

ODL_RESCUE_LATENCY_DELTA_MS = Histogram(
    'tomehub_odl_rescue_latency_delta_ms',
    'Additional ODL rescue latency in milliseconds',
    buckets=(1, 5, 10, 20, 40, 80, 120, 200, 300, 500, 1000)
)

# Graph enrichment metrics (async jobs triggered on ingest or manual calls)
GRAPH_ENRICH_JOBS_TOTAL = Counter(
    'tomehub_graph_enrich_jobs_total',
    'Graph enrichment jobs by status and reason',
    labelnames=['status', 'reason']
)

GRAPH_ENRICH_CHUNKS_TOTAL = Counter(
    'tomehub_graph_enrich_chunks_total',
    'Graph enrichment chunk outcomes',
    labelnames=['outcome']
)

GRAPH_ENRICH_DURATION_SECONDS = Histogram(
    'tomehub_graph_enrich_duration_seconds',
    'Graph enrichment job duration in seconds',
    labelnames=['status'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0, 60.0)
)

# ==============================================================================
# 3. TECHNICAL METRICS (Resilience & Traffic)
# ==============================================================================

# DB Pool Utilization (Gauge)
# Labels: pool_type (read, write), metric_type (active, idle, max)
DB_POOL_UTILIZATION = Gauge(
    'tomehub_db_pool_utilization',
    'Database connection pool statistics',
    labelnames=['pool_type', 'metric_type']
)

# Ingestion Processing (Histogram)
# Labels: status (success, fail), source_type (PDF, EPUB, etc.)
INGESTION_LATENCY = Histogram(
    'tomehub_ingestion_duration_seconds',
    'Latency of document ingestion in seconds',
    labelnames=['status', 'source_type'],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

# AI Service (Gemini/Embedding) Latency (Histogram)
# Labels: service (gemini_flash, google_embedding), operation (generate, embed)
AI_SERVICE_LATENCY = Histogram(
    'tomehub_ai_service_duration_seconds',
    'Latency of external AI service calls',
    labelnames=['service', 'operation'],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
)

LLM_CALLS_TOTAL = Counter(
    'tomehub_llm_calls_total',
    'Total number of LLM calls',
    labelnames=['task', 'model_tier', 'status']
)

LLM_PROVIDER_CALLS_TOTAL = Counter(
    'tomehub_llm_provider_calls_total',
    'Total number of LLM calls by provider',
    labelnames=['task', 'provider', 'status']
)

LLM_FALLBACK_TOTAL = Counter(
    'tomehub_llm_fallback_total',
    'Total number of model/provider fallback events',
    labelnames=['from_provider', 'to_provider', 'reason']
)

LLM_TOKENS_TOTAL = Counter(
    'tomehub_llm_tokens_total',
    'Total number of LLM tokens by direction',
    labelnames=['task', 'model_tier', 'direction']
)

LLM_PARALLEL_RACE_TOTAL = Counter(
    'tomehub_llm_parallel_race_total',
    'Explorer parallel NVIDIA race outcomes and winners',
    labelnames=['route_mode', 'winner_provider', 'winner_model', 'status']
)

LLM_PARALLEL_RACE_LOSER_TOTAL = Counter(
    'tomehub_llm_parallel_race_loser_total',
    'Explorer parallel NVIDIA race loser outcomes',
    labelnames=['route_mode', 'loser_provider', 'outcome']
)

LLM_RPM_GUARD_TOTAL = Counter(
    'tomehub_llm_rpm_guard_total',
    'Rate-limit guard slot reservation decisions for Qwen/NVIDIA route',
    labelnames=['provider', 'result', 'mode']
)

REDIS_AVAILABLE = Gauge(
    'tomehub_redis_available',
    'Whether Redis-backed L2 cache is available (1=yes, 0=no)',
    labelnames=['layer']
)

DATA_CLEANER_AI_APPLIED_TOTAL = Counter(
    'tomehub_data_cleaner_ai_applied_total',
    'Number of ingestion chunks sent to AI data cleaner'
)

DATA_CLEANER_AI_SKIPPED_TOTAL = Counter(
    'tomehub_data_cleaner_ai_skipped_total',
    'Number of ingestion chunks skipped from AI data cleaner',
    labelnames=['reason']
)

DATA_CLEANER_NOISE_SCORE = Histogram(
    'tomehub_data_cleaner_noise_score',
    'Heuristic noise score of chunks before AI cleaning',
    buckets=(0, 1, 2, 3, 4, 5, 7, 10, 15, 20)
)

L3_PERF_GUARD_APPLIED_TOTAL = Counter(
    'tomehub_l3_perf_guard_applied_total',
    'Total number of Layer-3 performance guard applications',
    labelnames=['guard_name']
)

L3_PHASE_LATENCY_SECONDS = Histogram(
    'tomehub_l3_phase_latency_seconds',
    'Layer-3 phase latency in seconds',
    labelnames=['phase'],
    buckets=(0.01, 0.05, 0.1, 0.3, 0.6, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0)
)

# Flow Text Repair Metrics (Layer 4 display-time quality gate)
FLOW_TEXT_REPAIR_APPLIED_TOTAL = Counter(
    'tomehub_flow_text_repair_applied_total',
    'Number of flow card texts repaired successfully',
    labelnames=['source_type', 'ruleset']
)

FLOW_TEXT_REPAIR_SKIPPED_TOTAL = Counter(
    'tomehub_flow_text_repair_skipped_total',
    'Number of flow card texts skipped from repair',
    labelnames=['source_type', 'reason']
)

FLOW_TEXT_REPAIR_HIGH_DELTA_REJECT_TOTAL = Counter(
    'tomehub_flow_text_repair_high_delta_reject_total',
    'Number of flow card texts rejected due to high delta ratio',
    labelnames=['source_type']
)

FLOW_TEXT_REPAIR_LATENCY_SECONDS = Histogram(
    'tomehub_flow_text_repair_latency_seconds',
    'Latency of flow text repair execution in seconds',
    labelnames=['source_type', 'ruleset'],
    buckets=(0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05)
)

# Circuit Breaker Status (Gauge)
# 0 = Closed (All good), 1 = Half-Open, 2 = Open (Blocked)
CIRCUIT_BREAKER_STATE = Gauge(
    'tomehub_circuit_breaker_state',
    'Current state of the embedding API circuit breaker',
    labelnames=['service']
)

# Firestore -> Oracle sync backfill observability
EMBEDDING_BACKFILL_TOTAL_CALLS = Counter(
    'tomehub_embedding_backfill_total_calls',
    'Total embedding calls performed by firestore->oracle backfill worker'
)

EMBEDDING_BACKFILL_QUEUE_DEPTH = Gauge(
    'tomehub_embedding_backfill_queue_depth',
    'Approximate number of pending firestore items in active backfill queue'
)

EMBEDDING_BACKFILL_COST_ESTIMATE = Gauge(
    'tomehub_embedding_backfill_cost_estimate_usd',
    'Estimated embedding backfill cost in USD'
)
