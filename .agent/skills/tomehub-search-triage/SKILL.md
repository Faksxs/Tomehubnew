---
name: tomehub-search-triage
description: Diagnose TomeHub search quality issues by isolating retrieval path differences, ranking behavior, and graph/vector contribution in /api/search and /api/smart-search.
---

# TomeHub Search Triage

Use this skill when users report low relevance, noisy ranking, inconsistent search results, or search regressions.

## Triggers
- search quality
- wrong ranking
- /api/search
- /api/smart-search
- relevance regression
- triage search

## Workflow
1. Confirm endpoint and query sample first.
2. Identify active retrieval path and ranking strategy.
3. Compare expected source coverage vs returned evidence.
4. Document likely root cause and next corrective action.

## References
- Read `references/checklist.md` for a concise triage decision tree.
