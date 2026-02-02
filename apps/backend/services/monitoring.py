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

# Circuit Breaker Status (Gauge)
# 0 = Closed (All good), 1 = Half-Open, 2 = Open (Blocked)
CIRCUIT_BREAKER_STATE = Gauge(
    'tomehub_circuit_breaker_state',
    'Current state of the embedding API circuit breaker',
    labelnames=['service']
)
