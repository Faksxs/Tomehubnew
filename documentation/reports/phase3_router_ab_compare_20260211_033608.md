# Phase-3 Router A/B Compare Report (20260211_033608)

## Decision
- quality_change_pct: 21.22
- latency_gain_pct: -2.44
- quality_pass (>= -2%): True
- latency_pass (>= +5%): False
- recommend_rule_based: False

## Endpoint Deltas (rule_based - static)
### search
- success_rate delta: 0.0556
- timeout_rate delta: -0.0556
- latency_p50_ms delta: -2000.44
- latency_p95_ms delta: 2.10
- mrr_mean delta: 0.1222
- ndcg_at_10_mean delta: 0.1197
- explorer_avg_attempts delta: 0.0000
- explorer_fallback_timeout_rate delta: 0.0000

### smart
- success_rate delta: 0.0000
- timeout_rate delta: 0.0000
- latency_p50_ms delta: 704.11
- latency_p95_ms delta: 697.16
- mrr_mean delta: 0.0240
- ndcg_at_10_mean delta: -0.0224
- explorer_avg_attempts delta: 0.0000
- explorer_fallback_timeout_rate delta: 0.0000
