# Ingestion Consistency Checklist

## Input capture
1. Record item id, ingestion timestamp, and endpoint used.
2. Record expected vs observed search behavior.

## Pipeline checks
1. Confirm ingestion completion status.
2. Verify whether vector indexing is complete.
3. Verify whether graph enrichment is complete or pending.

## Interpretation
1. Visible in vector only: expected interim state.
2. Missing in both: ingestion or indexing failure likely.
3. Present but low rank: ranking or query mismatch likely.

## Output format
1. Current readiness state.
2. Probable bottleneck.
3. Next operator step and recheck window.
