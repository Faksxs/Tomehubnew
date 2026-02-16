# Phase-0 Baseline Report (20260211_033608)

## Scope
- Endpoints: /api/search, /api/smart-search, /api/chat (EXPLORER)
- Metrics: success/timeout, latency p50-p95, MRR, nDCG@10, graph hit-rate probe

## Acceptance Targets
- Quality gain target (future comparison): >= +5%
- Latency increase ceiling (future comparison): <= +10%
- Explorer p95 target: <= 12000ms

## Endpoint: search
- Query count: 18
- Success rate: 0.667
- Timeout rate: 0.333
- Latency p50/p95 (ms): 20637.3 / 25028.3
- Result count mean: 6.00
- MRR mean: 0.3778
- nDCG@10 mean: 0.3512

## Endpoint: smart
- Query count: 18
- Success rate: 1.000
- Timeout rate: 0.000
- Latency p50/p95 (ms): 2374.3 / 4298.5
- Result count mean: 176.94
- MRR mean: 0.3421
- nDCG@10 mean: 0.3202
