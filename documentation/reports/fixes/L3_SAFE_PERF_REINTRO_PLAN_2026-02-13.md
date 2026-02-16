# Layer-3 Safe Performance Reintroduction Report (2026-02-13)

## Scope
- Layer-3 Standard and Explorer latency tuning
- Quality-first approach (short/underfilled answer regression must be prevented)
- Gradual rollout with rollback-friendly flags

## KPI Targets
1. Standard (`/api/search`): `P50 = 14-20s`, `P95 <= 26s`
2. Explorer (`/api/chat`, mode=`EXPLORER`): `P50 = 8-12s`, `P95 <= 16s`

## Benchmark Set Design (6 queries)
- Distribution: `2 short (2-4 words) + 2 medium (5-9 words) + 2 long (10-16 words)`
- Same 6 queries will be used for both Standard and Explorer for fair comparison.
- Dataset: `apps/backend/data/l3_phase1_query_set_6.json`

## Current Baseline Snapshot
- `L3_PERF_CONTEXT_BUDGET_ENABLED=false`
- `L3_PERF_OUTPUT_BUDGET_ENABLED=false`
- `L3_PERF_REWRITE_GUARD_ENABLED=false` (before Phase-1)
- `L3_PERF_SUPPLEMENTARY_GATE_ENABLED=false` (before Phase-1)
- `L3_PERF_EXPANSION_TAIL_FIX_ENABLED=false` (before Phase-1)
- `L3_PERF_CONTEXT_CHARS_STANDARD=2000` (before Phase-1)
- `L3_PERF_MAX_OUTPUT_TOKENS_STANDARD=4000` (before Phase-1)

## Phase-1 Decision
Phase-1 starts with only low-risk guards enabled. Context/output hard budgets remain disabled.

### Applied Phase-1 Settings
- `L3_PERF_REWRITE_GUARD_ENABLED=true`
- `L3_PERF_SUPPLEMENTARY_GATE_ENABLED=true`
- `L3_PERF_EXPANSION_TAIL_FIX_ENABLED=true`
- `L3_PERF_CONTEXT_BUDGET_ENABLED=false`
- `L3_PERF_OUTPUT_BUDGET_ENABLED=false`

### Gradual Parameter Reduction (requested)
- `L3_PERF_CONTEXT_CHARS_STANDARD`: `2000 -> 1400`
- `L3_PERF_MAX_OUTPUT_TOKENS_STANDARD`: `4000 -> 2800`

Note: these two values are reduced now, but not active yet because output/context budget flags are still off in Phase-1.

### Phase-1 Benchmark Run Command
```bash
cd apps/backend
python scripts/phase0_benchmark.py --uid <FIREBASE_UID> --base-url http://localhost:5000 --dataset data/l3_phase1_query_set_6.json --chat-sample-size 6
```

## Next Step Plan (after Phase-1 measurements)
If KPI and quality remain stable:
1. Step-2 candidate: `context_chars ~1100`, `max_output_tokens ~2200`
2. Step-3 candidate: `context_chars ~900`, `max_output_tokens ~1800`
3. Only then evaluate selective enablement of context/output budget in safe profile.

## Rollback
Immediate rollback path is available by toggling:
- `L3_PERF_REWRITE_GUARD_ENABLED=false`
- `L3_PERF_SUPPLEMENTARY_GATE_ENABLED=false`
- `L3_PERF_EXPANSION_TAIL_FIX_ENABLED=false`

No schema or API contract change in Phase-1.
