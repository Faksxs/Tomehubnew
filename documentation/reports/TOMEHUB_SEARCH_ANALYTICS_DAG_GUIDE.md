# TomeHub Search Analytics DAG
**File:** `dags/tomehub_search_analytics.py`  
**Created:** February 22, 2026

---

## Overview

Analytics DAG that processes daily search logs from `TOMEHUB_SEARCH_LOGS` and generates insights about:
- Intent distribution (Semantic vs Exact vs Lemma matches)
- Strategy effectiveness (RRF scoring, fusion weights)
- Query performance (execution time, latency distribution)
- User behavior patterns

---

## Schedule & Configuration

| Setting | Value |
|---------|-------|
| **DAG ID** | `tomehub_search_analytics` |
| **Schedule** | Daily at 2:00 AM UTC (`0 2 * * *`) |
| **Start Date** | 2026-02-01 |
| **Catchup** | Disabled (new DAG) |
| **Max Active Runs** | 1 (sequential daily runs) |
| **Timeout** | 2 hours (execution_timeout per task) |
| **Retries** | 2 attempts with 5-minute backoff |

---

## Task Workflow

```
extract_search_logs
        ↓
    ┌───┴───┬───────────────┐
    ↓       ↓               ↓
analyze  analyze      analyze_
intent   strategy     performance
    ↓       ↓               ↓
    └───┬───┴───────────────┘
        ↓
  generate_report
        ↓
  notify_completion
```

---

## Tasks Detailed

### 1. **extract_search_logs**
Fetches search logs from Oracle database for past 24 hours.

**Input:** Airflow execution date (`ds`)  
**Output:** Dictionary with:
- `logs_json`: Serialized Pandas DataFrame (JSON format)
- `metadata`: Count, date range, unique users
- `row_count`: Total logs extracted

**Query:**
```sql
SELECT ID, FIREBASE_UID, QUERY_TEXT, INTENT, STRATEGY_WEIGHTS,
       EXECUTION_TIME_MS, RRF_SCORE, RESULT_COUNT, CREATED_AT
FROM TOMEHUB_SEARCH_LOGS
WHERE CREATED_AT >= TRUNC(SYSDATE - 1)
ORDER BY CREATED_AT DESC
```

**Example Output:**
```python
{
  "logs_json": "[{...}, {...}]",  # Pandas JSON
  "metadata": {
    "total_logs": 1249,
    "date_range": "2026-02-21 to 2026-02-22",
    "unique_users": 3,
    "execution_time": "2026-02-22T02:00:00"
  },
  "row_count": 1249
}
```

---

### 2. **analyze_intent**
Classifies search queries by intent type.

**Intent Types:**
- `SEMANTIC_SEARCH`: Vector similarity matching
- `EXACT_MATCH`: Token-level matching
- `LEMMA_MATCH`: Normalized lemma matching (Turkish support)
- `HYBRID`: Multiple strategies combined

**Output:**
```python
{
  "intent_distribution": {
    "SEMANTIC_SEARCH": 650,
    "EXACT_MATCH": 450,
    "LEMMA_MATCH": 120,
    "HYBRID": 29
  },
  "intent_percentage": {
    "SEMANTIC_SEARCH": 52.04,
    "EXACT_MATCH": 36.03,
    "LEMMA_MATCH": 9.61,
    "HYBRID": 2.32
  },
  "most_common_intent": "SEMANTIC_SEARCH",
  "row_count": 1249
}
```

---

### 3. **analyze_strategy**
Evaluates strategy effectiveness using RRF (Reciprocal Rank Fusion) metrics.

**Metrics:**
- Average RRF score (0-1, higher is better)
- Execution time percentiles (P50, P95, P99)
- Average result count per query

**Output:**
```python
{
  "strategy_stats": {
    "avg_rrf_score": 0.72,
    "median_execution_time_ms": 847,
    "p95_execution_time_ms": 1823,
    "p99_execution_time_ms": 2456,
    "avg_result_count": 12.3
  },
  "row_count": 1249
}
```

---

### 4. **analyze_performance**
Calculates performance distribution and identifies slow queries.

**Performance Buckets:**
- Under 200ms: Fast queries
- 200-500ms: Good range
- 500-1000ms: Acceptable
- 1000-2000ms: Slow
- Over 2000ms: Very slow (requires attention)

**Output:**
```python
{
  "performance_stats": {
    "total_queries": 1249,
    "avg_execution_time_ms": 956.3,
    "slow_queries_count": 58,
    "slow_queries_pct": 4.64,
    "execution_time_buckets": {
      "under_200ms": 320,
      "200_500ms": 410,
      "500_1000ms": 361,
      "1000_2000ms": 100,
      "over_2000ms": 58
    }
  },
  "row_count": 1249
}
```

---

### 5. **generate_report**
Creates comprehensive markdown report combining all analyses.

**Report Sections:**
1. Executive Summary (total queries, users, date range)
2. Intent Distribution (pie-chart style percentages)
3. Strategy Effectiveness table (RRF, latency, results)
4. Performance Metrics (execution time buckets)
5. Slow Query Analysis
6. Smart Recommendations based on data

**Example Report:**
```markdown
# TomeHub Search Analytics Report
**Date:** 2026-02-22
**Generated:** 2026-02-22T02:15:30

---

## Executive Summary
- **Total Search Queries Analyzed:** 1,249
- **Unique Users:** 3
- **Date Range:** 2026-02-21 00:00 to 2026-02-22 00:00

...

## Recommendations
✅ **Query performance is healthy** - Below 5% slow query threshold
⚠️ **Intent skew detected** - SEMANTIC_SEARCH dominates 52.04% of queries
```

**Output:** String (report content)

---

### 6. **notify_completion**
Logs completion status and report preview.

**Output:** Logs summary to Airflow task logs:
```
╔════════════════════════════════════════════════════════════════╗
║  ✅ TomeHub Search Analytics Complete                          ║
╠════════════════════════════════════════════════════════════════╣
║  Date: 2026-02-22                                              ║
║  Runtime: 127 seconds                                          ║
║  Status: SUCCESS                                               ║
╚════════════════════════════════════════════════════════════════╝
```

---

## Dependencies & Libraries

**Required Packages:**
```
pandas>=1.3.0
apache-airflow>=2.7.0
oracledb>=1.0.0
```

**Internal Dependencies:**
- `infrastructure.db_manager.DatabaseManager` - Oracle connection pooling
- Airflow TaskFlow API (`@dag`, `@task`)

**Airflow Features Used:**
- TaskFlow API (modern DAG definition)
- XCom for task communication
- Context dictionary for execution metadata
- Retry with exponential backoff
- Task execution timeout

---

## Data Flow

```
TOMEHUB_SEARCH_LOGS (Oracle)
         ↓
   extract_search_logs Task
         ↓ (XCom: JSON DataFrame)
    ┌────┴────────────────────────┐
    ↓            ↓                 ↓
   intent   strategy          performance
  analysis  analysis          analysis
    ↓            ↓                 ↓
    └────┬───────┴─────────────────┘
         ↓ (XCom: Plot data)
    generate_report
         ↓ (XCom: Markdown string)
    notify_completion
         ↓
    Airflow Logs
```

---

## Configuration Variables

Can be set in Airflow UI or `airflow_settings.yaml`:

```yaml
airflow:
  variables:
    - variable_name: tomehub_analytics_email
      variable_value: analytics@example.com
    - variable_name: tomehub_slack_channel
      variable_value: "#data-analytics"
    - variable_name: tomehub_report_storage
      variable_value: "include/reports"
```

**Current Usage:** None (can be extended for email/Slack notifications)

---

## Monitoring & Troubleshooting

### Check DAG Status
```bash
af dags get tomehub_search_analytics
af dags explore tomehub_search_analytics
```

### Trigger Manual Run
```bash
af runs trigger tomehub_search_analytics
```

### Monitor Execution
```bash
af runs trigger-wait tomehub_search_analytics --timeout 300
```

### View Task Logs
```bash
af tasks logs tomehub_search_analytics <run_id> extract_search_logs
af tasks logs tomehub_search_analytics <run_id> analyze_intent
af tasks logs tomehub_search_analytics <run_id> generate_report
```

### Diagnose Failures
```bash
af runs diagnose tomehub_search_analytics <run_id>
```

---

## Performance Characteristics

| Task | Est. Duration | Notes |
|------|---------------|-------|
| extract_search_logs | 10-30s | Depends on 24h log volume |
| analyze_intent | 5-15s | Pandas groupby operations |
| analyze_strategy | 5-15s | Statistical calculations |
| analyze_performance | 5-15s | Bucketing and quantiles |
| generate_report | 3-10s | String building |
| notify_completion | <1s | Logging |
| **Total** | **40-85s** | ~1-2 min expected runtime |

---

## Known Limitations

1. **XCom Size:** Pandas DataFrame serialization limited to ~2MB default
   - Current: 1,249 logs ✓ (well under limit)
   - Future scaling: May need external storage (S3, Oracle BLOB)

2. **Schema Assumptions:**
   - Assumes `TOMEHUB_SEARCH_LOGS` exists with all columns
   - Expects `FIREBASE_UID`, `EXECUTION_TIME_MS`, `RRF_SCORE` columns
   - Falls back gracefully if optional columns missing

3. **Timezone:** All times in UTC (Airflow default)
   - Reports use server timezone
   - Logs timestamps from Oracle

---

## Future Enhancements

### Phase 1: Report Persistence
- [ ] Store report as artifact in `/include/reports/`
- [ ] Create `TOMEHUB_ANALYTICS_DAILY` table for time-series
- [ ] Send report via email/Slack notification

### Phase 2: Advanced Analytics
- [ ] Trend analysis (daily, weekly, monthly)
- [ ] Anomaly detection (unusual query patterns)
- [ ] User segmentation by search behavior
- [ ] A/B test comparison for strategy changes

### Phase 3: Integration
- [ ] Dynamic task mapping for per-user analytics
- [ ] Datahub/Lineage integration
- [ ] Dashboard auto-update (Grafana, Looker)
- [ ] Alerts for SLO breaches

### Phase 4: Optimization
- [ ] Incremental analytics (only new logs)
- [ ] Parallel analysis for large datasets
- [ ] Caching frequent calculations
- [ ] Query optimization for billion-row tables

---

## Related DAGs

Future analytics pipelines for TomeHub:

- `tomehub_ingestion_analytics` - Track document intake rate
- `tomehub_content_quality_analytics` - Vector coverage, embedding validity
- `tomehub_graph_analytics` - Concept graph density, traversal patterns
- `tomehub_user_analytics` - User activity, retention, churn
- `tomehub_cost_analytics` - API costs, embedding costs, query costs

---

## Validation Checklist

Before deploying to production:

- [ ] DAG parses without errors: `af dags errors`
- [ ] Tasks visible: `af dags explore tomehub_search_analytics`
- [ ] Manual trigger succeeds: `af runs trigger-wait tomehub_search_analytics --timeout 300`
- [ ] Report generates correctly
- [ ] No slow queries in analytics (recursive >5s)
- [ ] Database connection pooling works
- [ ] Error handling tested (missing columns, empty dataset)

---

**Last Updated:** 2026-02-22  
**Status:** Ready for Testing  
**Owner:** data-team  

---

## Quick Start

1. **Place file** in `dags/tomehub_search_analytics.py`
2. **Validate:** `af dags errors`
3. **Test:** `af runs trigger-wait tomehub_search_analytics --timeout 300`
4. **Monitor:** Check task logs for report output
5. **Schedule:** DAG will auto-run daily at 2 AM UTC

See [IMPLEMENTATION_PLAN.md](../../documentation/IMPLEMENTATION_PLAN_PHASE_ABC.md) for full Airflow setup if needed.
