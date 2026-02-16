# Layer-3 Phase-1 Benchmark Report (6 Queries) - 2026-02-13

## Scope
- Phase-1 configuration validated after enabling low-risk guards:
  - `L3_PERF_REWRITE_GUARD_ENABLED=true`
  - `L3_PERF_SUPPLEMENTARY_GATE_ENABLED=true`
  - `L3_PERF_EXPANSION_TAIL_FIX_ENABLED=true`
- Budget flags remain disabled:
  - `L3_PERF_CONTEXT_BUDGET_ENABLED=false`
  - `L3_PERF_OUTPUT_BUDGET_ENABLED=false`

## Dataset
- File: `apps/backend/data/l3_phase1_query_set_6.json`
- Mix: `2 short + 2 medium + 2 long`

## Measurement Method
Two runs were attempted:
1. HTTP benchmark script (`phase0_benchmark.py`) against local API
2. Service-level benchmark (direct Python calls) to bypass endpoint auth blocker and measure real L3 runtime

## Result A - HTTP Benchmark (Blocked)
- Reports:
  - `documentation/reports/phase0_baseline_20260213_175700.md`
  - `documentation/reports/phase0_baseline_20260213_175828.md`
- Outcome:
  - `401 Unauthorized` on `/api/search`, `/api/smart-search`, `/api/chat`
  - Success rate: `0.000`
- Conclusion: endpoint-path latency KPI could not be trusted from these runs.

## Result B - Service-Level L3 Benchmark (Valid for pipeline timing)
- Standard (`generate_answer`) over 6 queries:
  - `P50 = 2.856s`
  - `P95 = 19.901s`
  - Details: `[3.269, 2.686, 2.475, 2.167, 25.445, 3.026]`
- Explorer (`get_rag_context + generate_evaluated_answer`) over 6 queries:
  - `P50 = 27.718s`
  - `P95 = 58.005s`
  - Details: `[11.894, 13.338, 10.558, 42.097, 62.516, 44.472]`

## KPI Comparison
- Standard target: `14-20s` (P50)
  - Current service-level P50 (`2.856s`) is faster than target window; one tail outlier (`25.445s`) exists.
- Explorer target: `8-12s` (P50)
  - Current service-level P50 (`27.718s`) misses target significantly.

## Observed Bottlenecks
1. Explorer path has heavy tail due to LLM provider timeouts/fallback:
   - `Qwen primary failed with retryable error; using secondary fallback`
2. Long query graph retrieval also contributes delay:
   - Graph retrieval logs show multi-second spikes
3. One Standard outlier came from long query path (retrieval+generation spike).

## Phase-2 Proposed Focus (next action)
1. Explorer provider timeout budget tighten + faster fallback trigger
2. Explorer max-attempt policy hard-cap to reduce long tails on retry paths
3. Graph retrieval timeout clamp for long queries to cap outliers
4. Re-run same 6-query benchmark and compare deltas

## Notes
- No API contract change was introduced in this benchmark step.
- Auth-related temporary experiments were reverted; current auth behavior remains original.

---

## Phase-2 Trial (applied immediately after this report draft)

### Applied code changes
1. `apps/backend/services/dual_ai_orchestrator.py`
- Explorer watchdog timeout: `45s -> 24s`
- Fast-track threshold fixed to reachable range:
  - `confidence >= 5.5 and DIRECT` -> `confidence >= 4.5 and (DIRECT or FOLLOW_UP)`

2. `apps/backend/services/work_ai_service.py`
- Explorer output token cap: `2048 -> 1945` (about `%5` reduction)
- Explorer LLM timeout: `None -> 12s`

### Re-benchmark (same 6-query set, service-level)
- Standard:
  - `P50 = 2.368s`
  - `P95 = 29.773s`
  - Details: `[2.935, 2.245, 2.079, 2.012, 38.719, 2.491]`
- Explorer:
  - `P50 = 24.878s`
  - `P95 = 39.849s`
  - Details: `[19.267, 24.666, 25.853, 24.148, 44.514, 25.091]`

### Delta vs previous service-level run
- Explorer improved but still above target:
  - `P50: 27.718s -> 24.878s` (better)
  - `P95: 58.005s -> 39.849s` (better)
- Standard tail remains unstable due long-query outlier.

### Interpretation
1. Explorer long-tail is still dominated by retrieval + provider fallback delays.
2. `%5` depth reduction was safe for structure but not enough for target latency.
3. Next effective lever should be retrieval-tail clamp (especially long-query graph path), not only LLM timeout.

---

## Phase-2 Trial B (Explorer provider route change)

### Additional applied config
1. `apps/backend/.env`
- `LLM_EXPLORER_QWEN_PILOT_ENABLED=false`

Reason: Qwen timeout + fallback sequence was the dominant Explorer tail source.

### Re-benchmark (same 6-query set, service-level)
- Standard:
  - `P50 = 3.162s`
  - `P95 = 51.770s`
  - Details: `[3.089, 2.456, 61.008, 2.612, 24.054, 3.235]`
- Explorer:
  - `P50 = 11.471s`  ✅ target band (`8-12s`) achieved
  - `P95 = 38.196s`  ❌ tail still high
  - Details: `[11.632, 10.805, 10.019, 11.309, 46.543, 13.154]`

### Interpretation
1. Explorer median latency is now in target range with Gemini-first route.
2. Tail latency problem remains and comes from retrieval spikes on long prompts.
3. Next action should focus on long-query retrieval clamps (graph/context path), not LLM provider route.
