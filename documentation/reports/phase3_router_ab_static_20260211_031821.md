# Phase-0 Baseline Report (20260211_031821)

## Scope
- Endpoints: /api/search, /api/smart-search, /api/chat (EXPLORER)
- Metrics: success/timeout, latency p50-p95, MRR, nDCG@10, graph hit-rate probe

## Acceptance Targets
- Quality gain target (future comparison): >= +5%
- Latency increase ceiling (future comparison): <= +10%
- Explorer p95 target: <= 12000ms

## Endpoint: search
- Query count: 24
- Success rate: 1.000
- Timeout rate: 0.000
- Latency p50/p95 (ms): 21180.6 / 33301.3
- Result count mean: 10.00
- MRR mean: 0.5433
- nDCG@10 mean: 0.5102

## Endpoint: smart
- Query count: 24
- Success rate: 1.000
- Timeout rate: 0.000
- Latency p50/p95 (ms): 1809.6 / 3745.3
- Result count mean: 145.92
- MRR mean: 0.3688
- nDCG@10 mean: 0.3439

## Endpoint: chat_explorer
- Query count: 10
- Success rate: 1.000
- Timeout rate: 0.000
- Latency p50/p95 (ms): 10417.1 / 12466.4
- Result count mean: 9.60
- MRR mean: 0.4625
- nDCG@10 mean: 0.4389
- Explorer avg attempts: 1.00
- Explorer fallback-timeout rate: 0.000
