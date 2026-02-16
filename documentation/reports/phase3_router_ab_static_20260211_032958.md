# Phase-0 Baseline Report (20260211_032958)

## Scope
- Endpoints: /api/search, /api/smart-search, /api/chat (EXPLORER)
- Metrics: success/timeout, latency p50-p95, MRR, nDCG@10, graph hit-rate probe

## Acceptance Targets
- Quality gain target (future comparison): >= +5%
- Latency increase ceiling (future comparison): <= +10%
- Explorer p95 target: <= 12000ms

## Endpoint: search
- Query count: 18
- Success rate: 0.611
- Timeout rate: 0.389
- Latency p50/p95 (ms): 22637.8 / 25026.2
- Result count mean: 5.33
- MRR mean: 0.2556
- nDCG@10 mean: 0.2314

## Endpoint: smart
- Query count: 18
- Success rate: 1.000
- Timeout rate: 0.000
- Latency p50/p95 (ms): 1670.2 / 3601.3
- Result count mean: 141.33
- MRR mean: 0.3181
- nDCG@10 mean: 0.3426
