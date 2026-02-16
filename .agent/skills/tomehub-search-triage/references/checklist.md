# Search Triage Checklist

## Quick isolate
1. Confirm whether issue is on `/api/search` or `/api/smart-search`.
2. Capture one failing query and one passing query.
3. Note if mismatch is ranking, missing sources, or stale context.

## Retrieval checks
1. Validate retrieval path used (keyword, lemma, semantic, graph).
2. Check whether graph evidence is expected but missing.
3. Verify if endpoint path excludes graph by design.

## Ranking checks
1. Determine whether fusion mode or strict ordering dominates.
2. Inspect if exact-match noise pushes better semantic hits down.
3. Compare top-3 with expected grounded documents.

## Output format
1. Root cause hypothesis.
2. Confidence level (high, medium, low).
3. Next step with owner (code, data, or runbook).
